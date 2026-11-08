"""The report: ledger + price sheet → Markdown tables.

Per task and arm: tokens per item, cost per 1,000 items under each chosen price, and the
projection to volume. An arm that is not batchable (an agent, whose turns wait on each other)
is shown at real-time rates only; a batchable one (the graph) at both, so the saving from the
shape of the work and the saving from the batch discount can be read apart.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from . import cache, paired
from .ledger import Record
from .prices import Price
from .project import Projection, project


@dataclass
class Group:
    """One arm's records on one task."""

    task: str
    arm: str
    units: dict[str, list[Record]] = field(default_factory=lambda: defaultdict(list))
    items: int = 0  # documents processed; a unit can be one item or a chunk of many
    # Requests the server refused (status >= 400). Not priced: the server reports no usage for
    # them, though it may have generated before failing. Shown so the gap is visible.
    failed: int = 0

    @property
    def records(self) -> list[Record]:
        return [r for rs in self.units.values() for r in rs]

    def per_item(self, field_: str) -> float:
        return sum(getattr(r, field_) for r in self.records) / self.items

    def billed(self, price: Price) -> tuple[dict[str, list[Record]], int]:
        """The units' records as the price's provider would bill them: its cache rule replayed
        over the recorded prompts (the local server's cache hits are dropped), and how many
        records had no prompt shape to replay. Without a cache rule, every prompt token is new.
        Requests the priced model answered itself are taken as recorded: the vendor counted them,
        cache reads and writes included, and that count is the bill."""
        own = [r for r in self.records if _billed_by(r, price)]
        rest = [r for r in self.records if not _billed_by(r, price)]
        unknown = 0
        if price.cache is None:
            rest = [replace(r, input=r.prompt, cache_read=0, cache_write=0) for r in rest]
        elif rest:
            rest, unknown = cache.replay(rest, price.cache)
        units: dict[str, list[Record]] = defaultdict(list)
        for r in own + rest:
            units[r.item].append(r)
        return units, unknown

    def unit_costs(self, price: Price, batch: bool) -> dict[str, float]:
        """Cost per item by unit: a unit of k items contributes its cost / k."""
        units, _ = self.billed(price)
        per_unit = self.items / len(units)
        return {u: sum(price.cost(r, batch) for r in rs) / per_unit for u, rs in units.items()}

    def item_costs(self, price: Price, batch: bool) -> list[float]:
        return list(self.unit_costs(price, batch).values())

    @property
    def per_item_units(self) -> bool:
        """Whether each unit is one item, so the arm can be paired with another item by item."""
        return self.items == len(self.units)

    def cached_share(self, price: Price) -> float:
        """The share of prompt tokens the provider would have read from its cache."""
        units, _ = self.billed(price)
        recs = [r for rs in units.values() for r in rs]
        prompt = sum(r.prompt for r in recs)
        return sum(r.cache_read for r in recs) / prompt if prompt else 0.0


def _billed_by(r: Record, price: Price) -> bool:
    """Whether the request was answered by the priced model itself, so its recorded usage is the
    vendor's own bill rather than a local model's tokens to be priced as if."""
    return r.model == price.id or r.model.startswith(price.id + "-")


def group(records: Iterable[Record], items: dict[tuple[str, str], int] | None = None) -> list[Group]:
    """Records grouped by (task, arm). `items` gives the document count for an arm whose units
    are not one document each (an agent handed the whole file); otherwise each distinct item
    label is one document."""
    gs: dict[tuple[str, str], Group] = {}
    runs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in records:
        g = gs.setdefault((r.task, r.arm), Group(r.task, r.arm))
        if r.status >= 400:
            g.failed += 1  # a refused request is a failure to report, not a priced cost
            continue
        g.units[r.item].append(r)
        runs[(r.task, r.arm)].add(r.run)
    mixed = {f"{t}:{a}": sorted(rs) for (t, a), rs in runs.items() if len(rs) > 1}
    if mixed:
        # The same items run twice would be counted as one arm's units and their costs summed.
        raise ValueError(f"an arm appears in more than one run, pick one with --run: {mixed}")
    for key, g in gs.items():
        g.items = (items or {}).get(key, len(g.units))
    # An arm whose every request was refused has nothing to price.
    return sorted((g for g in gs.values() if g.units), key=lambda g: (g.task, g.arm))


def _usd(x: float) -> str:
    if x == 0:
        return "$0"
    if x < 0.01:
        return f"${x:.4f}"
    if x < 1000:
        return f"${x:,.2f}"
    return f"${x:,.0f}"


def _modes(arm: str, price: Price, batchable: set[str]) -> list[bool]:
    modes = [False, True] if arm in batchable else [False]
    return [b for b in modes if price.can(b)]


def _signed_usd(x: float) -> str:
    return ("−" if x < 0 else "+") + _usd(abs(x))


def _pct(x: float) -> str:
    return f"{x * 100:+.1f} pts"


def _about(text: str, guide: str, anchor: str) -> list[str]:
    """One plain sentence on what the next table shows, and where its columns are defined."""
    return [text + (f" Columns: [reading a report]({guide}#{anchor})." if guide else ""), ""]


def _paired(
    tg: list[Group],
    prices: list[Price],
    batchable: set[str],
    passed: dict[tuple[str, str], dict[str, bool]],
    pairs: list[tuple[str, str]],
    guide: str = "",
) -> list[str]:
    """The graph-against-agent tables for one task: success, then cost under each price."""
    by_arm = {g.arm: g for g in tg}
    task = tg[0].task
    usable = [(a, b) for a, b in pairs if a in by_arm and b in by_arm
              and by_arm[a].per_item_units and by_arm[b].per_item_units]  # fmt: skip
    if not usable:
        return []
    out = ["### Graph against agent, item by item", ""]
    out += _about("Each graph arm next to the agent on the same model, so the two differ only in shape, compared on "
                  "the items both ran.", guide, "graph-against-agent-item-by-item")  # fmt: skip
    scored = [(a, b) for a, b in usable if (task, a) in passed and (task, b) in passed]
    if scored:
        out += [
            "| Graph | Agent | Items | Only graph right | Only agent right | Success, graph − agent | p |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for a, b in scored:
            s = paired.success(passed[(task, a)], passed[(task, b)])
            out.append(
                f"| {a} | {b} | {s.items:,} | {s.a_only:,} | {s.b_only:,} | {_pct(s.diff.mean)} "
                f"({_pct(s.diff.low)} to {_pct(s.diff.high)}) | {s.p:.2g} |"
            )
        out += [
            "",
            "p is McNemar's exact test on the items where the arms disagree: how likely a split this",
            "uneven would be if neither arm were better.",
            "",
        ]
    out += [
        "| Graph | Agent | Priced as | Graph mode | Graph − agent, per 1,000 items | Relative |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for a, b in usable:
        for price in prices:
            if not price.can(False):
                continue  # the agent has only a real-time price to compare against
            agent = by_arm[b].unit_costs(price, False)
            base = sum(agent.values()) / len(agent)
            for batch in _modes(a, price, batchable):
                d = paired.cost(by_arm[a].unit_costs(price, batch), agent)
                rel = f"{d.mean / base:+.0%}" if base else "–"
                out.append(
                    f"| {a} | {b} | {price.id} | {'batch' if batch else 'real-time'} | {_signed_usd(d.mean * 1000)} "
                    f"({_signed_usd(d.low * 1000)} to {_signed_usd(d.high * 1000)}) | {rel} |"
                )
    out += ["", "The agent is priced real-time throughout; negative means the graph costs less.", ""]
    return out


def render(
    groups: list[Group],
    prices: list[Price],
    batchable: set[str],
    volumes: list[int],
    title: str = "Results",
    success: dict[tuple[str, str], float] | None = None,
    passed: dict[tuple[str, str], dict[str, bool]] | None = None,
    pairs: list[tuple[str, str]] | None = None,
    guide: str = "",
) -> str:
    """`success` is each (task, arm)'s success rate from `avg score`; with it, each row also shows
    the cost per 1,000 successful items, so an arm cannot look cheap by failing. `pairs` are
    (graph, agent) arms to compare item by item, on success too when `passed` has both arms'
    per-item results. `guide` is a link to docs/reading-reports.md from where the report will be
    read; with it, each table links to its column definitions."""
    success = success or {}
    out: list[str] = [f"# {title}", ""]
    for task in sorted({g.task for g in groups}):
        tg = [g for g in groups if g.task == task]
        out += [f"## Task: {task}", "", "### Tokens per item", ""]
        out += _about("What each arm sent to the model and got back, per item, counted at the wire.", guide,
                      "tokens-per-item")  # fmt: skip
        out += [
            "| Arm | Items | Requests / item | Prompt | Output | Refused requests |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for g in tg:
            out.append(
                f"| {g.arm} | {g.items:,} | {len(g.records) / g.items:,.1f} | {g.per_item('prompt'):,.0f} | "
                f"{g.per_item('output'):,.0f} | {g.failed:,} |"
            )
        out += [
            "",
            "Prompt counts every input token. What a provider would have served from its cache is",
            "replayed from the recorded prompts under each price's own cache rule, below. Refused",
            "requests are not priced: the server reports no usage for them.",
            "",
        ]

        for price in prices:
            if not any(_modes(g.arm, price, batchable) for g in tg):
                continue  # e.g. a batch-only price and no batchable arm on this task
            out += [f"### Priced as {price.id} ({price.vendor})", ""]
            out += _about(f"What the run's tokens would cost at {price.vendor}'s published prices for {price.id}, per "
                          "item and projected to monthly volumes.", guide, "price-tables")  # fmt: skip
            vol_cols = " | ".join(f"{v:,} / month" for v in volumes)
            out += [
                (
                    f"| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | {vol_cols} "
                    f"| Year at {volumes[-1]:,} / month |"
                ),
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | " + " | ".join("---:" for _ in volumes) + " | ---: |",
            ]
            for g in tg:
                for batch in _modes(g.arm, price, batchable):
                    p: Projection = project(g.item_costs(price, batch))
                    cells = []
                    for v in volumes:
                        est, lo, hi = p.at(v)
                        cells.append(f"{_usd(est)} ({_usd(lo)}–{_usd(hi)})" if p.items > 1 else _usd(est))
                    year = p.at(volumes[-1])[0] * 12
                    rate = success.get((g.task, g.arm))
                    ok = "–" if rate is None else f"{rate:.0%}"
                    per_ok = "–" if not rate else _usd(p.mean * 1000 / rate)
                    out.append(
                        f"| {g.arm} | {'batch' if batch else 'real-time'} | {g.cached_share(price):.0%} | {ok} | "
                        f"{_usd(p.mean * 1000)} | "
                        f"{per_ok} | {_usd(p.p95)} | {' | '.join(cells)} | {_usd(year)} |"
                    )
            src = f"Rates from {price.source}, checked {price.checked}."
            if price.cache:
                c = price.cache
                how = (
                    "every prefix it sees"
                    if c.mode == "auto"
                    else "prefixes marked where a later request reuses them (the best case)"
                )
                src += (f" Cache replayed as {price.vendor}'s: {how}, from {c.min_tokens:,} tokens, "
                        f"{c.ttl_s / 60:g}-minute lifetime.")  # fmt: skip
            else:
                src += " No prompt cache."
            own = sum(_billed_by(r, price) for g in tg for r in g.records)
            if own:
                src += (f" {own:,} requests were answered by {price.id} itself and are priced as {price.vendor} "
                        "counted them, cache included, not replayed.")  # fmt: skip
            unknown = sum(g.billed(price)[1] for g in tg)
            if unknown:
                src += f" {unknown:,} requests had no recorded prompt shape and are priced as all new input."
            if price.verify:
                src += f" **Unverified:** {price.verify}"
            out += ["", src, ""]
        out += _paired(tg, prices, batchable, passed or {}, pairs or [], guide)
        not_batch = sorted({g.arm for g in tg} - batchable)
        if not_batch:
            out += [
                f"Arms shown at real-time rates only, because their requests wait on each other: {', '.join(not_batch)}.",
                "",
            ]
    out += [
        "Ranges are a 90% bootstrap interval on the mean cost per item: how sure the sample makes us of",
        "the average, not how much a real month will vary.",
        "",
    ]
    return "\n".join(out)
