"""Graph against agent, item by item: the paired success test and the paired cost difference."""

import pytest

from avg import paired


@pytest.mark.parametrize(
    "a_only,b_only,want",
    [
        (0, 0, 1.0),  # no disagreement: no evidence either way
        (0, 5, 2 / 2**5),  # 5 of 5 disagreements one way
        (1, 9, 2 * (1 + 10) / 2**10),
        (9, 1, 2 * (1 + 10) / 2**10),  # symmetric
        (5, 5, 1.0),  # an even split, capped at 1
    ],
)
def test_mcnemar_exact(a_only, b_only, want):
    assert paired.mcnemar(a_only, b_only) == pytest.approx(want)


def test_success_counts_only_disagreements():
    a = {"1": True, "2": True, "3": False, "4": True, "x": True}
    b = {"1": True, "2": False, "3": False, "4": False, "y": False}
    s = paired.success(a, b)
    assert (s.items, s.a_only, s.b_only) == (4, 2, 0), "items only one arm ran are left out"
    assert s.diff.mean == pytest.approx(0.5)
    assert s.p == pytest.approx(0.5)


def test_cost_difference_is_resolved_by_pairing():
    # Item costs spread 1 to 100 in both arms, but the graph is always 1 cheaper: unpaired, the
    # spread would swamp the difference; paired, the interval is exactly -1.
    agent = {str(i): float(i) for i in range(1, 101)}
    graph = {k: v - 1 for k, v in agent.items()}
    d = paired.cost(graph, agent)
    assert (d.mean, d.low, d.high) == pytest.approx((-1.0, -1.0, -1.0))


def test_arms_with_no_items_in_common_are_refused():
    with pytest.raises(ValueError, match="no items"):
        paired.cost({"a": 1.0}, {"b": 1.0})


def test_default_pairs_match_the_model():
    arms = {"graph", "graph-12b", "agent-12b", "agent-e4b", "claude-code"}
    assert paired.default_pairs(arms) == [("graph-12b", "agent-12b")], "graph mixes models: no default partner"
