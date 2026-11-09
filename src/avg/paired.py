"""A graph arm against an agent arm, item by item.

Both arms ran the same items, so each item is its own control. Most of the spread in cost is the
items' own (a long listing costs more in every arm); pairing takes it out, so a difference shows
far sooner than by laying two arms' intervals side by side. Success is compared with McNemar's
exact test, since only the items where the arms disagree say which is better; cost with a
bootstrap over the per-item differences.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb

from .project import Projection, project


@dataclass
class Success:
    items: int  # items both arms ran
    a_only: int  # items only the first arm got right
    b_only: int
    diff: Projection  # first arm's success rate minus the second's, per item in {-1, 0, 1}
    p: float  # McNemar's exact two-sided p


def mcnemar(a_only: int, b_only: int) -> float:
    """Two-sided exact p for the discordant pairs: how likely a split this uneven is if neither arm
    is better, when each disagreement is a fair coin."""
    n = a_only + b_only
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(a_only, b_only) + 1))
    return min(1.0, 2 * tail / 2**n)


def _common(a: dict, b: dict) -> list[str]:
    ids = sorted(a.keys() & b.keys())
    if not ids:
        raise ValueError("the arms share no items")
    return ids


def success(a: dict[str, bool], b: dict[str, bool]) -> Success:
    ids = _common(a, b)
    a_only = sum(a[i] and not b[i] for i in ids)
    b_only = sum(b[i] and not a[i] for i in ids)
    diff = project([float(a[i]) - float(b[i]) for i in ids])
    return Success(len(ids), a_only, b_only, diff, mcnemar(a_only, b_only))


def cost(a: dict[str, float], b: dict[str, float]) -> Projection:
    """The first arm's cost per item minus the second's, over the items both ran."""
    ids = _common(a, b)
    return project([a[i] - b[i] for i in ids])


def default_pairs(arms: set[str]) -> list[tuple[str, str]]:
    """Each agent-<model> arm against graph-<model> and its variants (graph-<model>-lean): the same
    model in both shapes."""
    out = []
    for a in sorted(arms):
        if a.startswith("agent-"):
            g = f"graph-{a[6:]}"
            out += [(x, a) for x in sorted(arms) if x == g or x.startswith(g + "-")]
    return out
