"""Scoring results files against the gold answers: a table for people and counts for the report."""

from __future__ import annotations

import json
from pathlib import Path

from .tasks import enrich, intake


def score_files(items_path: Path, results: list[Path]) -> tuple[str, dict]:
    """The scores table, and per arm the items, how many succeeded and which: the report prices
    successes from the counts and pairs arms item by item from `passed`. The task is told by the
    gold: catalog intake's items carry a kind."""
    items = enrich.load(items_path)
    rows: dict[str, dict[str, dict]] = {}
    for path in results:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows.setdefault(r["arm"], {})[r["id"]] = r
    if items and "kind" in items[0].gold:
        return _intake(items, rows)
    return _enrich(items, rows)


def _enrich(items: list[enrich.Item], rows: dict[str, dict[str, dict]]) -> tuple[str, dict]:
    by_id = {it.id: it for it in items}
    table = [
        "| Arm | Items | Valid | Brand | Color | Success |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    out = {}
    for arm, by_item in sorted(rows.items()):
        ss = {i: enrich.score(r.get("record"), by_id[i]) for i, r in by_item.items()}
        n = len(ss)
        colored = [s.color for s in ss.values() if s.color is not None]
        ok = sum(s.success for s in ss.values())
        color = f"{sum(colored) / len(colored):.0%}" if colored else "–"
        table.append(
            f"| {arm} | {n} | {sum(s.valid for s in ss.values()) / n:.0%} | "
            f"{sum(s.brand for s in ss.values()) / n:.0%} | {color} | {ok / n:.0%} |"
        )
        out[f"{enrich.TASK}:{arm}"] = {
            "items": n,
            "succeeded": ok,
            "passed": {i: s.success for i, s in sorted(ss.items())},
        }
    return "\n".join(table) + "\n", out


def _intake(items: list[enrich.Item], rows: dict[str, dict[str, dict]]) -> tuple[str, dict]:
    table = [
        "| Arm | Items | New catalogued | Duplicates skipped | Exclusions skipped | Records for rejects | Success |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    out = {}
    for arm, by_item in sorted(rows.items()):
        mine = [it for it in items if it.id in by_item]
        s = intake.score(mine, by_item)
        share = lambda kinds, s=s: _share([ok for i, ok in s.passed.items() if s.kinds[i] in kinds])
        n, ok = len(mine), sum(s.passed.values())
        table.append(
            f"| {arm} | {n} | {share({'new'})} | {share({'catalog_duplicate', 'feed_duplicate'})} | "
            f"{share({'excluded_brand', 'excluded_kind'})} | {s.records_for_rejects} | {ok / n:.0%} |"
        )
        out[f"{intake.TASK}:{arm}"] = {
            "items": n,
            "succeeded": ok,
            "passed": dict(sorted(s.passed.items())),
            "kinds": dict(sorted(s.kinds.items())),
            "records_for_rejects": s.records_for_rejects,
        }
    return "\n".join(table) + "\n", out


def _share(oks: list[bool]) -> str:
    return f"{sum(oks) / len(oks):.0%}" if oks else "–"
