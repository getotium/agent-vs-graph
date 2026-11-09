"""Building task inputs from public datasets.

ESCI: Amazon's Shopping Queries dataset (github.com/amazon-science/esci-data, Apache-2.0). Its
product catalog has 1.8M listings in three locales. The enrichment task takes a seeded sample of
US listings that have a brand, a color and some text to work from, with weapons, adult
products, tobacco and drugs filtered out. The sample is chosen by a
hash of the seed and the product id, so it does not depend on the order the file is read in.
"""

from __future__ import annotations

import hashlib
import heapq
import html
import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

# Matched as whole words, case-insensitive, against title, bullets, description and brand.
BLOCKED = re.compile(
    r"\b(guns?|firearms?|rifles?|riflescopes?|pistols?|handguns?|shotguns?|revolvers?|ammo|ammunition|"
    r"cartridges?|holsters?|muzzle|suppressors?|silencers?|bayonets?|airsoft|"
    r"bb guns?|pellet guns?|crossbows?|tactical|knives|knife|switchblade|swords?|daggers?|machetes?|sharpened|"
    r"brass knuckles|stun guns?|tasers?|"
    r"pepper spray|sex|sexy|adult|erotic|lingerie|see-through|g-strings?|nipples?|nippleless|vibrators?|vibratex|wand massagers?|"
    r"personal massagers?|dildos?|"
    r"condoms?|lubricant|nicotine|vape|"
    r"vaping|cbd|thc|cannabis|marijuana|kratom|tobacco|cigars?|cigarettes?)\b",
    re.IGNORECASE,
)

# Catalog placeholders, not brands: an item carrying one has no gold brand to score against.
PLACEHOLDER_BRANDS = {"unknown", "generic", "na", "none", "unbranded", "nobrand", "brand"}

MAX_TEXT = 1500  # characters of bullets and of description kept per listing
_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"[ \t\r\f\v]+")


def clean_text(s: str | None, limit: int = MAX_TEXT) -> str:
    """Listing text with HTML tags and entities removed, spaces collapsed, cut at a word."""
    if not s:
        return ""
    s = html.unescape(_TAGS.sub(" ", s))
    s = "\n".join(line.strip() for line in _SPACE.sub(" ", s).splitlines() if line.strip())
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + " …"
    return s


def item(row: dict) -> dict | None:
    """One catalog row as a task item, or None when it does not qualify."""
    if row.get("product_locale") != "us":
        return None
    title = clean_text(row.get("product_title"), 300)
    brand = (row.get("product_brand") or "").strip()
    color = (row.get("product_color") or "").strip()
    bullets = clean_text(row.get("product_bullet_point"))
    desc = clean_text(row.get("product_description"))
    if not (title and brand and color and (bullets or desc)):
        return None
    if BLOCKED.search(f"{title} {bullets} {desc} {brand}"):
        return None
    # The gold brand must be recoverable: named somewhere in the listing every arm reads.
    norm = _alnum(brand)
    if norm in PLACEHOLDER_BRANDS or norm not in _alnum(f"{title} {bullets} {desc}"):
        return None
    return {
        "id": row["product_id"],
        "title": title,
        "bullets": bullets,
        "description": desc,
        "gold": {"brand": brand, "color": color},
    }


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _rank(seed: int, pid: str) -> str:
    return hashlib.sha256(f"{seed}:{pid}".encode()).hexdigest()


def sample(rows: Iterable[dict], n: int, seed: int = 1) -> list[dict]:
    """The n qualifying items with the lowest seeded hash, in hash order: the same n for the same
    seed however the rows arrive, and a larger n is a superset of a smaller one."""
    best: list[tuple[int, str, dict]] = []  # a max-heap on rank, via negated ints
    for row in rows:
        it = item(row)
        if it is None:
            continue
        r = _rank(seed, it["id"])
        key = -int(r, 16)
        if len(best) < n:
            heapq.heappush(best, (key, it["id"], it))
        elif key > best[0][0]:
            heapq.heapreplace(best, (key, it["id"], it))
    return [it for _, _, it in sorted(best, key=lambda t: -t[0])]


def esci_rows(parquet: Path) -> Iterator[dict]:
    """The US rows of the ESCI product file, streamed one row group at a time."""
    import pyarrow.parquet as pq  # only `avg data` needs it: pip install -e '.[data]'

    f = pq.ParquetFile(parquet)
    for i in range(f.num_row_groups):
        t = f.read_row_group(i)
        yield from (r for r in t.to_pylist() if r.get("product_locale") == "us")


def write(items: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


# ---- catalog intake -----------------------------------------------------------------------------
# Task 1's items with rejects mixed in (docs/design.md, "Catalog intake"). Everything is built from
# the catalog by fixed rules and a seed: the re-listings are rewritten by code, not by a model.

# Anything that could be read as a book or other media is kept out of the new items, so an arm
# that excludes it as a book is never scored wrong for it.
MEDIA = re.compile(
    r"\b(books?|novels?|paperback|hardcover|hardback|kindle|ebook|audiobooks?|edition|isbn|author|"
    r"dvds?|blu-ray|cds?|vinyl|album|magazines?|comics?|manga|calendar|journal|notebook|planner)\b",
    re.IGNORECASE,
)
ISBN = re.compile(r"\d{9}[\dX]")
MIXES = {20: 0.20, 85: 0.85}  # file suffix → share of the feed that should be rejected
SPLIT = {"catalog_duplicate": 0.30, "feed_duplicate": 0.20, "excluded_brand": 0.25}  # the rest: books
EXCLUDED_BRANDS = 12
FILLER = 400  # catalog entries beyond the duplicates and their distractors
POOL = 40_000  # qualifying listings sampled (lowest seeded hash) to build every mix from


def book(row: dict) -> dict | None:
    """A US listing whose product id is an ISBN-10: a book, the store's excluded kind."""
    if row.get("product_locale") != "us" or not ISBN.fullmatch(row.get("product_id") or ""):
        return None
    title = clean_text(row.get("product_title"), 300)
    bullets, desc = clean_text(row.get("product_bullet_point")), clean_text(row.get("product_description"))
    if not (title and (bullets or desc)) or BLOCKED.search(f"{title} {bullets} {desc}"):
        return None
    brand = (row.get("product_brand") or "").strip()
    return {"id": row["product_id"], "title": title, "bullets": bullets, "description": desc,
            "gold": {"brand": brand, "color": ""}}  # fmt: skip


def relist(it: dict, rng) -> dict:
    """The same product listed again in other words: title parts reordered with the brand moved,
    bullets reversed, the description dropped when there are bullets and halved when there are not.
    The brand, model and facts survive."""
    brand, title = it["gold"]["brand"], it["title"]
    rest = re.sub(re.escape(brand), "", title, count=1, flags=re.IGNORECASE).strip(" -,|:")
    parts = [p.strip() for p in re.split(r"\s+[-|]\s+|,\s+", rest) if p.strip()]
    if len(parts) > 1:
        k = rng.randrange(1, len(parts))
        parts = parts[k:] + parts[:k]
    rest = ", ".join(parts)
    title = f"{rest} - {brand}" if rng.random() < 0.5 else f"{brand} {rest}"
    bullets = "\n".join(reversed(it["bullets"].splitlines())) if it["bullets"] else ""
    desc = "" if bullets else it["description"][: max(1, len(it["description"]) // 2)].rsplit(" ", 1)[0]
    return {**it, "title": title, "bullets": bullets, "description": desc}


def intake_pools(rows: Iterable[dict], seed: int = 1) -> tuple[list[dict], list[dict]]:
    """The listings every mix is built from: qualifying task 1 items with nothing media-like, and
    books. Seeded hash order, so the same pools come out however the rows arrive."""
    items: list[tuple[int, str, dict]] = []
    books: list[tuple[int, str, dict]] = []
    for row in rows:
        it = item(row)
        if it is not None and not MEDIA.search(f"{it['title']} {it['bullets']} {it['description']}"):
            heap, cap = items, POOL
        else:
            it = book(row)
            if it is None:
                continue
            heap, cap = books, 2_000
        key = -int(_rank(seed, it["id"]), 16)
        if len(heap) < cap:
            heapq.heappush(heap, (key, it["id"], it))
        elif key > heap[0][0]:
            heapq.heapreplace(heap, (key, it["id"], it))
    order = lambda h: [it for _, _, it in sorted(h, key=lambda t: -t[0])]
    return order(items), order(books)


def intake(pool: list[dict], books: list[dict], n: int = 500, seed: int = 1) -> dict:
    """Every file of the task: the shared policy, and per mix its items and catalog. An item's gold
    carries its kind, and the group of listings it shares a product with when it is in one."""
    import random

    by_brand: dict[str, list[dict]] = {}
    for it in pool:
        by_brand.setdefault(_alnum(it["gold"]["brand"]), []).append(it)
    names = sorted(by_brand, key=lambda b: _rank(seed, b))
    excluded = [b for b in names if len(by_brand[b]) >= 12][:EXCLUDED_BRANDS]
    policy = {
        "excluded_brands": sorted(by_brand[b][0]["gold"]["brand"] for b in excluded),
        "excluded_kinds": ["books"],
    }
    # A product that so much as names an excluded brand ("fits The North Face jackets") is kept out
    # of everything but the excluded-brand rejects, so skipping it is never scored as wrong.
    named = re.compile("|".join(rf"\b{re.escape(b)}\b" for b in policy["excluded_brands"]), re.IGNORECASE)
    for b in names:
        if b not in excluded:
            by_brand[b] = [it for it in by_brand[b] if not named.search(listing_of(it))]
    out: dict = {"policy.json": policy}
    for suffix, share in MIXES.items():
        rng = random.Random(f"{seed}:{suffix}")
        rejects = round(n * share)
        keep = n - rejects
        cat = round(rejects * SPLIT["catalog_duplicate"])
        feed = round(rejects * SPLIT["feed_duplicate"])
        exb = round(rejects * SPLIT["excluded_brand"])
        nbooks = rejects - cat - feed - exb
        copies = 1 if feed <= keep // 2 else 2  # re-listings per feed-duplicated product
        groups = -(-feed // copies)

        free = [b for b in names if b not in excluded]
        rng.shuffle(free)
        used: set[str] = set()
        take = lambda it, used=used: used.add(it["id"]) or it  # marks an item as used
        catalog, feed_items, catalog_items = [], [], []

        # Catalog duplicates: a brand with three products gives one to re-list, one to the catalog
        # as a distractor, and one to the feed as a new product the brand match alone would miss.
        multi = [b for b in free if len(by_brand[b]) >= 3]
        hard = []
        for b in multi[:cat]:
            dup, other, new = by_brand[b][:3]
            catalog += [take(dup), take(other)]
            catalog_items.append(("catalog_duplicate", relist(dup, rng), None))
            hard.append(take(new))
        rest = [it for b in free for it in by_brand[b] if it["id"] not in used and b not in multi[:cat]]
        rng.shuffle(rest)
        for g in range(groups):
            orig = take(rest.pop())
            feed_items.append(("new", orig, f"g{g}"))
            for _ in range(min(copies, feed - g * copies)):
                feed_items.append(("feed_duplicate", relist(orig, rng), f"g{g}"))
        news = hard[: keep - groups]
        news += [take(rest.pop()) for _ in range(keep - groups - len(news))]
        catalog += [take(rest.pop()) for _ in range(FILLER)]  # the rest of the store's catalog
        exb_items = [by_brand[excluded[k % len(excluded)]][k // len(excluded)] for k in range(exb)]
        chosen = (
            [("new", it, None) for it in news]
            + feed_items
            + catalog_items
            + [("excluded_brand", it, None) for it in exb_items]
            + [("excluded_kind", it, None) for it in books[:nbooks]]
        )
        rng.shuffle(chosen)
        items = []
        for k, (kind, it, group) in enumerate(chosen):
            gold = {**it["gold"], "kind": kind, "source": it["id"]}
            if group:
                gold["group"] = group
            pid = "p" + hashlib.sha256(f"{seed}:{suffix}:{k}:{it['id']}".encode()).hexdigest()[:8]
            items.append({"id": pid, "title": it["title"], "bullets": it["bullets"],
                          "description": it["description"], "gold": gold})  # fmt: skip
        rng.shuffle(catalog)
        out[f"items-{suffix}.jsonl"] = items
        out[f"catalog-{suffix}.jsonl"] = [
            {"sku": f"C{k:05d}", "brand": c["gold"]["brand"], "title": c["title"], "color": c["gold"]["color"]}
            for k, c in enumerate(catalog)
        ]
    return out


def listing_of(it: dict) -> str:
    return f"{it['title']} {it['bullets']} {it['description']}"
