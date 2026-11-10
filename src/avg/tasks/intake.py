"""Task 2, catalog intake: task 1 with rejects. A supplier's feed in; a record and page content out
for the products the store should take, a skip for the rest (docs/design.md, "Catalog intake").

Every item is new, a duplicate of a catalog entry, a duplicate of another listing in the same feed,
of an excluded brand, or of the excluded kind (a book). Finding out takes reading the listing: the
brand, the model and the kind of product come first, and only then can the item be checked against
the store's rules and catalog. Only kept items get the content, the expensive part.

A result row is {"arm", "id", "record", "skip"}: a record for a catalogued item, or skip set to
"duplicate" or "excluded".
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import agent
from ..llm import Client, ModelError
from .enrich import Item, Models, _gather, _safe, matches, parse_json
from .record import CONTENT_KEYS, CONTENT_SPEC, RECORD_SPEC, listing_text, validate

TASK = "intake"
KINDS = ("new", "catalog_duplicate", "feed_duplicate", "excluded_brand", "excluded_kind")
SKIPS = ("duplicate", "excluded")
BOOKS = "Books & Media"  # the category a book is given; the store does not sell books
ROUNDS = 3  # validate-and-fix rounds, as in task 1's graph
CANDIDATES = 3  # catalog or feed entries of the same brand sent to one compare step


def paths(items: Path) -> tuple[Path, Path]:
    """A mix's catalog and the shared policy, beside its items: items-20.jsonl → catalog-20.jsonl."""
    return items.with_name(items.name.replace("items-", "catalog-")), items.with_name("policy.json")


def load_catalog(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_policy(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rules(policy: dict) -> str:
    """The store's rules, as every arm is told them."""
    return f"""The store's rules:
- It does not sell books (printed or audio). A book is categorized "{BOOKS}".
- It does not sell any product of these brands: {", ".join(policy["excluded_brands"])}.
- A product already in the store's catalog is a duplicate: same brand, same product, same variant \
(color, size, count). Another product of the same brand is not a duplicate.
- A second listing of a product already taken from the same feed is a duplicate too."""


def norm(s: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower()) if s else ""


def same_brand(a: object, b: object) -> bool:
    """Equal, or one contains the other ("P PURLOVE" and "PURLOVE"): the agent's catalog lookup's
    rule, given to the gated graph."""
    x, y = norm(a), norm(b)
    return bool(x and y) and (x == y or (min(len(x), len(y)) >= 3 and (x in y or y in x)))


def check(record: object, it: Item) -> list[str]:
    """The shared validator for a full intake record: task 1's record plus its page content."""
    return validate(record, listing=listing_text(it.public()), content=True)


# ---- scoring ------------------------------------------------------------------------------------


@dataclass
class Scores:
    passed: dict[str, bool]  # id → success
    kinds: dict[str, str]  # id → kind
    records_for_rejects: int  # records written for items that should have been skipped


def score(items: list[Item], rows: dict[str, dict]) -> Scores:
    """A reject succeeds if it was skipped; a new item if it has a valid record with the right brand.
    A product listed several times in the feed succeeds, for every listing, if exactly one listing
    has a valid record with the right brand."""
    passed, kinds, wasted = {}, {}, 0
    groups: dict[str, list[Item]] = {}
    for it in items:
        kinds[it.id] = it.gold["kind"]
        if "group" in it.gold:
            groups.setdefault(it.gold["group"], []).append(it)
    good = lambda it, r: r is not None and not check(r, it) and matches(r.get("brand"), it.gold["brand"])
    for it in items:
        row = rows.get(it.id) or {}
        record = row.get("record")
        if it.gold["kind"] == "feed_duplicate" or "group" in it.gold:
            continue
        if it.gold["kind"] == "new":
            passed[it.id] = good(it, record)
        else:
            passed[it.id] = record is None and row.get("skip") in SKIPS
            wasted += record is not None
    for members in groups.values():
        records = [(m, (rows.get(m.id) or {}).get("record")) for m in members]
        written = [(m, r) for m, r in records if r is not None]
        ok = len(written) == 1 and good(*written[0])
        wasted += max(0, len(written) - 1)
        for m in members:
            passed[m.id] = ok
    return Scores(passed, kinds, wasted)


# ---- the graph ----------------------------------------------------------------------------------

SORT = """You sort a product listing before anything else is done with it. Reply with one JSON object
and nothing else, with the keys "brand": the product's brand as the listing gives it, or null;
"book": true if the product is a book (printed or audio), otherwise false; and "model": its model
or part number as a string, or null if the listing gives none."""

EXTRACT = f"""You turn a product listing into catalog attributes. Reply with one JSON object and
nothing else: the keys "category", "brand", "color" and "specs" as described below (no description),
and "model": the product's model or part number as a string, or null if the listing gives none.

{RECORD_SPEC}"""

REPAIR = f"""You fix a product record that failed validation. Reply with the corrected JSON object
and nothing else, keeping what was right.

{RECORD_SPEC}

{CONTENT_SPEC}"""

COMPARE = """You decide whether a new listing is a product the store already has. Below it are
numbered products of the same brand. Reply with the number of the one that is the same product
(same model and the same variant: color, size, count), or 0 if none is. Reply with the number only."""

WRITE = f"""You write a product's description and its page content from its listing and its
attributes. Reply with one JSON object and nothing else, with the keys "description" (as below),
"seo_title", "meta_description" and "long_description".

- "description": a plain product description of 15 to 60 words, in your own words.

{CONTENT_SPEC}"""

_WRITTEN = ("description", *sorted(CONTENT_KEYS))


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _rank(title: str, candidates: list[dict]) -> list[dict]:
    """Same-brand entries, most shared title words first, at most CANDIDATES."""
    mine = _words(title)
    score = lambda c: len(mine & _words(c["title"])) / (len(mine | _words(c["title"])) or 1)
    return sorted(candidates, key=score, reverse=True)[:CANDIDATES]


async def graph(
    client: Client,
    arm: str,
    items: list[Item],
    models: Models,
    catalog: list[dict],
    policy: dict,
    limit: int = 4,
    gate: bool = False,
) -> dict[str, dict]:
    """extract (small) → the rules, in code: an excluded brand or a book stops here → repair what is
    still invalid (large) → match the catalog and the rest of the feed: same-brand entries ranked by
    shared title words, the top few to one compare step (small) → write the content (small) for what
    is left → validate and fix, up to ROUNDS rounds. Every step runs over every item first, so the
    feed match sees the whole feed. Returns id → {"record": ...} or {"skip": ...}.

    `gate` is the graph's one round of tuning (docs/design.md, "Catalog intake"): a sort step
    (small, thinking off) reads only the brand, whether it is a book and the model; the rules and
    the match run on that, so a reject stops before the full extract; and brands match as
    `same_brand`, not only when equal."""
    by_id = {it.id: it for it in items}
    excluded = [norm(b) for b in policy["excluded_brands"]]
    out: dict[str, dict] = {}

    def excluded_brand(brand: object) -> bool:
        return any(same_brand(brand, e) for e in excluded) if gate else norm(brand) in excluded

    async def sort(it: Item):
        msg = [{"role": "system", "content": SORT}, {"role": "user", "content": it.listing()}]
        return parse_json((await client.chat(arm, TASK, it.id, models.small, msg, think=False)).get("content"))

    async def extract(it: Item):
        msg = [{"role": "system", "content": EXTRACT}, {"role": "user", "content": it.listing()}]
        return parse_json((await client.chat(arm, TASK, it.id, models.small, msg)).get("content"))

    async def repair(it: Item, record, errors: list[str]):
        msg = [
            {"role": "system", "content": REPAIR},
            {"role": "user", "content": f"{it.listing()}\n\nRecord:\n{json.dumps(record)}\n\nErrors:\n"
                                        + "\n".join(f"- {e}" for e in errors)},
        ]  # fmt: skip
        return parse_json((await client.chat(arm, TASK, it.id, models.large, msg)).get("content"))

    async def compare(it: Item, candidates: list[dict]) -> dict | None:
        numbered = "\n".join(f"{k}. {c['brand']}: {c['title']} (color: {c.get('color') or 'none'})"
                             for k, c in enumerate(candidates, 1))  # fmt: skip
        msg = [{"role": "system", "content": COMPARE},
               {"role": "user", "content": f"New listing:\n{it.listing()}\n\nProducts:\n{numbered}"}]  # fmt: skip
        m = re.search(r"\d+", (await client.chat(arm, TASK, it.id, models.small, msg)).get("content") or "")
        k = int(m.group()) if m else 0
        return candidates[k - 1] if 1 <= k <= len(candidates) else None

    async def write(it: Item, record: dict, errors: list[str] | None = None):
        attrs = {k: record.get(k) for k in ("category", "brand", "color", "specs")}
        user = f"{it.listing()}\n\nAttributes:\n{json.dumps(attrs)}"
        if errors:
            last = {k: record.get(k) for k in _WRITTEN}
            user += f"\n\nYour last version was:\n{json.dumps(last)}\n\nIt failed because:\n"
            user += "\n".join(f"- {e}" for e in errors)
        msg = [{"role": "system", "content": WRITE}, {"role": "user", "content": user}]
        got = parse_json((await client.chat(arm, TASK, it.id, models.small, msg)).get("content")) or {}
        return {**attrs, **{k: got.get(k) for k in _WRITTEN}}

    async def fix(it: Item, record, errors: list[str]):
        # Content faults alone are written again by the writer; anything else is repaired.
        if isinstance(record, dict) and all(e.split(" ", 1)[0] in _WRITTEN for e in errors):
            return await write(it, record, errors)
        return await repair(it, record, errors)

    def ruled_out(record) -> bool:
        return isinstance(record, dict) and (excluded_brand(record.get("brand")) or record.get("category") == BOOKS)

    # Match: catalog entries and earlier listings in the feed of the same brand.
    known = list(catalog)

    async def match(survivors: list[Item], seen: dict[str, tuple], model_no: dict[str, str]) -> None:
        """Skip, as duplicates, the survivors the compare step finds among the catalog and the feed's
        earlier survivors; feed order, so a later listing is compared with the earlier ones."""
        pending = []
        for it in survivors:
            brand, color = seen.get(it.id, (None, None))
            if gate:
                cands = [c for c in known if same_brand(brand, c["brand"])]
            else:
                cands = [c for c in known if norm(c["brand"]) == norm(brand)]
            pending.append((it, _rank(f"{it.title} {model_no.get(it.id, '')}", cands)))
            known.append({"brand": brand or "", "title": it.title, "color": color})
        matched = await _gather(limit, (_safe(compare(it, cands)) if cands else _none() for it, cands in pending))
        for (it, _), m in zip(pending, matched, strict=True):
            if m is not None:
                out[it.id] = {"skip": "duplicate"}

    model_no: dict[str, str] = {}
    todo = items
    if gate:
        sorted_ = await _gather(limit, (_safe(sort(it)) for it in items))
        brand_of: dict[str, tuple] = {}
        for it, s in zip(items, sorted_, strict=True):
            if not isinstance(s, dict):
                continue  # unsorted: the full extract and the rules after it decide
            if s.get("book") is True or excluded_brand(s.get("brand")):
                out[it.id] = {"skip": "excluded"}
            brand_of[it.id], model_no[it.id] = (s.get("brand"), None), str(s.get("model") or "")
        await match([it for it in items if it.id not in out and it.id in brand_of], brand_of, model_no)
        todo = [it for it in items if it.id not in out]

    extracted = await _gather(limit, (_safe(extract(it)) for it in todo))
    records: dict[str, object] = {}
    for it, r in zip(todo, extracted, strict=True):
        if isinstance(r, dict):
            m = str(r.pop("model", "") or "")
            model_no.setdefault(it.id, m)
        records[it.id] = r

    def apply_rules():
        for i, r in list(records.items()):
            if ruled_out(r):
                out[i] = {"skip": "excluded"}
                del records[i]

    apply_rules()
    for _ in range(ROUNDS):
        await _fix_round(limit, {i: by_id[i] for i in records}, records, repair, partial=True)
    apply_rules()
    for i in [i for i, r in records.items() if validate(r, partial=True, content=True)]:
        del records[i]  # still invalid after its rounds: dropped, neither catalogued nor skipped

    if not gate:
        left = [it for it in items if it.id in records]
        await match(left, {i: (r.get("brand"), r.get("color")) for i, r in records.items()}, model_no)  # type: ignore[union-attr]
        for it in left:
            if it.id in out:
                del records[it.id]
    else:
        # Sorted items were matched before their extract; one the sort could not read is matched now.
        late = [it for it in items if it.id in records and it.id not in brand_of]
        await match(late, {it.id: (records[it.id].get("brand"), records[it.id].get("color")) for it in late}, model_no)  # type: ignore[union-attr]
        for it in late:
            if it.id in out:
                del records[it.id]

    kept = [by_id[i] for i in records]
    written = await _gather(limit, (_safe(write(it, records[it.id])) for it in kept))
    for it, r in zip(kept, written, strict=True):
        records[it.id] = r
    for _ in range(ROUNDS):
        await _fix_round(limit, {it.id: it for it in kept}, records, fix, partial=False)
    for it in kept:
        r = records.get(it.id)
        if isinstance(r, dict) and not check(r, it):
            out[it.id] = {"record": r}
    return out


async def _none():
    return None


async def _fix_round(limit, items: dict[str, Item], records: dict, fixer, partial: bool) -> None:
    """One round: `fixer` every item whose record still fails, all at once."""
    errs = {i: validate(records.get(i), partial, listing_text(it.public()), content=True) for i, it in items.items()}
    failed = {i: e for i, e in errs.items() if e}
    fixed = await _gather(limit, (_safe(fixer(items[i], records.get(i), e)) for i, e in failed.items()))
    for i, r in zip(failed, fixed, strict=True):
        if r is not None:
            records[i] = r


# ---- the per-item agent -------------------------------------------------------------------------


def agent_prompt(policy: dict) -> str:
    return f"""You take products into a store's catalog from a supplier's feed, one product at a time.

First decide whether the store should take this product at all, before writing anything. Read
what it is and its brand. If the rules exclude it, call skip_item with "excluded". Otherwise call
lookup_catalog with its brand and compare: if the same product is already there, call skip_item
with "duplicate". Only for a product the store should take, write the full record, check it with
validate_record, fix whatever it reports, and finish with submit_record, which refuses an invalid
record.

{rules(policy)}

{RECORD_SPEC}

{CONTENT_SPEC}"""


_RECORD_ARG = {"type": "object", "description": "the full record, as described in the instructions"}


class Store:
    """The catalog the agents look brands up in, plus every product an agent has accepted so far
    in this run: the shared store a builder would give agents working one feed in parallel."""

    def __init__(self, catalog: list[dict]):
        self.entries = list(catalog)

    def lookup(self, brand: str) -> list[dict]:
        b = norm(brand)
        if not b:
            return []
        hits = [e for e in self.entries if norm(e["brand"]) == b]
        hits += [e for e in self.entries if norm(e["brand"]) != b and len(b) >= 3 and b in norm(e["brand"])]
        return hits[:20]

    def accept(self, it: Item, record: dict) -> None:
        self.entries.append({"sku": f"new:{it.id}", "brand": record.get("brand") or "", "title": it.title,
                             "color": record.get("color")})  # fmt: skip


def tools(store: Store, results: dict[str, dict], it: Item) -> list[agent.Tool]:
    async def lookup_catalog(brand: str = "") -> str:
        return json.dumps({"products": store.lookup(brand)})

    async def skip_item(reason: str = "") -> str | agent.Done:
        if reason not in SKIPS:
            return json.dumps({"accepted": False, "error": f"reason must be one of {list(SKIPS)}"})
        results[it.id] = {"skip": reason}
        return agent.Done(json.dumps({"accepted": True}), None)

    async def validate_record(record: object = None) -> str:
        errs = check(record, it)
        return json.dumps({"valid": not errs, "errors": errs})

    async def submit_record(record: object = None) -> str | agent.Done:
        errs = check(record, it)
        if errs:
            return json.dumps({"accepted": False, "errors": errs})
        results[it.id] = {"record": record}
        store.accept(it, record)  # type: ignore[arg-type]
        return agent.Done(json.dumps({"accepted": True}), record)

    params = {"type": "object", "properties": {"record": _RECORD_ARG}, "required": ["record"]}
    return [
        agent.Tool("lookup_catalog", "The store's catalog entries (and products already taken from this feed) of a "
                   "brand.", {"type": "object", "properties": {"brand": {"type": "string"}}, "required": ["brand"]},
                   lookup_catalog),
        agent.Tool("skip_item", "Skip this product: not taken into the catalog. Ends the task.",
                   {"type": "object", "properties": {"reason": {"type": "string", "enum": list(SKIPS)}},
                    "required": ["reason"]}, skip_item),
        agent.Tool("validate_record", "Check a full record; returns whether it is valid and what is wrong.", params,
                   validate_record),
        agent.Tool("submit_record", "Submit the finished, valid record. Ends the task.", params, submit_record),
    ]  # fmt: skip


async def agents(
    client: Client,
    arm: str,
    items: list[Item],
    model: str,
    catalog: list[dict],
    policy: dict,
    limit: int = 4,
    max_turns: int = 8,
    on_done: Callable[[Item, agent.Outcome, dict], None] | None = None,
) -> tuple[dict[str, dict], dict[str, agent.Outcome]]:
    """One agent per item, `limit` at a time, all sharing one Store."""
    store, results = Store(catalog), {}
    system = agent_prompt(policy)

    async def one(it: Item) -> agent.Outcome:
        user = f"Product {it.id}:\n\n{it.listing()}"
        try:
            o = await agent.run(client, arm, TASK, it.id, model, system, user, tools(store, results, it), max_turns)
        except ModelError as e:
            o = agent.Outcome(False, reason=f"model error: {e}")
        if on_done:
            on_done(it, o, results.get(it.id, {}))
        return o

    outcomes = await _gather(limit, (one(it) for it in items))
    return results, {it.id: o for it, o in zip(items, outcomes, strict=True)}
