"""The enrichment record: its spec and its validator, shared by every arm.

Standard library only, on purpose: the harness arms get this file copied into their workspace
beside a small validate script, so the agents check their work with exactly the code the graph
and the scorer use.
"""

from __future__ import annotations

import json
import re

CATEGORIES = [
    "Clothing",
    "Shoes",
    "Jewelry & Watches",
    "Bags & Luggage",
    "Beauty & Personal Care",
    "Health & Household",
    "Home & Kitchen",
    "Furniture",
    "Tools & Home Improvement",
    "Garden & Outdoor",
    "Sports & Fitness",
    "Toys & Games",
    "Baby",
    "Pet Supplies",
    "Electronics",
    "Computers & Accessories",
    "Cell Phones & Accessories",
    "Office & School Supplies",
    "Arts & Crafts",
    "Automotive",
    "Books & Media",
    "Grocery",
    "Other",
]

KEYS = {"category", "brand", "color", "specs", "description"}
MAX_SPECS, MAX_SPEC_CHARS = 8, 80
MIN_WORDS, MAX_WORDS = 15, 60
# Written, not copied: at most this share of the description's PHRASE-word phrases may appear
# verbatim in the listing. On the first runs, descriptions a model wrote peaked at 0.40; ones
# assembled from the listing's own sentences ran 0.70 to 1.00.
MAX_COPIED, PHRASE = 0.5, 5
# A spec value this many words long that stops mid-word in the listing was cut from it.
CUT_WORDS = 6

RECORD_SPEC = f"""A record is one JSON object with exactly these keys:
- "category": one of {json.dumps(CATEGORIES)}
- "brand": the maker's brand as a string, or null if the listing does not say
- "color": the product's main color as a string, or null if it has none or the listing does not say
- "specs": an object of 1 to {MAX_SPECS} short facts from the listing, string keys to string values \
of at most {MAX_SPEC_CHARS} characters (for example "material", "size", "count"); a fact, not a \
sentence cut from the listing
- "description": a plain product description of {MIN_WORDS} to {MAX_WORDS} words, in your own words \
rather than sentences copied from the listing, claiming nothing the listing does not support"""
# The spec states the copy rules in words; the validator holds the thresholds and names them when a
# record fails. Stating "at most half of its 5-word phrases" here sent Gemma 4 12B into counting
# phrases while it thought: 8 of 10 first turns ran out the 4,096-token cap without answering.

# Catalog intake's content: what a store page needs, written only for the items the store keeps.
CONTENT_KEYS = {"seo_title", "meta_description", "long_description"}
MAX_SEO_CHARS = 60
MIN_META_CHARS, MAX_META_CHARS = 120, 160
MIN_LONG_WORDS, MAX_LONG_WORDS = 120, 200

CONTENT_SPEC = f"""A catalogued product's record also has its page content, three more keys:
- "seo_title": the page title, at most {MAX_SEO_CHARS} characters, naming the brand and the product
- "meta_description": the search snippet, {MIN_META_CHARS} to {MAX_META_CHARS} characters, one or two plain sentences
- "long_description": the page's description, {MIN_LONG_WORDS} to {MAX_LONG_WORDS} words, in your own words rather \
than sentences copied from the listing, claiming nothing the listing does not support"""


def listing_text(product: dict) -> str:
    """The text a record is written from: a product's title, bullets and description."""
    return "\n".join(str(product.get(k) or "") for k in ("title", "bullets", "description"))


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def copied_share(description: str, listing: str) -> float:
    """The share of the description's PHRASE-word phrases that appear verbatim in the listing."""
    d, src = _words(description), _words(listing)
    phrases = [tuple(d[i : i + PHRASE]) for i in range(len(d) - PHRASE + 1)]
    have = {tuple(src[i : i + PHRASE]) for i in range(len(src) - PHRASE + 1)}
    return sum(p in have for p in phrases) / len(phrases) if phrases else 0.0


def cut_from(value: str, listing: str) -> bool:
    """Whether a spec value is the listing's own text stopped mid-word: CUT_WORDS or more words,
    found verbatim, with the listing's next character still a letter or digit."""
    v, src = (re.sub(r"\s+", " ", t).strip().lower() for t in (value, listing))
    if len(v.split()) < CUT_WORDS or not v[-1:].isalnum():
        return False
    k = src.find(v)
    while k >= 0:
        if src[k + len(v) : k + len(v) + 1].isalnum():
            return True
        k = src.find(v, k + 1)
    return False


def validate(record: object, partial: bool = False, listing: str | None = None, content: bool = False) -> list[str]:
    """What is wrong with a record, as messages a model can act on; empty when it is valid.
    `partial` checks a record without its description (the graph writes that last). Given the
    `listing` (see listing_text), it also checks that specs and description were not copied.
    `content` checks a catalog intake record, which also carries its page content (CONTENT_KEYS);
    with `partial` too, neither the description nor the content is expected yet."""
    if not isinstance(record, dict):
        return ["the record must be a JSON object"]
    keys = KEYS | CONTENT_KEYS if content else KEYS
    want = keys - {"description"} - CONTENT_KEYS if partial else keys
    errs = []
    missing = sorted(want - set(record))
    if missing:
        errs.append(f"missing keys: {', '.join(missing)}")
    extra = sorted(set(record) - keys)
    if extra:
        errs.append(f"unexpected keys: {', '.join(extra)}")
    if "category" in record and record["category"] not in CATEGORIES:
        errs.append(f"category {record['category']!r} is not one of the allowed categories")
    for k in ("brand", "color"):
        v = record.get(k)
        if k in record and v is not None and not (isinstance(v, str) and v.strip()):
            errs.append(f"{k} must be a non-empty string or null")
    if "specs" in record:
        specs = record["specs"]
        if not isinstance(specs, dict) or not specs:
            errs.append(f"specs must be an object with 1 to {MAX_SPECS} entries")
        else:
            if len(specs) > MAX_SPECS:
                errs.append(f"specs has {len(specs)} entries; at most {MAX_SPECS}")
            bad = [k for k, v in specs.items() if not isinstance(v, str) or not v.strip() or len(v) > MAX_SPEC_CHARS]
            if bad:
                errs.append(f"specs values must be non-empty strings of at most {MAX_SPEC_CHARS} characters: "
                            f"{', '.join(bad)}")  # fmt: skip
            cut = [k for k, v in specs.items() if listing and isinstance(v, str) and cut_from(v, listing)]
            if cut:
                errs.append(f"specs values must be facts, not listing text cut off mid-word: {', '.join(cut)}")
    if "description" in record:
        d = record["description"]
        n = len(d.split()) if isinstance(d, str) else 0
        if not MIN_WORDS <= n <= MAX_WORDS:
            errs.append(f"description must be {MIN_WORDS} to {MAX_WORDS} words; it has {n}")
        share = copied_share(d, listing) if listing and isinstance(d, str) else 0.0
        if share > MAX_COPIED:
            errs.append(f"description repeats the listing: {share:.0%} of its {PHRASE}-word phrases appear in it "
                        f"word for word (at most {MAX_COPIED:.0%}); write it in your own words")  # fmt: skip
    if content:
        errs += _content_errors(record, listing)
    return errs


def _content_errors(record: dict, listing: str | None) -> list[str]:
    # Each message starts with its key, so a fixer can tell content faults from the rest.
    errs = []
    t = record.get("seo_title")
    if "seo_title" in record and not (isinstance(t, str) and 0 < len(t.strip()) <= MAX_SEO_CHARS):
        errs.append(f"seo_title must be a string of 1 to {MAX_SEO_CHARS} characters; it has {_chars(t)}")
    m = record.get("meta_description")
    if "meta_description" in record and not (isinstance(m, str) and MIN_META_CHARS <= len(m.strip()) <= MAX_META_CHARS):
        errs.append(f"meta_description must be {MIN_META_CHARS} to {MAX_META_CHARS} characters; it has {_chars(m)}")
    if "long_description" in record:
        d = record["long_description"]
        n = len(d.split()) if isinstance(d, str) else 0
        if not MIN_LONG_WORDS <= n <= MAX_LONG_WORDS:
            errs.append(f"long_description must be {MIN_LONG_WORDS} to {MAX_LONG_WORDS} words; it has {n}")
        share = copied_share(d, listing) if listing and isinstance(d, str) else 0.0
        if share > MAX_COPIED:
            errs.append(f"long_description repeats the listing: {share:.0%} of its {PHRASE}-word phrases appear in "
                        f"it word for word (at most {MAX_COPIED:.0%}); write it in your own words")  # fmt: skip
    return errs


def _chars(v: object) -> int:
    return len(v.strip()) if isinstance(v, str) else 0
