"""Publishing a run: from the scratch area (runs/, gitignored) to results/, which is committed.

Only what a reader needs to check or rescore the run is copied: its conditions, its ledger, each
arm's outputs, the scores and the report generated from them. Server logs stay behind; they name
the machine's GPU and paths. The report is always regenerated here, never edited, so its tables
match the data beside it.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import harness, ledger, paired, prices, report
from .scores import score_files
from .tasks import enrich, intake


@dataclass
class Published:
    path: Path
    arms: list[str]


def publish(
    run: str,
    runs: Path = Path("runs"),
    results: Path = Path("results"),
    items: Path = Path("data/enrich/items.jsonl"),
    sheet: Path = Path("prices/default.yaml"),
    code: str = "",
) -> Published:
    """Copy one run to results/<run>, score it and write its report. `code` names the commit for a
    run whose meta.json predates recording it; the meta then says it was added afterwards."""
    src, dst = runs / run, results / run
    meta_path = src / "meta.json"
    if not meta_path.exists():
        raise ValueError(f"{meta_path} not found: only runs started by `avg serial` can be published")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if code and not meta.get("code"):
        meta["code"], meta["code_note"] = code, "recorded at publication, from the commit the run was started at"
    elif code and meta["code"] != code:
        raise ValueError(f"{meta_path} already names code {meta['code']}")
    if not meta.get("code") or meta["code"] == "unknown":
        raise ValueError(f"{meta_path} names no code version; pass the commit the run was started at")
    if meta["code"].endswith("-dirty"):
        raise ValueError(f"run {run} ran on uncommitted code ({meta['code']}); it cannot be reproduced")

    arms = sorted(ledger.arms(src / "ledger.jsonl", run))
    if not arms:
        raise ValueError(f"run {run} has no ledger records")
    missing = [a for a in arms if not (src / f"{a}.jsonl").exists()]
    if missing:
        raise ValueError(f"run {run} has ledger records but no results for: {', '.join(missing)}")

    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    (dst / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = (src / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    mine = [x for x in lines if x.strip() and json.loads(x)["run"] == run]
    (dst / "ledger.jsonl").write_text("".join(x + "\n" for x in mine), encoding="utf-8", newline="\n")
    outputs = []
    for a in arms:
        shutil.copyfile(src / f"{a}.jsonl", dst / f"{a}.jsonl")
        outputs.append(dst / f"{a}.jsonl")

    table, counts = score_files(Path(meta.get("items", items)), outputs)  # an intake run names its mix
    (dst / "scores.json").write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8", newline="\n")
    rows = {a: sum(1 for x in (dst / f"{a}.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())
            for a in arms}  # fmt: skip
    # A harness is handed the whole file as one unit; the rest are one unit per item.
    chunked = {(meta.get("task", enrich.TASK), a): rows[a] for a in arms if harness.harness_of(a)}
    groups = report.group(ledger.read([dst / "ledger.jsonl"]), chunked)
    md = report.render(
        groups,
        list(prices.load(sheet).values()),
        {g.arm for g in groups if g.arm == "graph" or g.arm.startswith("graph-")},
        [10_000, 100_000, 1_000_000],
        f"Run {run}",
        success={tuple(k.split(":", 1)): v["succeeded"] / v["items"] for k, v in counts.items()},
        passed={tuple(k.split(":", 1)): v["passed"] for k, v in counts.items()},
        pairs=paired.default_pairs(set(arms)),
        guide=GUIDE,
    )
    _, body = md.split("\n", 1)
    head = context(run, meta, groups, table)
    (dst / "report.md").write_text("\n".join(head) + body, encoding="utf-8", newline="\n")
    index(results)
    return Published(dst, arms)


# Links from results/<run>/report.md back into the repo.
README, DESIGN, GUIDE = "../../README.md", "../../docs/design.md", "../../docs/reading-reports.md"

TASKS = {
    enrich.TASK: "product enrichment: each item is a product listing, to be turned into a validated catalog record",
    intake.TASK: "catalog intake: each item is a listing from a supplier's feed, to be catalogued with page content or "
    "skipped as a duplicate or excluded product",
}

CONDITIONS = {
    "limit": "items in the run, the first N of the task's input file",
    "slots": "requests a per-item arm keeps in flight at once; changes speed, not tokens",
    "thinking": "0: no thinking phase; N: up to N thinking tokens per reply",
    "max_tokens": "the cap on one reply, thinking included",
    "llama_server": "the llama.cpp build that served the models",
    "small": "the small model",
    "large": "the large model",
    "harness_ctx": "context window for the whole-file harnesses",
    "code": "the commit of this repo the run used",
    "provider": "the hosted API the run used; its own counts are the bill when priced as its model",
    "model": "the hosted model every arm used",
    "anthropic_version": "the Messages API version the requests named",
    "task": "the task, when it is not task 1",
    "items": "the input file: for catalog intake, the mix (items-20: 20% of the feed should be rejected)",
}

SUCCESS = {
    enrich.TASK: "- **Success** is a record that passes the shared validator and names the right brand.",
    intake.TASK: (
        "- **Success** is a skip for an item the store should not take (a duplicate, an excluded brand, a book), "
        "and for a new product a record with its page content that passes the shared validator and names the "
        "right brand. A product listed several times in the feed succeeds when exactly one listing is catalogued."
    ),
}


def shape(arm: str) -> str:
    """What an arm is, from its name (see docs/reading-reports.md#arms)."""
    if arm == "graph":
        return "Workflow graph; easy steps on the small model, repairs on the large"
    if arm.startswith("graph-") and arm.endswith("-lean"):
        return "Workflow graph; every step on one model, the description written without thinking"
    if arm.startswith("graph-") and arm.endswith("-gated"):
        return "Workflow graph; every step on one model, a cheap sort step first and loose brand matching"
    if arm.startswith("graph-"):
        return "Workflow graph; every step on one model"
    if arm.startswith("agent-"):
        return "One tool-calling agent per item"
    if harness.harness_of(arm) and "-skill" in arm:
        return "Agent harness handed the whole input file, with a skill for the task"
    if harness.harness_of(arm):
        return "Agent harness handed the whole input file"
    return "–"


def context(run: str, meta: dict, groups: list[report.Group], scores_table: str) -> list[str]:
    """The top of a published report: what the run is, its arms and conditions, how to read the
    numbers, and the scores. Facts and definitions only; what they mean is for the reader."""
    tasks = sorted({g.task for g in groups})
    what = "; ".join(f"`{t}`, {TASKS.get(t, 'see the README')}" for t in tasks)
    out = [
        f"# Run {run}",
        "",
        (
            f"One run of [agent-vs-graph]({README}), which measures what the same job costs when a fixed workflow graph "
            f"does it and when agent loops do. Task: {what}. The first {meta.get('limit', 'N')} items were given to "
            "every arm below. Every model request was metered; costs are those tokens priced afterwards at each "
            "vendor's published rates. This page is generated from the files beside it by `avg publish` and not "
            "edited by hand."
        ),
        "",
        (
            f"Read more: [how to read this report]({GUIDE}) · [why it is measured this way]({DESIGN}) · "
            "[all published runs](../README.md)"
        ),
        "",
        "## In brief",
        "",
        SUCCESS.get(meta.get("task", enrich.TASK), SUCCESS[enrich.TASK]),
        (
            "- **Costs** are per item, as each vendor would bill the run's tokens. The run itself was local: token "
            "counts are the local model's, so they compare arms like for like rather than quote a hosted bill."
        ),
        "- **Batch** prices apply only to graph arms; an agent's requests wait on each other's answers.",
        "- **Ranges** in brackets are 90% intervals on the average, from resampling the items.",
        "- **Graph against agent** puts the same model in both shapes side by side, item by item.",
        "",
        "## Arms",
        "",
        "| Arm | Shape | Model |",
        "| --- | --- | --- |",
    ]
    for g in groups:
        models = ", ".join(sorted({r.model for r in g.records}))
        out.append(f"| {g.arm} | {shape(g.arm)} | {models} |")
    out += ["", "## Conditions", "", "| Setting | Value | Meaning |", "| --- | --- | --- |"]
    for k, v in meta.items():
        if k != "code_note":
            out.append(f"| {k} | {v} | {CONDITIONS.get(k, '')} |")
    if meta.get("code_note"):
        out += ["", f"On `code`: {meta['code_note']}."]
    out += [
        "",
        "## Scores",
        "",
        (
            "How often each arm's output was right, against the catalog's own fields. Columns: "
            f"[reading a report]({GUIDE}#scores)."
        ),
        "",
        scores_table,
    ]
    return out


INDEX_HEAD = """# Published runs

Each folder is one run, committed as it was measured: `meta.json` (its conditions, and the commit
of this repo it ran on), `ledger.jsonl` (every model request's tokens, with a hash of the prompt's
shape and never its text), one `<arm>.jsonl` per arm (each item's output), `scores.json` and
`report.md`. The report is generated by `avg publish` and never edited by hand; rerun
`task publish RUN=<run>` from the run's scratch folder, or price the ledger yourself with
`avg report results/<run>/ledger.jsonl --scores results/<run>/scores.json`.

What every table and column in a report means: [docs/reading-reports.md](../docs/reading-reports.md).
Why the benchmark measures these things: [docs/design.md](../docs/design.md).

The outputs are written from listings in Amazon's Shopping Queries Dataset (ESCI), Apache-2.0;
see [data/enrich/README.md](../data/enrich/README.md) for the attribution.

This file is generated by `avg publish`.

| Run | Items | Thinking | Slots | Code | Report |
| --- | ---: | --- | ---: | --- | --- |
"""


def index(results: Path) -> None:
    """Rewrite results/README.md from every published run's meta.json."""
    rows = []
    for meta_path in sorted(results.glob("*/meta.json")):
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        run = meta_path.parent.name
        t = m.get("thinking")
        if isinstance(t, str):
            thinking = t  # a hosted run's "model default"
        else:
            thinking = "off" if not t else ("no limit" if t < 0 else f"{t:,} tokens")
        if m.get("model"):
            thinking += f" ({m['model']})"
        code = m.get("code", "–") + (" (recorded at publication)" if m.get("code_note") else "")
        rows.append(f"| {run} | {m.get('limit', '–')} | {thinking} | {m.get('slots', '–')} | {code} | "
                    f"[report]({run}/report.md) |\n")  # fmt: skip
    (results / "README.md").write_text(INDEX_HEAD + "".join(rows), encoding="utf-8", newline="\n")
