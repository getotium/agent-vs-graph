"""Replaying a provider's prompt cache over recorded prompts, from hand-built traffic."""

from avg import cache
from avg.ledger import Record

SYSTEM = {"role": "system", "content": "s" * 3000}
AUTO = cache.Rule("auto", min_tokens=100, ttl_s=300)
MARKED = cache.Rule("marked", min_tokens=100, ttl_s=300)


def req(*user: str, arm="agent", model="m") -> dict:
    return {"model": model, "messages": [SYSTEM, *({"role": "user", "content": u} for u in user)]}


def rec(body: dict, start: float, prompt: int = 1_000, arm="agent", latency_ms=1_000) -> Record:
    return Record(
        run="r", arm=arm, task="t", item="i", wire="openai", model=body["model"], input=prompt, cache_read=0,
        cache_write=0, output=10, latency_ms=latency_ms, status=200, ts=start + latency_ms / 1000,
        extra={"prefix": cache.chain("openai", body)},
    )  # fmt: skip


def test_chain_shares_a_prefix_exactly_as_far_as_the_prompts_agree():
    a, b = cache.chain("openai", req("x")), cache.chain("openai", req("y"))
    assert a[0] == b[0] and a[1][0] != b[1][0], "same system prompt, different user turn"
    assert cache.chain("openai", req("x", model="other"))[0][0] != a[0][0], "caches are per model"
    assert a[1][1] > a[0][1], "characters accumulate"


def test_auto_reads_the_shared_prefix_after_the_first_request_finishes():
    first, second = rec(req("x"), 0), rec(req("y"), 10)
    [a, b], unknown = cache.replay([first, second], AUTO)
    assert unknown == 0 and a.cache_read == 0
    assert 900 < b.cache_read < 1_000, "most of the prompt is the shared system prompt"
    assert b.input + b.cache_read == 1_000 and b.cache_write == 0, "auto caching charges no write"


def test_requests_in_flight_together_do_not_read_each_other():
    [_, b], _ = cache.replay([rec(req("x"), 0, latency_ms=5_000), rec(req("y"), 1)], AUTO)
    assert b.cache_read == 0


def test_an_entry_expires_after_its_lifetime():
    [_, b], _ = cache.replay([rec(req("x"), 0), rec(req("y"), 400)], AUTO)
    assert b.cache_read == 0


def test_short_prefixes_are_below_the_minimum():
    [_, b], _ = cache.replay([rec(req("x"), 0, prompt=50), rec(req("y"), 10, prompt=50)], AUTO)
    assert b.cache_read == 0


def test_marked_writes_only_what_a_later_request_reads():
    a, b, c = rec(req("x"), 0), rec(req("x", "more"), 10), rec(req("unrelated"), 1_000)
    [a2, b2, c2], _ = cache.replay([a, b, c], MARKED)
    assert a2.cache_write == 1_000, "the whole first prompt is marked, since the next request reuses it"
    assert 950 < b2.cache_read < 1_000, "the next one reads it: all of its prompt but its new turn"
    assert c2.cache_write == 0, "nothing reads it later, so nothing is marked"
    assert all(r.input + r.cache_read + r.cache_write == 1_000 for r in (a2, b2, c2))


def test_arms_do_not_share_a_cache():
    [_, b], _ = cache.replay([rec(req("x"), 0, arm="one"), rec(req("y"), 10, arm="two")], AUTO)
    assert b.cache_read == 0
