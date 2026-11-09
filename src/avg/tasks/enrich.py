"""Task 1, product enrichment: a messy catalog listing in, a validated JSON record out.

The reference workload behind the benchmark (a catalog enriched record by record), on public
data: Amazon's Shopping Queries (ESCI) product catalog, Apache-2.0. Each item's listing has a
title, bullet points and a description; the catalog's own brand and color fields are kept aside
as gold and never shown to any arm.

Every arm writes the same record, checked by the same validator and scored the same way:

    category     one of CATEGORIES
    brand        the maker's brand, or null when the listing does not say
    color        the main color, or null when it has none or does not say
    specs        1 to 8 short key → value facts from the listing (size, material, count...)
    description  a plain description, 15 to 60 words, nothing the listing does not support

An item **succeeds** when its final record is valid and its brand matches the catalog's.
Color is scored too, but reported apart: the catalog's color field is too loose ("A-black",
"Multi") to gate success on.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .. import agent
from ..llm import Client, ModelError, parse_json
from .record import MAX_WORDS, MIN_WORDS, RECORD_SPEC, listing_text, validate

TASK = "enrich"


@dataclass
class Item:
    id: str
    title: str
    bullets: str
    description: str
    gold: dict  # brand, color: the catalog's own fields, never shown to an arm

    def listing(self) -> str:
        """The listing as every arm sees it."""
        parts = [f"Title: {self.title}"]
        if self.bullets:
            parts.append(f"Bullet points:\n{self.bullets}")
        if self.description:
            parts.append(f"Description: {self.description}")
        return "\n\n".join(parts)

    def public(self) -> dict:
        return {"id": self.id, "title": self.title, "bullets": self.bullets, "description": self.description}

    def check(self, record: object, partial: bool = False) -> list[str]:
        """The shared validator, with this listing to check copying against."""
        return validate(record, partial, listing_text(self.public()))


def load(path) -> list[Item]:
    with open(path, encoding="utf-8") as f:
        return [Item(**json.loads(line)) for line in f if line.strip()]


# ---- scoring ------------------------------------------------------------------------------------


def _norm(s: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower()) if s else ""


def matches(got: object, gold: object) -> bool:
    """Lenient match: equal once case, spaces and punctuation are dropped, or one contains the
    other ("Samsung" against "SAMSUNG Electronics"). Short strings must match exactly."""
    a, b = _norm(got), _norm(gold)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 3 and short in long_


@dataclass
class Score:
    valid: bool
    brand: bool
    color: bool | None  # None: the catalog has no color to check against

    @property
    def success(self) -> bool:
        return self.valid and self.brand


def score(record: dict | None, item: Item) -> Score:
    gold = item.gold
    if record is None:
        return Score(False, False, None if not gold.get("color") else False)
    color = None if not gold.get("color") else matches(record.get("color"), gold["color"])
    return Score(not item.check(record), matches(record.get("brand"), gold.get("brand")), color)


# ---- the graph ----------------------------------------------------------------------------------

EXTRACT = f"""You turn a product listing into catalog attributes. Reply with one JSON object and
nothing else: the keys "category", "brand", "color" and "specs" as described below (no description).

{RECORD_SPEC}"""

REPAIR = f"""You fix a product record that failed validation. Reply with the corrected JSON object
and nothing else, keeping what was right.

{RECORD_SPEC}"""

DESCRIBE = f"""You write the description for a product record: {MIN_WORDS} to {MAX_WORDS} words, plain
and factual, in your own words rather than the listing's, claiming nothing the listing does not
support. Reply with the description text only."""


@dataclass
class Models:
    small: str
    large: str


async def _gather(limit: int, coros: Iterable):
    """Run a step over every item at once, at most `limit` in flight (the server's slots)."""
    sem = asyncio.Semaphore(limit)

    async def one(c):
        async with sem:
            return await c

    return await asyncio.gather(*(one(c) for c in coros))


# The graph's model steps, by the names `graph(no_thinking=...)` takes.
STEPS = ("extract", "repair", "describe")


async def graph(
    client: Client,
    arm: str,
    items: list[Item],
    models: Models,
    limit: int = 4,
    reasons: dict | None = None,
    no_thinking: frozenset[str] = frozenset(),
) -> dict[str, dict]:
    """extract (small) → validate (code) → repair the failures (large) → describe (small) →
    validate → repair the failures again (large). Each step runs over every item before the
    next starts, which is what lets every model step be one batch. Returns id → record for the
    items that came out valid; `reasons`, if given, gets why each other item dropped out.
    Steps named in `no_thinking` run with thinking off whatever the run's condition."""
    if unknown := no_thinking - set(STEPS):
        raise ValueError(f"no such graph step: {', '.join(sorted(unknown))}")
    think = {s: s not in no_thinking for s in STEPS}

    async def extract(it: Item):
        msg = [{"role": "system", "content": EXTRACT}, {"role": "user", "content": it.listing()}]
        return parse_json(
            (await client.chat(arm, TASK, it.id, models.small, msg, think=think["extract"])).get("content")
        )

    async def repair(it: Item, record, errors: list[str]):
        msg = [
            {"role": "system", "content": REPAIR},
            {"role": "user", "content": f"{it.listing()}\n\nRecord:\n{json.dumps(record)}\n\nErrors:\n"
                                        + "\n".join(f"- {e}" for e in errors)},
        ]  # fmt: skip
        return parse_json(
            (await client.chat(arm, TASK, it.id, models.large, msg, think=think["repair"])).get("content")
        )

    async def describe(it: Item, record: dict):
        attrs = {k: record.get(k) for k in ("category", "brand", "color", "specs")}
        msg = [
            {"role": "system", "content": DESCRIBE},
            {"role": "user", "content": f"{it.listing()}\n\nAttributes:\n{json.dumps(attrs)}"},
        ]
        reply = await client.chat(arm, TASK, it.id, models.small, msg, think=think["describe"])
        return (reply.get("content") or "").strip()

    by_id = {it.id: it for it in items}
    records: dict[str, object] = dict(
        zip(by_id, await _gather(limit, (_safe(extract(it)) for it in items)), strict=True)
    )
    await _repair_pass(limit, by_id, records, repair, partial=True)

    ready = [i for i, r in records.items() if i in by_id and not by_id[i].check(r, partial=True)]
    texts = await _gather(limit, (_safe(describe(by_id[i], records[i])) for i in ready))
    for i, text in zip(ready, texts, strict=True):
        records[i] = {**records[i], "description": text}
    await _repair_pass(limit, {i: by_id[i] for i in ready}, records, repair, partial=False)
    out = {i: r for i, r in records.items() if i in by_id and isinstance(r, dict) and not by_id[i].check(r)}
    if reasons is not None:
        done = set(ready)
        for i, it in by_id.items():
            if i in out:
                continue
            if records.get(i) is None:
                reasons[i] = "attributes: no usable reply"
            elif i not in done:
                reasons[i] = "attributes: " + "; ".join(it.check(records[i], partial=True))
            else:
                reasons[i] = "description: " + "; ".join(it.check(records[i]))
    return out


async def _repair_pass(limit, items: dict[str, Item], records: dict, repair, partial: bool) -> None:
    failed = {i: it.check(records.get(i), partial) for i, it in items.items()}
    failed = {i: e for i, e in failed.items() if e}
    fixed = await _gather(limit, (_safe(repair(items[i], records.get(i), e)) for i, e in failed.items()))
    for i, r in zip(failed, fixed, strict=True):
        if r is not None:
            records[i] = r


async def _safe(coro):
    """A failed request leaves that item without a record; it does not stop the step."""
    try:
        return await coro
    except ModelError:
        return None


# ---- the per-item agent -------------------------------------------------------------------------

AGENT = f"""You enrich product listings for a catalog. Write the record for the product you are
given, check it with validate_record, fix whatever it reports, and finish by calling submit_record
with the valid record. submit_record refuses an invalid record.

{RECORD_SPEC}"""

_RECORD_ARG = {"type": "object", "description": "the record, as described in the instructions"}


def tools(submitted: dict[str, dict], item: Item) -> list[agent.Tool]:
    """The tools the per-item agent gets. The same validator the graph runs."""

    async def validate_record(record: object = None) -> str:
        errs = item.check(record)
        return json.dumps({"valid": not errs, "errors": errs})

    async def submit_record(record: object = None) -> str | agent.Done:
        errs = item.check(record)
        if errs:
            return json.dumps({"accepted": False, "errors": errs})
        submitted[item.id] = record  # type: ignore[assignment]
        return agent.Done(json.dumps({"accepted": True}), record)

    params = {"type": "object", "properties": {"record": _RECORD_ARG}, "required": ["record"]}
    return [
        agent.Tool("validate_record", "Check a record; returns whether it is valid and what is wrong.", params,
                   validate_record),
        agent.Tool("submit_record", "Submit the finished, valid record. Ends the task.", params, submit_record),
    ]  # fmt: skip


async def agents(
    client: Client,
    arm: str,
    items: list[Item],
    model: str,
    limit: int = 4,
    max_turns: int = 8,
    on_done: Callable[[Item, agent.Outcome, dict | None], None] | None = None,
) -> tuple[dict[str, dict], dict[str, agent.Outcome]]:
    """One agent per item, `limit` at a time. The listing is in the first message, as an agent
    builder would write it: no turn is spent fetching it. `on_done` hears of each item as it
    finishes, so a run that breaks part way keeps what it finished."""
    submitted: dict[str, dict] = {}

    async def one(it: Item) -> agent.Outcome:
        user = f"Product {it.id}:\n\n{it.listing()}"
        try:
            o = await agent.run(client, arm, TASK, it.id, model, AGENT, user, tools(submitted, it), max_turns)
        except ModelError as e:
            o = agent.Outcome(False, reason=f"model error: {e}")
        if on_done:
            on_done(it, o, submitted.get(it.id))
        return o

    outcomes = await _gather(limit, (one(it) for it in items))
    return submitted, {it.id: o for it, o in zip(items, outcomes, strict=True)}
