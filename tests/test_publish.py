"""Publishing a run: only the files a reader needs, a report generated from them, and an index."""

import json
from pathlib import Path

import pytest

from avg import data, ledger, publish
from avg.ledger import Record
from avg.tasks import enrich

SHEET = Path(__file__).parent.parent / "prices" / "default.yaml"
GOOD = {"category": "Home & Kitchen", "brand": "Acme", "color": "Blue", "specs": {"material": "steel"},
        "description": " ".join(["word"] * 20)}  # fmt: skip
ITEMS = [enrich.Item(f"p{i}", "Acme kettle", "Steel", "", {"brand": "Acme", "color": "Blue"}) for i in range(4)]
META = {"limit": 4, "slots": 4, "thinking": 0, "max_tokens": 4096, "code": "abc123def456"}


def rec(run, arm, item, input):
    return Record(run=run, arm=arm, task="enrich", item=item, wire="openai", model="m", input=input, cache_read=0,
                  cache_write=0, output=10, latency_ms=1, status=200)  # fmt: skip


@pytest.fixture
def tree(tmp_path):
    """A finished run r1 with a graph and an agent arm, plus another run's records in the ledger."""
    runs, items = tmp_path / "runs", tmp_path / "items.jsonl"
    data.write([{"id": it.id, "title": it.title, "bullets": it.bullets, "description": it.description,
                 "gold": it.gold} for it in ITEMS], items)  # fmt: skip
    src = runs / "r1"
    src.mkdir(parents=True)
    (src / "meta.json").write_text(json.dumps(META), encoding="utf-8")
    for it in ITEMS:
        ledger.append(src / "ledger.jsonl", rec("r1", "graph-12b", it.id, 100))
        ledger.append(src / "ledger.jsonl", rec("r1", "agent-12b", it.id, 300))
    ledger.append(src / "ledger.jsonl", rec("other", "graph-12b", "p0", 999))
    for arm, wrong in (("graph-12b", set()), ("agent-12b", {"p2", "p3"})):
        rows = [{"arm": arm, "id": it.id, "record": None if it.id in wrong else GOOD} for it in ITEMS]
        (src / f"{arm}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (src / "llama-gemma-4-12b.log").write_text("device: the machine's GPU", encoding="utf-8")
    return tmp_path, runs, items


def run_publish(tree, **kw):
    tmp, runs, items = tree
    return publish.publish("r1", runs=runs, results=tmp / "results", items=items, sheet=SHEET, **kw)


def test_publish_copies_what_a_reader_needs_and_nothing_else(tree):
    out = run_publish(tree)
    assert out.arms == ["agent-12b", "graph-12b"]
    names = sorted(p.name for p in out.path.iterdir())
    assert names == ["agent-12b.jsonl", "graph-12b.jsonl", "ledger.jsonl", "meta.json", "report.md", "scores.json"]
    assert {r.run for r in ledger.read([out.path / "ledger.jsonl"])} == {"r1"}, "another run's records stay behind"
    scores = json.loads((out.path / "scores.json").read_text(encoding="utf-8"))
    assert scores["enrich:agent-12b"]["succeeded"] == 2


def test_report_carries_conditions_scores_and_the_paired_comparison(tree):
    md = (run_publish(tree).path / "report.md").read_text(encoding="utf-8")
    assert md.startswith("# Run r1\n\nConditions: limit 4,")
    assert "code abc123def456" in md
    assert "| agent-12b | 4 | 50% |" in md, "the scores table"
    assert "### Graph against agent, item by item" in md
    assert "| graph-12b | agent-12b | 4 | 2 | 0 | +50.0 pts" in md
    assert "| graph-12b | agent-12b | claude-haiku-5-5 | batch | −$" in md, (
        "the graph is cheaper: a negative difference"
    )


def test_index_lists_every_published_run(tree):
    tmp, _, _ = tree
    run_publish(tree)
    index = (tmp / "results" / "README.md").read_text(encoding="utf-8")
    assert "| r1 | 4 | off | 4 | abc123def456 | [report](r1/report.md) |" in index
    assert "Apache-2.0" in index, "the outputs carry the dataset's attribution"


def test_a_run_without_its_code_version_needs_one_given(tree):
    tmp, runs, _ = tree
    meta = {k: v for k, v in META.items() if k != "code"}
    (runs / "r1" / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="no code version"):
        run_publish(tree)
    out = run_publish(tree, code="feedc0ffee12")
    published = json.loads((out.path / "meta.json").read_text(encoding="utf-8"))
    assert published["code"] == "feedc0ffee12" and "recorded at publication" in published["code_note"]
    assert "feedc0ffee12 (recorded at publication)" in (tmp / "results" / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "change,error",
    [
        ({"code": "abc123def456-dirty"}, "uncommitted"),
        ({"code": "unknown"}, "no code version"),
    ],
)
def test_unreproducible_runs_are_refused(tree, change, error):
    _, runs, _ = tree
    (runs / "r1" / "meta.json").write_text(json.dumps(META | change), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        run_publish(tree)


def test_an_arm_without_results_is_refused(tree):
    _, runs, _ = tree
    (runs / "r1" / "agent-12b.jsonl").unlink()
    with pytest.raises(ValueError, match="no results for: agent-12b"):
        run_publish(tree)
