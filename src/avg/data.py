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
