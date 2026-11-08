"""Prices, projection and the report, from hand-built ledgers whose costs can be worked by hand."""

from pathlib import Path

import pytest

from avg import prices, report
from avg.ledger import Record
from avg.project import project, quantile

SHEET = Path(__file__).parent.parent / "prices" / "default.yaml"


def rec(item="a", arm="graph", task="t", input=0, cache_read=0, cache_write=0, output=0, status=200):
    return Record(
        run="r", arm=arm, task=task, item=item, wire="anthropic", model="m",
        input=input, cache_read=cache_read, cache_write=cache_write, output=output,
        latency_ms=1, status=status,
    )  # fmt: skip


@pytest.fixture(scope="module")
def sheet():
    return prices.load(SHEET)


def test_sheet_entries_are_sourced(sheet):
    assert {"claude-haiku-5-5", "gpt-6-luna", "otium-small"} <= set(sheet)
    for p in sheet.values():
        assert p.source.startswith("https://") and p.checked


def test_cost_by_token_class(sheet):
    haiku = sheet["claude-haiku-5-5"]
    r = rec(input=1_000_000, cache_read=1_000_000, cache_write=1_000_000, output=1_000_000)
    # 3M prompt tokens is over the 100K line, so every class pays the long-prompt rate.
    assert haiku.cost(r, batch=False) == pytest.approx(0.50 + 0.05 + 0.625 + 2.50)
    short = rec(input=50_000, cache_read=40_000, output=10_000)
    assert haiku.cost(short, batch=False) == pytest.approx((50_000 * 0.10 + 40_000 * 0.01 + 10_000 * 0.50) / 1e6)
    assert haiku.cost(short, batch=True) == pytest.approx(haiku.cost(short, batch=False) / 2)


def test_long_prompt_line_is_strict(sheet):
    haiku = sheet["claude-haiku-5-5"]
    at = rec(input=100_000)
    over = rec(input=100_001)
    assert haiku.cost(at, False) == pytest.approx(100_000 * 0.10 / 1e6)
    assert haiku.cost(over, False) == pytest.approx(100_001 * 0.50 / 1e6)


def test_batch_only_price_has_no_real_time(sheet):
    otium = sheet["otium-small"]
    r = rec(input=1_000_000, cache_read=1_000_000, output=1_000_000)
    assert otium.cost(r, batch=True) == pytest.approx(0.048 + 0 + 0.24), "cached input is free"
    assert not otium.can(batch=False)
    with pytest.raises(ValueError):
        otium.cost(r, batch=False)


def test_load_rejects_an_unsourced_price(tmp_path):
    bad = tmp_path / "p.yaml"
    bad.write_text("prices:\n  - {id: x, vendor: v, checked: 2026-01-01, input: 1, output: 1}\n")
    with pytest.raises(ValueError, match="source"):
        prices.load(bad)


def test_projection():
    p = project([1.0, 1.0, 1.0, 5.0])
    assert p.mean == 2.0 and p.max == 5.0
    assert p.low <= p.mean <= p.high
    assert p.at(100_000)[0] == pytest.approx(200_000)
    assert project([1.0, 1.0, 1.0, 5.0]) == p, "seeded: the same sample projects the same"
    single = project([3.0])
    assert (single.low, single.high) == (3.0, 3.0)
    with pytest.raises(ValueError):
        project([])


def test_quantile():
    assert quantile([1, 2, 3, 4, 5], 0.5) == 3
    assert quantile([0, 10], 0.95) == pytest.approx(9.5)


def test_group_counts_items_and_skips_failures():
    recs = [
        rec("a", input=100), rec("a", input=100), rec("b", input=300),
        rec("c", status=500, input=10_000),
        rec("chunk-1", arm="agent-file", input=1_000), rec("chunk-2", arm="agent-file", input=3_000),
    ]  # fmt: skip
    gs = {g.arm: g for g in report.group(recs, items={("t", "agent-file"): 10})}
    assert gs["graph"].items == 2, "a failed request is not an item"
    assert gs["graph"].failed == 1, "but it is counted"
    assert gs["graph"].per_item("input") == 250
    assert gs["agent-file"].items == 10
    assert gs["agent-file"].per_item("input") == 400


def test_an_arm_from_two_runs_is_refused():
    from dataclasses import replace

    recs = [rec("a", input=100), replace(rec("a", input=100), run="r2"), replace(rec("a", arm="agent"), run="r2")]
    with pytest.raises(ValueError, match="t:graph"):
        report.group(recs)
    assert len(report.group(recs[1:])) == 2, "different arms from different runs are fine"


def test_item_costs_split_chunks(sheet):
    haiku = sheet["claude-haiku-5-5"]
    recs = [rec("chunk-1", arm="agent-file", input=1_000_000), rec("chunk-2", arm="agent-file", input=0)]
    [g] = report.group(recs, items={("t", "agent-file"): 4})
    # Two chunks of two items: the first chunk's $0.50 (long prompt) is $0.25 an item.
    assert g.item_costs(haiku, batch=False) == pytest.approx([0.25, 0.0])


def test_render(sheet):
    recs = [rec("a", input=1_000, output=100), rec("b", input=3_000, output=300)]
    recs += [rec("a", arm="agent", input=10_000, cache_read=20_000, output=500)]
    md = report.render(
        report.group(recs), [sheet["claude-haiku-5-5"], sheet["otium-small"]], {"graph"}, [100_000], "Dry run"
    )
    assert md.startswith("# Dry run")
    assert "| graph | 2 | 1.0 | 2,000 |" in md
    assert "| graph | batch |" in md and "| agent | batch |" not in md, "an agent is never priced as a batch"
    assert "| agent | real-time |" in md
    assert "otium-small" in md and "| graph | real-time |" in md
    otium_rows = md.split("Priced as otium-small")[1]
    assert "real-time" not in otium_rows.split("Rates from")[0], "Otium has no real-time price"
    assert "real-time rates only" in md


def test_cli_report(tmp_path, capsys):
    from avg import cli, ledger

    path = tmp_path / "ledger.jsonl"
    for r in [rec("a", input=1_000), rec("chunk-1", arm="agent-file", input=9_000)]:
        ledger.append(path, r)
    assert cli.main(["report", str(path), "--prices", str(SHEET), "--price-as", "claude-haiku-5-5",
                     "--items", "t:agent-file=3", "--volume", "100000"]) == 0  # fmt: skip
    out = capsys.readouterr().out
    assert "| agent-file | 3 | 0.3 | 3,000 |" in out
    assert "Priced as claude-haiku-5-5" in out and "otium-small" not in out


def test_render_cost_per_success(sheet):
    recs = [rec("a", input=1_000_000 // 10), rec("b", input=1_000_000 // 10)]
    md = report.render(report.group(recs), [sheet["claude-haiku-5-5"]], set(), [1_000], success={("t", "graph"): 0.5})
    # $0.01 an item at $0.10/M; half the items succeed, so $20 per 1,000 successes.
    assert "| graph | real-time | 0% | 50% | $10.00 | $20.00 |" in md
    assert "| graph | real-time | 0% | – | $10.00 | – |" in report.render(report.group(recs), [sheet["claude-haiku-5-5"]],
                                                                   set(), [1_000])  # fmt: skip


def test_cli_report_filters_runs_and_batches_every_graph_arm(tmp_path, capsys):
    from avg import cli, ledger

    path = tmp_path / "ledger.jsonl"
    old = rec("a", arm="graph-12b", input=1_000)
    old.run = "old"
    for r in [rec("a", arm="graph-12b", input=2_000), old, rec("a", arm="agent", input=1_000)]:
        ledger.append(path, r)
    assert cli.main(["report", str(path), "--prices", str(SHEET), "--price-as", "claude-haiku-5-5", "--run", "r"]) == 0
    out = capsys.readouterr().out
    assert "| graph-12b | 1 | 1.0 | 2,000 |" in out, "the old run is left out"
    assert "| graph-12b | batch |" in out and "| agent | batch |" not in out


def test_a_cache_rate_needs_a_cache_rule(tmp_path):
    bad = tmp_path / "p.yaml"
    bad.write_text("prices:\n  - {id: x, vendor: V, source: https://v, checked: 2026-01-01, input: 1, output: 2, "
                   "cache_read: 0.1}\n", encoding="utf-8")  # fmt: skip
    with pytest.raises(ValueError, match="cache rule"):
        prices.load(bad)


def test_the_local_servers_cache_hits_are_not_priced(sheet):
    """A record with llama.cpp's cache hits but no prompt shape is billed as all new input."""
    [g] = report.group([rec("a", input=100, cache_read=900)])
    units, unknown = g.billed(sheet["claude-haiku-5-5"])
    assert unknown == 1 and units["a"][0].input == 1_000 and units["a"][0].cache_read == 0
