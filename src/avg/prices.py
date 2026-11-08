"""Price sheets and what a request costs under one.

A price sheet is YAML (see prices/default.yaml): per-million-token rates for each model, each
with the page it came from and the date it was checked. The ledger stores tokens, never money,
so any token profile can be priced as any model: what the local run's traffic would have cost
on a hosted API at real-time or batch rates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .cache import Rule
from .ledger import Record

M = 1_000_000


@dataclass
class Rates:
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float | None = None  # None: the provider has no cache discount
    cache_write: float | None = None  # None: writing the cache costs the input rate


@dataclass
class Price:
    id: str
    vendor: str
    source: str
    checked: str
    rates: Rates
    # The vendor's discount for asynchronous batch work, applied to every token class.
    batch_discount: float = 0.0
    # The listed rates are already the batch price and there is no real-time option (Otium).
    batch_only: bool = False
    # A request whose prompt (new + cached + cache-write tokens) is over this many tokens pays
    # long_rates for all of it, as Anthropic prices long prompts.
    long_over: int | None = None
    long_rates: Rates | None = None
    # How the provider's prompt cache works; the report replays the traffic against it. Required
    # when there is a cache discount: the local server's own hits are never priced.
    cache: Rule | None = None
    # Set when a number could not be confirmed from the vendor's own page.
    verify: str = ""
    notes: list[str] = field(default_factory=list)

    def can(self, batch: bool) -> bool:
        """Whether this price has the mode at all: a batch-only service has no real-time rate."""
        return batch or not self.batch_only

    def cost(self, rec: Record, batch: bool) -> float:
        """USD for one ledger record. Raises if the mode is not offered (see `can`)."""
        if not self.can(batch):
            raise ValueError(f"{self.id} has no real-time price")
        r = self.long_rates if self.long_over is not None and rec.prompt > self.long_over else self.rates
        assert r is not None
        cache_read = r.input if r.cache_read is None else r.cache_read
        cache_write = r.input if r.cache_write is None else r.cache_write
        usd = (
            rec.input * r.input + rec.cache_read * cache_read + rec.cache_write * cache_write + rec.output * r.output
        ) / M
        if batch and not self.batch_only:
            usd *= 1 - self.batch_discount
        return usd


def _rates(d: dict) -> Rates:
    return Rates(
        input=float(d["input"]),
        output=float(d["output"]),
        cache_read=None if d.get("cache_read") is None else float(d["cache_read"]),
        cache_write=None if d.get("cache_write") is None else float(d["cache_write"]),
    )


def load(path: Path) -> dict[str, Price]:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    out: dict[str, Price] = {}
    for p in doc["prices"]:
        for key in ("id", "vendor", "source", "checked", "input", "output"):
            if key not in p:
                raise ValueError(f"price {p.get('id', '?')}: missing {key}")
        long = p.get("long_prompt")
        c = p.get("cache")
        if c is None and (p.get("cache_read") is not None or p.get("cache_write") is not None):
            raise ValueError(f"price {p['id']}: a cache rate needs a cache rule (mode, min_tokens, ttl_s)")
        if c is not None and c.get("mode") not in ("auto", "marked"):
            raise ValueError(f"price {p['id']}: cache mode must be auto or marked")
        out[p["id"]] = Price(
            id=p["id"],
            vendor=p["vendor"],
            source=p["source"],
            checked=str(p["checked"]),
            rates=_rates(p),
            batch_discount=float(p.get("batch_discount", 0.0)),
            batch_only=bool(p.get("batch_only", False)),
            long_over=int(long["over"]) if long else None,
            long_rates=_rates(long) if long else None,
            cache=Rule(c["mode"], int(c["min_tokens"]), float(c["ttl_s"]), int(c.get("step_tokens", 1))) if c else None,
            verify=p.get("verify", ""),
            notes=list(p.get("notes", [])),
        )
    return out
