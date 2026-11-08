"""Task 1: the validator, the scoring, the input sample, and both runners driven end to end
through the meter by a scripted stand-in model."""

import json

import aiohttp
import pytest
from aiohttp.test_utils import TestServer

from avg import data, ledger, meter, stub
from avg.llm import Client, parse_json
from avg.tasks import enrich, record

GOOD = {
    "category": "Home & Kitchen",
    "brand": "Acme",
    "color": "Blue",
    "specs": {"material": "steel", "capacity": "1.5 L"},
    "description": " ".join(["word"] * 20),
}


@pytest.mark.parametrize(
    "change,partial,want",
    [
        ({}, False, []),
        ({"brand": None, "color": None}, False, []),
        ({"description": None}, True, []),
        ({"category": "Weapons"}, False, ["category 'Weapons' is not one of the allowed categories"]),
        ({"brand": ""}, False, ["brand must be a non-empty string or null"]),
        ({"specs": {}}, False, ["specs must be an object with 1 to 8 entries"]),
        ({"specs": {str(i): "x" for i in range(9)}}, False, ["specs has 9 entries; at most 8"]),
        ({"specs": {"size": "x" * 81}}, False, ["specs values must be non-empty strings of at most 80 characters: size"]),
        ({"description": "too short"}, False, ["description must be 15 to 60 words; it has 2"]),
        ({"extra": 1}, False, ["unexpected keys: extra"]),
        ({"description": None}, False, ["missing keys: description"]),
    ],
)  # fmt: skip
def test_validate(change, partial, want):
    record = {**GOOD, **change}
    record = {k: v for k, v in record.items() if not (k == "description" and v is None)}
    assert enrich.validate(record, partial) == want


def test_validate_rejects_a_non_object():
    assert enrich.validate(["not", "a", "record"]) == ["the record must be a JSON object"]
    assert enrich.validate(None) == ["the record must be a JSON object"]


@pytest.mark.parametrize(
    "got,gold,want",
    [
        ("Amazon Basics", "AmazonBasics", True),
        ("samsung", "SAMSUNG Electronics", True),
        ("HP", "HPE", False),  # short strings must match exactly
        ("Acme", "Apex", False),
        (None, "Acme", False),
        ("Acme", "", False),
    ],
)
def test_matches(got, gold, want):
    assert enrich.matches(got, gold) is want


def _item(gold: dict, title: str = "Acme kettle", bullets: str = "") -> enrich.Item:
    return enrich.Item("p1", title, bullets, "", gold)


def test_score():
    s = enrich.score(GOOD, _item({"brand": "ACME Corp", "color": "Navy Blue"}))
    assert (s.valid, s.brand, s.color, s.success) == (True, True, True, True)
    wrong = enrich.score({**GOOD, "brand": "Other"}, _item({"brand": "Acme", "color": ""}))
    assert (wrong.success, wrong.color) == (False, None), "no gold color: not scored"
    missing = enrich.score(None, _item({"brand": "Acme", "color": "Red"}))
    assert (missing.valid, missing.success, missing.color) == (False, False, False)


BULLETS = ("STAINLESS STEEL BODY: the kettle is made of food grade stainless steel that resists rust and "
           "keeps water tasting clean for years of daily use in any kitchen")  # fmt: skip


def test_a_copied_record_is_not_a_success():
    item = _item({"brand": "Acme", "color": ""}, bullets=BULLETS)
    copied = {**GOOD, "description": BULLETS.split(": ", 1)[1]}
    s = enrich.score(copied, item)
    assert (s.valid, s.brand, s.success) == (False, True, False), "right brand, but the description is the bullet"
    cut = {**GOOD, "specs": {"body": "the kettle is made of food grade stainless st"}}
    assert any("cut off mid-word" in e for e in item.check(cut))
    assert enrich.score(GOOD, item).success, "a record written in its own words passes"


@pytest.mark.parametrize(
    "value,want",
    [
        ("the kettle is made of food grade stainless st", True),  # stops inside "steel"
        ("the kettle is made of food grade stainless steel", False),  # a whole phrase: quoting is fine
        ("stainless st", False),  # too short to call a cut
        ("made of aluminium and glass with a wooden handle", False),  # not in the listing
    ],
)
def test_cut_from(value, want):
    assert record.cut_from(value, BULLETS) is want


def test_copied_share():
    assert record.copied_share(BULLETS, BULLETS) == 1.0
    assert record.copied_share("A rust resistant steel kettle that keeps water clean.", BULLETS) == 0.0
    assert record.copied_share("too short", BULLETS) == 0.0


@pytest.mark.parametrize(
    "text,want",
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('Here it is: {"a": {"b": 2}} hope that helps', {"a": {"b": 2}}),
        ("[1, 2]", None),
        ("no json", None),
        ("{broken", None),
        (None, None),
    ],
)
def test_parse_json(text, want):
    assert parse_json(text) == want


# ---- the sample ---------------------------------------------------------------------------------


def row(pid, **kw):
    base = {
        "product_id": pid,
        "product_title": f"Widget {pid}",
        "product_description": "<p>A fine&nbsp;widget &amp; more.</p>",
        "product_bullet_point": "Steel\nTwo pack\nMade by Acme",
        "product_brand": "Acme",
        "product_color": "Blue",
        "product_locale": "us",
    }
    return {**base, **kw}


@pytest.mark.parametrize(
    "change",
    [
        {"product_locale": "es"},
        {"product_brand": None},
        {"product_color": " "},
        {"product_description": None, "product_bullet_point": None},
        {"product_title": "Tactical rifle sling"},
        {"product_bullet_point": "Fits most pistol grips"},
        {"product_description": "A leather holster for everyday carry."},
        {"product_brand": "Unknown", "product_title": "Unknown widget"},
        {"product_brand": "Jewelry Affairs"},  # named nowhere in the listing: not recoverable
        {"product_title": "Master Sword SHARPENED edition"},
        {"product_title": "Men's See-Through G-String"},
    ],
)
def test_item_rejects(change):
    assert data.item(row("B1", **change)) is None


def test_item_cleans_text_and_keeps_gold():
    it = data.item(row("B1"))
    assert it["description"] == "A fine\xa0widget & more."
    assert it["gold"] == {"brand": "Acme", "color": "Blue"}


def test_clean_text_cuts_at_a_word():
    assert data.clean_text("aaa bbb ccc", limit=6) == "aaa …"


def test_sample_is_seeded_and_order_free():
    rows = [row(f"B{i}") for i in range(50)]
    a = data.sample(rows, 10, seed=1)
    assert [x["id"] for x in a] == [x["id"] for x in data.sample(list(reversed(rows)), 10, seed=1)]
    assert [x["id"] for x in data.sample(rows, 5, seed=1)] == [x["id"] for x in a[:5]], "a prefix of the larger"
    assert [x["id"] for x in data.sample(rows, 10, seed=2)] != [x["id"] for x in a]


# ---- the runners, end to end through the meter --------------------------------------------------

ITEMS = [
    enrich.Item("p1", "Acme kettle", "Steel", "", {"brand": "Acme", "color": "Blue"}),
    enrich.Item("p2", "Bolt kettle", "Steel", "", {"brand": "Bolt", "color": "Red"}),
]


def system(req) -> str:
    return req["messages"][0]["content"]


def graph_model(req) -> dict:
    """extract writes a bad category for p2; repair fixes it; describe writes 20 words."""
    sys_, user = system(req), req["messages"][-1]["content"]
    brand = "Bolt" if "Bolt" in user else "Acme"
    attrs = {k: v for k, v in GOOD.items() if k != "description"} | {"brand": brand}
    if sys_ == enrich.EXTRACT:
        if brand == "Bolt":
            attrs["category"] = "Kettles"
        return {"role": "assistant", "content": f"```json\n{json.dumps(attrs)}\n```"}
    if sys_ == enrich.REPAIR:
        return {"role": "assistant", "content": json.dumps(attrs)}
    if sys_ == enrich.DESCRIBE:
        return {"role": "assistant", "content": GOOD["description"]}
    raise AssertionError(f"unexpected prompt: {sys_[:40]}")


def agent_model(req) -> dict:
    """First turn validates a bad record, second submits a good one: the loop's normal path."""
    turn = sum(m["role"] == "assistant" for m in req["messages"]) + 1
    assert [t["function"]["name"] for t in req["tools"]] == ["validate_record", "submit_record"]
    record = {**GOOD, "category": "Kettles"} if turn == 1 else GOOD
    name = "validate_record" if turn == 1 else "submit_record"
    call = {
        "id": f"c{turn}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps({"record": record})},
    }
    return {"role": "assistant", "content": None, "tool_calls": [call]}


@pytest.fixture
async def rig(aiohttp_client, tmp_path):
    async def make(reply, models=None):
        servers = {}
        for name in models or ["m"]:
            servers[name] = TestServer(stub.app(name, reply))
            await servers[name].start_server()
        urls = {n: str(s.make_url("")).rstrip("/") for n, s in servers.items()}
        first = next(iter(urls.values()))
        path = tmp_path / "ledger.jsonl"
        up = meter.Upstreams(openai=first, anthropic=first, models=urls if models else {})
        client = await aiohttp_client(meter.app(up, path))
        session = aiohttp.ClientSession()
        make.cleanup = [session.close, *(s.close for s in servers.values())]
        return Client(session, str(client.make_url("")), "r1"), path

    yield make
    for close in getattr(make, "cleanup", []):
        await close()


async def test_graph_repairs_only_the_failure_and_routes_by_size(rig):
    client, path = await rig(graph_model, models=["small", "large"])
    records = await enrich.graph(client, "graph", ITEMS, enrich.Models("small", "large"))
    assert set(records) == {"p1", "p2"}
    assert records["p2"]["brand"] == "Bolt" and not enrich.validate(records["p2"])

    recs = list(ledger.read([path]))
    per_item = {i: [r.model for r in recs if r.item == i] for i in ("p1", "p2")}
    assert per_item["p1"] == ["small", "small"], "extract and describe; nothing to repair"
    assert sorted(per_item["p2"]) == ["large", "small", "small"], "plus one repair, on the large model"
    assert {(r.run, r.arm, r.task) for r in recs} == {("r1", "graph", "enrich")}


async def test_agent_loops_until_submitted(rig):
    client, path = await rig(agent_model)
    records, outcomes = await enrich.agents(client, "agent", ITEMS, "m")
    assert records == {"p1": GOOD, "p2": GOOD}
    assert outcomes["p1"].done and outcomes["p1"].turns == 2

    recs = [r for r in ledger.read([path]) if r.item == "p1"]
    assert len(recs) == 2, "one metered request per turn"
    # Turn 2 re-sends turn 1: system, user, the assistant's call and the tool's answer.
    transcript = outcomes["p1"].messages
    assert [m["role"] for m in transcript] == ["system", "user", "assistant", "tool", "assistant", "tool"]
    assert '"valid": false' in transcript[3]["content"]


async def test_agent_that_never_calls_a_tool_stops(rig):
    client, _ = await rig(lambda req: {"role": "assistant", "content": "Done!"})
    records, outcomes = await enrich.agents(client, "agent", ITEMS[:1], "m")
    assert records == {} and outcomes["p1"].reason == "answered without calling a tool"


async def test_agent_bad_tool_call_is_answered_not_fatal(rig):
    def model(req):
        turn = sum(m["role"] == "assistant" for m in req["messages"]) + 1
        if turn == 1:
            call = {"id": "c1", "type": "function", "function": {"name": "submit", "arguments": "{"}}
            return {"role": "assistant", "content": None, "tool_calls": [call]}
        return agent_model({**req, "messages": req["messages"][:2] + [{"role": "assistant"}]})

    client, _ = await rig(model)
    records, outcomes = await enrich.agents(client, "agent", ITEMS[:1], "m")
    assert records == {"p1": GOOD}
    assert outcomes["p1"].messages[3]["content"].startswith("error: no tool named 'submit'")


async def test_agent_turn_limit(rig):
    def model(req):
        call = {"id": "c", "type": "function",
                "function": {"name": "validate_record", "arguments": json.dumps({"record": GOOD})}}  # fmt: skip
        return {"role": "assistant", "content": None, "tool_calls": [call]}

    client, path = await rig(model)
    _, outcomes = await enrich.agents(client, "agent", ITEMS[:1], "m", max_turns=3)
    assert (outcomes["p1"].done, outcomes["p1"].reason, outcomes["p1"].turns) == (False, "turn limit", 3)
    assert len(list(ledger.read([path]))) == 3


def test_cli_score(tmp_path, capsys):
    from avg import cli

    items = tmp_path / "items.jsonl"
    data.write([{"id": it.id, "title": it.title, "bullets": it.bullets, "description": it.description,
                 "gold": it.gold} for it in ITEMS], items)  # fmt: skip
    res = tmp_path / "graph.jsonl"
    res.write_text(
        json.dumps({"arm": "graph", "id": "p1", "record": GOOD}) + "\n"
        + json.dumps({"arm": "graph", "id": "p2", "record": None}) + "\n",
        encoding="utf-8",
    )  # fmt: skip
    out = tmp_path / "scores.json"
    assert cli.main(["score", str(res), "--items", str(items), "--out", str(out)]) == 0
    assert "| graph | 2 | 50% | 50% | 50% | 50% |" in capsys.readouterr().out
    want = {"enrich:graph": {"items": 2, "succeeded": 1, "passed": {"p1": True, "p2": False}}}
    assert json.loads(out.read_text()) == want, "which items passed, so the report can pair arms"


def broken_model(req) -> dict:
    """Never replies with JSON: every item drops out at the attributes."""
    return {"role": "assistant", "content": "I cannot help with that."}


async def test_graph_says_why_an_item_dropped_out(rig):
    client, _ = await rig(broken_model, models=["small", "large"])
    reasons: dict[str, str] = {}
    records = await enrich.graph(client, "graph", ITEMS, enrich.Models("small", "large"), reasons=reasons)
    assert records == {} and reasons == {"p1": "attributes: no usable reply", "p2": "attributes: no usable reply"}


async def test_agents_report_each_item_as_it_finishes(rig):
    client, _ = await rig(agent_model)
    heard: list[tuple[str, bool]] = []
    await enrich.agents(client, "agent", ITEMS, "m", on_done=lambda it, o, record: heard.append((it.id, o.done)))
    assert sorted(heard) == [("p1", True), ("p2", True)]
