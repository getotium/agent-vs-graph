"""Scoring results files against the gold answers: a table for people and counts for the report."""

from __future__ import annotations

import json
from pathlib import Path

from .tasks import enrich


def score_files(items_path: Path, results: list[Path]) -> tuple[str, dict]:
    """The scores table, and per arm the items, how many succeeded and which: the report prices
    successes from the counts and pairs arms item by item from `passed`."""
    by_id = {it.id: it for it in enrich.load(items_path)}
    by_arm: dict[str, dict[str, enrich.Score]] = {}
    for path in results:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                by_arm.setdefault(r["arm"], {})[r["id"]] = enrich.score(r.get("record"), by_id[r["id"]])
    rows = [
        "| Arm | Items | Valid | Brand | Color | Success |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    out = {}
    for arm, by_item in sorted(by_arm.items()):
        ss = list(by_item.values())
        n = len(ss)
        colored = [s.color for s in ss if s.color is not None]
        ok = sum(s.success for s in ss)
        color = f"{sum(colored) / len(colored):.0%}" if colored else "–"
        rows.append(
            f"| {arm} | {n} | {sum(s.valid for s in ss) / n:.0%} | {sum(s.brand for s in ss) / n:.0%} | "
            f"{color} | {ok / n:.0%} |"
        )
        out[f"{enrich.TASK}:{arm}"] = {
            "items": n,
            "succeeded": ok,
            "passed": {i: s.success for i, s in sorted(by_item.items())},
        }
    return "\n".join(rows) + "\n", out
