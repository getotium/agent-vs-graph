"""What a provider's prompt cache would have given the recorded traffic.

The local server's cache hits are not the provider's: llama.cpp keeps a cache per slot, so its hit
rate moves with the number of slots, and no provider caches by those rules. So the meter records
each prompt's shape instead (`chain`: a hash at every boundary where a cache can match, with the
characters up to it; never the text), and the report replays an arm's requests against each
provider's rule (`replay`).

Two kinds of rule:

- auto (OpenAI, Otium): every prefix of at least `min_tokens` is cached when it is seen; a later
  request reads the longest one still alive. No write charge.
- marked (Anthropic): only a marked prefix is cached, and writing it costs extra. The replay
  marks a prefix exactly when a later request reuses it within the TTL, the best a caller could
  do, so the result is the arm's best case, not what an unmarked prompt would get.

Approximations, stated where the report shows a cached share: an entry is usable once the request
that wrote it has finished (conservative for requests in flight together); cached tokens are the
prompt's tokens in proportion to the prefix's characters.
"""

from __future__ import annotations

import bisect
import hashlib
import json
from dataclasses import dataclass, replace

from .ledger import Record


@dataclass(frozen=True)
class Rule:
    mode: str  # "auto" or "marked"
    min_tokens: int
    ttl_s: float
    step_tokens: int = 1  # a cached length is rounded down to a multiple of this (OpenAI: 128)


def _canon(x: object) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def chain(wire: str, req: dict) -> list[list]:
    """[[hash, chars], ...] at each prefix boundary of a request: tools, system, then each message.
    The model seeds the hash, since caches are per model."""
    segs: list[object] = []
    if req.get("tools"):
        segs.append({"tools": req["tools"]})
    if wire == "anthropic" and req.get("system"):
        segs.append({"system": req["system"]})
    segs += list(req.get("messages") or [])
    out, h, chars = [], hashlib.sha256(str(req.get("model", "")).encode()).hexdigest(), 0
    for seg in segs:
        text = _canon(seg)
        h = hashlib.sha256((h + text).encode()).hexdigest()
        chars += len(text)
        out.append([h[:16], chars])
    return out


def _tokens(rec: Record, chars: int, total: int, rule: Rule) -> int:
    t = rec.prompt * chars // total if total else 0
    t -= t % rule.step_tokens
    return t if t >= rule.min_tokens else 0


def replay(records: list[Record], rule: Rule) -> tuple[list[Record], int]:
    """The records with input, cache_read and cache_write as the rule would have billed them, in
    the same order, and how many had no recorded prefix (priced as all new input)."""
    out: list[Record] = list(records)
    unknown = 0
    groups: dict[tuple[str, str], list[int]] = {}
    for i, r in enumerate(records):
        groups.setdefault((r.run, r.arm), []).append(i)
    for idx in groups.values():
        idx.sort(key=lambda i: _start(records[i]))
        # For a marked rule: when each prefix is next seen, to mark only what will be read.
        seen: dict[str, list[float]] = {}
        for i in idx:
            for h, _ in records[i].extra.get("prefix") or []:
                seen.setdefault(h, []).append(_start(records[i]))
        alive: dict[str, tuple[float, float]] = {}  # hash → (usable from, expires)
        for i in idx:
            r = records[i]
            pre = r.extra.get("prefix") or []
            if not pre:
                unknown += 1
                out[i] = replace(r, input=r.prompt, cache_read=0, cache_write=0)
                continue
            s, end, total = _start(r), _start(r) + r.latency_ms / 1000, pre[-1][1]
            hit = -1
            for k in range(len(pre) - 1, -1, -1):
                ready, expires = alive.get(pre[k][0], (0.0, -1.0))
                if ready <= s < expires:
                    hit = k
                    break
            read = _tokens(r, pre[hit][1], total, rule) if hit >= 0 else 0
            for k in range(hit + 1):  # a read refreshes the entry
                h = pre[k][0]
                if h in alive:
                    alive[h] = (alive[h][0], s + rule.ttl_s)
            write = 0
            if rule.mode == "auto":
                for h, chars in pre:
                    if _tokens(r, chars, total, rule) and alive.get(h, (0.0, -1.0))[1] <= s:
                        alive[h] = (end, s + rule.ttl_s)
            else:
                mark = -1
                for k in range(len(pre) - 1, hit, -1):
                    times = seen.get(pre[k][0], [])
                    j = bisect.bisect_right(times, s)
                    if j < len(times) and times[j] <= s + rule.ttl_s:
                        mark = k
                        break
                if mark >= 0 and _tokens(r, pre[mark][1], total, rule):
                    write = max(_tokens(r, pre[mark][1], total, rule) - read, 0)
                    alive[pre[mark][0]] = (end, s + rule.ttl_s)
            out[i] = replace(r, input=r.prompt - read - write, cache_read=read, cache_write=write)
    return out, unknown


def _start(r: Record) -> float:
    return r.ts - r.latency_ms / 1000
