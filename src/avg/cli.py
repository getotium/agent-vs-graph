"""avg: the agent-vs-graph benchmark's command line.

avg meter   run the metering proxy in front of a model endpoint
avg stub    run the stand-in model server (tests and dry runs)
avg data    build a task's input file from a public dataset
avg run     run one arm of a task through the meter
avg harness run an agent harness (Claude Code, Hermes Agent) on the task as files
avg serial  run every arm one after another on local models, one model loaded at a time
avg hosted  run the arms against a hosted Anthropic model (the key from ANTHROPIC_API_KEY)
avg device  print llama-server's --device flag for the configured GPU (local.toml)
avg score   score arms' results against the gold answers
avg report  price a ledger and print the Markdown report
avg publish copy a finished run to results/, with its scores and report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import aiohttp
from aiohttp import web

from . import config, data, harness, ledger, llm, meter, paired, prices, publish, report, serial, stub
from .llm import Client, InfraError
from .scores import score_files
from .tasks import enrich


def _items(pairs: list[str]) -> dict[tuple[str, str], int]:
    out = {}
    for p in pairs:
        key, _, n = p.partition("=")
        task, _, arm = key.partition(":")
        if not (task and arm and n.isdigit()):
            raise SystemExit(f"--items wants task:arm=N, got {p!r}")
        out[(task, arm)] = int(n)
    return out


def _routes(pairs: list[str]) -> dict[str, str]:
    out = {}
    for p in pairs:
        model, _, url = p.partition("=")
        if not (model and url.startswith("http")):
            raise SystemExit(f"--route wants MODEL=URL, got {p!r}")
        out[model] = url
    return out


async def _run(a: argparse.Namespace, out) -> list[dict]:
    """Every item's result row. An agent arm also writes each row to `out` as it finishes, so a
    run that breaks part way keeps its finished items; the caller rewrites the file in order."""
    items = enrich.load(a.items)[: a.limit or None]
    timeout = aiohttp.ClientTimeout(total=None, sock_read=900)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # A hosted graph marks only its shared system prompt for caching: each step's request ends
        # in one item's listing, so caching the tail would pay the write premium for nothing. An
        # agent also caches its growing conversation, which its next turn re-sends.
        cache = "system" if a.shape == "graph" else "conversation"
        client = Client(session, a.meter, a.run, wire=a.wire, api_key=_key(a.wire), cache=cache, thinking=a.thinking)
        if a.shape == "graph":
            models = enrich.Models(small=a.small or a.model, large=a.large or a.model)
            reasons: dict[str, str] = {}
            records = await enrich.graph(client, a.arm, items, models, limit=a.concurrency, reasons=reasons)
            return [{"arm": a.arm, "id": it.id, "record": records.get(it.id), "reason": reasons.get(it.id, "")}
                    for it in items]  # fmt: skip

        def row(it: enrich.Item, o, record) -> dict:
            return {"arm": a.arm, "id": it.id, "record": record, "turns": o.turns, "reason": o.reason}

        def done(it, o, record) -> None:
            out.write(json.dumps(row(it, o, record)) + "\n")
            out.flush()

        records, outcomes = await enrich.agents(client, a.arm, items, a.model, a.concurrency, a.max_turns, done)
        return [row(it, outcomes[it.id], records.get(it.id)) for it in items]


def _key(wire: str) -> str:
    """The Anthropic API key for a hosted run, from the environment only; never from a flag, so it
    stays out of process listings and shell history."""
    if wire != "anthropic":
        return ""
    key = os.environ.get(llm.KEY_ENV, "")
    if not key:
        raise SystemExit(f"--wire anthropic needs {llm.KEY_ENV} (put it in .env.local; the Taskfile loads it)")
    return key


def _local() -> config.Local:
    try:
        return config.load()
    except (OSError, ValueError) as e:
        raise SystemExit(str(e)) from None


def _device(local: config.Local) -> str:
    """The configured device as llama.cpp names it, or "" when none is configured."""
    if not local.device:
        return ""
    try:
        return serial.pick_device(local.device, serial.list_devices(local.llama_server))
    except ValueError as e:
        raise SystemExit(str(e)) from None


def _serial(a: argparse.Namespace) -> int:
    local = _local()
    device = _device(local)
    print(f"[serial] device: {device or 'llama.cpp default (set device in local.toml)'}")
    small = serial.Server("gemma-4-e4b", local.small_gguf, 8082)
    large = serial.Server("gemma-4-12b", local.large_gguf, 8081)
    cfg = serial.Config(
        run=a.run, limit=a.limit, llama_server=local.llama_server, device=device, small=small, large=large,
        large_harness=serial.Server(large.alias, large.gguf, large.port, ctx=local.harness_ctx),
        hermes_bin=serial.resolve(local.hermes_bin), slots=a.slots or local.slots, thinking=a.thinking,
    )  # fmt: skip
    steps = serial.plan(cfg)
    if a.only:
        wanted = set(a.only.split(","))
        steps = [s for s in steps if s.arm in wanted]
    # The conditions every arm in the run shares, kept beside its results. No machine names.
    meta = {"limit": a.limit, "slots": cfg.slots, "thinking": cfg.thinking, "max_tokens": Client.max_tokens,
            "llama_server": Path(cfg.llama_server).parent.name, "small": Path(small.gguf).name,
            "large": Path(large.gguf).name, "harness_ctx": cfg.large_harness.ctx,
            "code": serial.code_version()}  # fmt: skip
    upstream = ["--openai", f"http://127.0.0.1:{large.port}",
                "--route", f"{large.alias}=http://127.0.0.1:{large.port}",
                "--route", f"{small.alias}=http://127.0.0.1:{small.port}"]  # fmt: skip
    return _sequence(a, cfg, steps, meta, upstream)


def _hosted(a: argparse.Namespace) -> int:
    if not os.environ.get(llm.KEY_ENV):
        raise SystemExit(f"hosted runs need {llm.KEY_ENV} (put it in .env.local; the Taskfile loads it)")
    cfg = serial.hosted_config(a.run, a.limit, a.slots, a.port)
    steps = serial.hosted_plan(cfg, a.model, a.thinking)
    if a.only:
        wanted = set(a.only.split(","))
        steps = [s for s in steps if s.arm in wanted]
    meta = {"limit": a.limit, "slots": cfg.slots, "thinking": 0 if a.thinking == "off" else "model default",
            "max_tokens": Client.max_tokens,
            "provider": "anthropic", "model": a.model, "anthropic_version": llm.ANTHROPIC_VERSION,
            "code": serial.code_version()}  # fmt: skip
    return _sequence(a, cfg, steps, meta, ["--openai", llm.ANTHROPIC_API, "--anthropic", llm.ANTHROPIC_API])


def _sequence(a: argparse.Namespace, cfg: serial.Config, steps: list[serial.Step], meta: dict,
              upstream: list[str]) -> int:  # fmt: skip
    """Record the run's conditions, start the meter in front of `upstream`, run the steps in turn
    and score what they wrote."""
    runs = Path("runs") / a.run
    runs.mkdir(parents=True, exist_ok=True)
    try:
        serial.check_meta(runs / "meta.json", meta)
    except ValueError as e:
        raise SystemExit(str(e)) from None
    meter_argv = [sys.executable, "-m", "avg.cli", "meter", "--port", str(cfg.meter_port), *upstream,
                  "--ledger", str(runs / "ledger.jsonl")]  # fmt: skip
    runner = serial.Runner()
    m = runner.start(meter_argv, runs / "meter.log")
    try:
        codes = runner.sequence(cfg, steps, runs, ledger_path=runs / "ledger.jsonl", replace=a.replace)
    finally:
        serial.stop(m)
    done = [runs / f"{s.arm}.jsonl" for s in steps if (runs / f"{s.arm}.jsonl").exists()]
    if done:
        table, counts = score_files(Path("data/enrich/items.jsonl"), done)
        sys.stdout.write(table)
        (runs / "scores.json").write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")
    return 0 if all(c == 0 for c in codes.values()) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="avg")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("meter", help="run the metering proxy")
    m.add_argument("--port", type=int, default=8787)
    m.add_argument("--openai", default="http://127.0.0.1:8080", help="upstream for chat completions")
    m.add_argument("--anthropic", default="", help="upstream for Messages (default: same as --openai)")
    m.add_argument("--route", action="append", default=[], help="MODEL=URL: chat completions for MODEL go to URL")
    m.add_argument("--ledger", type=Path, default=Path("runs/ledger.jsonl"))

    s = sub.add_parser("stub", help="run the stand-in model server")
    s.add_argument("--port", type=int, default=8080)

    d = sub.add_parser("data", help="build the enrichment task's items from the ESCI product catalog")
    d.add_argument("parquet", type=Path, help="shopping_queries_dataset_products.parquet")
    d.add_argument("--n", type=int, default=1000)
    d.add_argument("--seed", type=int, default=1)
    d.add_argument("--out", type=Path, default=Path("data/enrich/items.jsonl"))

    r = sub.add_parser("run", help="run one arm of the enrichment task through the meter")
    r.add_argument("--shape", choices=["graph", "agent"], required=True)
    r.add_argument("--arm", required=True, help="the arm's name in the ledger, e.g. graph or agent-12b")
    r.add_argument("--run", required=True, help="the run's name in the ledger")
    r.add_argument("--items", type=Path, default=Path("data/enrich/items.jsonl"))
    r.add_argument("--limit", type=int, default=0, help="first N items only")
    r.add_argument("--meter", default="http://127.0.0.1:8787")
    r.add_argument("--model", default="", help="the agent's model, or the graph's for both sizes")
    r.add_argument("--small", default="", help="graph: model for extract and describe")
    r.add_argument("--large", default="", help="graph: model for repairs")
    r.add_argument("--concurrency", type=int, default=4, help="requests in flight (the server's slots)")
    r.add_argument(
        "--wire",
        choices=["openai", "anthropic"],
        default="openai",
        help="openai for local models; anthropic for a hosted Claude model (key from ANTHROPIC_API_KEY)",
    )
    r.add_argument(
        "--thinking",
        choices=["off", "default"],
        default="off",
        help="anthropic: off sends thinking disabled; default leaves the model's own (local: set on the server)",
    )
    r.add_argument("--max-turns", type=int, default=8)
    r.add_argument("--out", type=Path, required=True, help="results file (.jsonl)")

    h = sub.add_parser("harness", help="run an agent harness on the enrichment task, handed the whole file")
    h.add_argument("--harness", choices=sorted(harness.HARNESSES), required=True)
    h.add_argument("--arm", default="", help="the arm's name in the ledger (default: the harness's name)")
    h.add_argument("--run", required=True)
    h.add_argument("--items", type=Path, default=Path("data/enrich/items.jsonl"))
    h.add_argument("--limit", type=int, default=0, help="first N items only")
    h.add_argument("--meter", default="http://127.0.0.1:8787")
    h.add_argument("--model", required=True)
    h.add_argument("--max-turns", type=int, default=150, help="the same cap for every harness")
    h.add_argument("--timeout", type=int, default=4 * 3600, help="seconds before the harness is stopped")
    h.add_argument("--bin", default="", help="the harness's executable (default: claude, or hermes on PATH)")
    h.add_argument("--workspace", type=Path, help="default: a directory under the system temp dir, "
                   "outside any repository so no CLAUDE.md is picked up")  # fmt: skip
    h.add_argument("--out", type=Path, required=True, help="results file (.jsonl)")
    h.add_argument(
        "--hosted",
        action="store_true",
        help="claude-code against the hosted API: the meter forwards to Anthropic with ANTHROPIC_API_KEY",
    )

    se = sub.add_parser("serial", help="run every arm one after another, one model server at a time")
    se.add_argument("--run", required=True)
    se.add_argument("--limit", type=int, default=20)
    se.add_argument("--only", default="", help="comma-separated arms to run (default: all)")
    se.add_argument(
        "--thinking",
        type=int,
        default=0,
        help="thinking tokens per reply for every arm: 0 off (default), N a budget, -1 no limit",
    )
    se.add_argument("--replace", action="store_true", help="rerun arms that already have records in this run")
    se.add_argument("--slots", type=int, default=0, help="requests in flight for per-item arms (default: local.toml)")

    ho = sub.add_parser("hosted", help="run the arms against a hosted Anthropic model, one after another")
    ho.add_argument("--run", required=True)
    ho.add_argument("--limit", type=int, default=50)
    ho.add_argument("--only", default="", help="comma-separated arms to run (default: all)")
    ho.add_argument("--model", default="claude-haiku-5-5")
    ho.add_argument("--thinking", choices=["off", "default"], default="off",
                    help="off: graph and agent with thinking disabled (Claude Code cannot be); default: every arm "
                         "as the model ships")  # fmt: skip
    ho.add_argument("--slots", type=int, default=4, help="requests in flight for per-item arms")
    ho.add_argument("--port", type=int, default=8788, help="the meter's port (a local run may hold 8787)")
    ho.add_argument("--replace", action="store_true", help="rerun arms that already have records in this run")

    sub.add_parser("device", help="print llama-server's --device flag for the configured GPU (empty if none)")

    sc = sub.add_parser("score", help="score results files against the gold answers")
    sc.add_argument("results", type=Path, nargs="+")
    sc.add_argument("--items", type=Path, default=Path("data/enrich/items.jsonl"))
    sc.add_argument("--out", type=Path, help="write success counts as JSON, for report --scores")

    rp = sub.add_parser("report", help="price a ledger and print the report")
    rp.add_argument("ledgers", type=Path, nargs="+")
    rp.add_argument("--prices", type=Path, default=Path("prices/default.yaml"))
    rp.add_argument("--price-as", action="append", default=[], help="price id to show (repeatable; default all)")
    rp.add_argument(
        "--batchable",
        action="append",
        default=[],
        help="arms that can run as batches (default: graph and every graph-* arm)",
    )
    rp.add_argument("--run", action="append", default=[], help="only these runs from the ledgers (repeatable)")
    rp.add_argument("--items", action="append", default=[], help="task:arm=N for arms whose units are chunks")
    rp.add_argument("--volume", type=int, action="append", default=[], help="documents a month (repeatable)")
    rp.add_argument("--scores", type=Path, help="success counts from avg score --out")
    rp.add_argument("--title", default="Results")
    rp.add_argument("--pair", action="append", default=[],
                    help="GRAPH:AGENT arms to compare item by item (default: each agent-X with graph-X)")  # fmt: skip

    pb = sub.add_parser("publish", help="copy a finished run to results/, with its scores and report")
    pb.add_argument("run")
    pb.add_argument("--code", default="", help="the commit the run started at, for a run that predates recording it")

    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # the tables use – and …, which a Windows console mangles
    if a.cmd == "meter":
        up = meter.Upstreams(openai=a.openai, anthropic=a.anthropic or a.openai, models=_routes(a.route))
        web.run_app(meter.app(up, a.ledger), host="127.0.0.1", port=a.port)
    elif a.cmd == "stub":
        web.run_app(stub.app(), host="127.0.0.1", port=a.port)
    elif a.cmd == "data":
        items = data.sample(data.esci_rows(a.parquet), a.n, a.seed)
        data.write(items, a.out)
        print(f"{len(items)} items written to {a.out}")
    elif a.cmd == "run":
        if not (a.model or (a.small and a.large)):
            raise SystemExit("run needs --model, or --small and --large for a graph")
        if a.shape == "agent" and not a.model:
            raise SystemExit("an agent runs on one --model")
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open("w", encoding="utf-8", newline="\n") as f:
            try:
                rows = asyncio.run(_run(a, f))
            except InfraError as e:
                raise SystemExit(f"run broken, not scored: {e}. Items finished so far are in {a.out}.") from None
        with a.out.open("w", encoding="utf-8", newline="\n") as f:
            f.writelines(json.dumps(row) + "\n" for row in rows)
        print(f"{sum(r['record'] is not None for r in rows)}/{len(rows)} records written to {a.out}")
    elif a.cmd == "harness":
        arm = a.arm or a.harness
        items = enrich.load(a.items)[: a.limit or None]
        root = a.workspace or Path(tempfile.gettempdir()) / "avg-ws" / a.run / arm
        ws = harness.workspace(root, items)
        base = f"{a.meter.rstrip('/')}/t/{a.run}/{arm}/{enrich.TASK}/all"
        make = harness.HARNESSES[a.harness]
        if a.hosted and a.harness != "claude-code":
            raise SystemExit("--hosted runs claude-code only")
        kw = {"binary": a.bin} if a.bin else {}
        if a.hosted:
            kw["api_key"] = _key("anthropic")
        inv = make(ws, base, a.model, a.max_turns, **kw)
        started = time.monotonic()
        code = harness.run(inv, a.timeout)
        records = harness.collect(ws)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open("w", encoding="utf-8", newline="\n") as f:
            for it in items:
                f.write(json.dumps({"arm": arm, "id": it.id, "record": records.get(it.id)}) + "\n")
        print(f"{a.harness} exited {code} after {time.monotonic() - started:.0f}s; "
              f"{len(records)}/{len(items)} records written to {a.out}; workspace {ws}")  # fmt: skip
    elif a.cmd == "serial":
        return _serial(a)
    elif a.cmd == "hosted":
        return _hosted(a)
    elif a.cmd == "device":
        device = _device(_local())
        print(f"--device {device}" if device else "")
    elif a.cmd == "score":
        table, counts = score_files(a.items, a.results)
        sys.stdout.write(table)
        if a.out:
            a.out.write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")
    elif a.cmd == "report":
        sheet = prices.load(a.prices)
        chosen = [sheet[i] for i in a.price_as] if a.price_as else list(sheet.values())
        recs = (r for r in ledger.read(a.ledgers) if not a.run or r.run in a.run)
        try:
            groups = report.group(recs, _items(a.items))
        except ValueError as e:
            raise SystemExit(str(e)) from None
        if not groups:
            raise SystemExit("the ledger has no successful requests")
        success, passed = None, None
        if a.scores:
            counts = json.loads(a.scores.read_text(encoding="utf-8"))
            success = {tuple(k.split(":", 1)): v["succeeded"] / v["items"] for k, v in counts.items()}
            passed = {tuple(k.split(":", 1)): v["passed"] for k, v in counts.items() if "passed" in v}
        pairs = [tuple(p.split(":", 1)) for p in a.pair] or paired.default_pairs({g.arm for g in groups})
        vols = a.volume or [10_000, 100_000, 1_000_000]
        batchable = set(a.batchable) or {g.arm for g in groups if g.arm == "graph" or g.arm.startswith("graph-")}
        sys.stdout.write(report.render(groups, chosen, batchable, vols, a.title, success, passed, pairs))
    elif a.cmd == "publish":
        try:
            done = publish.publish(a.run, code=a.code)
        except ValueError as e:
            raise SystemExit(str(e)) from None
        print(f"{a.run}: {', '.join(done.arms)} published to {done.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
