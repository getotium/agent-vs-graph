"""Catalog intake: building the mixes, scoring skips and records, the graph's early exits, the
agent's shared store, the harness's workspace and the plans. No network: a stub plays the model."""

import json
import subprocess
import sys
from dataclasses import replace

import aiohttp
import pytest
from aiohttp.test_utils import TestServer

from avg import data, harness, ledger, meter, serial, stub
from avg.llm import Client
from avg.scores import score_files
from avg.tasks import enrich, intake, record

POLICY = {"excluded_brands": ["Nope"], "excluded_kinds": ["books"]}
LONG = (
    "Every kitchen deserves dependable gear, and this one earns its place on the counter through careful "
    "construction and thoughtful details that make daily routines simpler for busy households everywhere. "
) * 6  # 168 words of prose no listing below contains
FULL = {
    "category": "Home & Kitchen",
    "brand": "Acme",
    "color": "Red",
    "specs": {"material": "steel"},
    "description": " ".join(["word"] * 20),
    "seo_title": "Acme Kettle, Red Steel",
    "meta_description": "A red steel kettle from Acme that heats water quickly on any stovetop, made for "
    "everyday kitchen use and for easy cleaning.",
    "long_description": LONG.strip(),
}


def item(i, title, kind="new", brand="Acme", group=None, bullets="Steel body", desc=""):
    gold = {"brand": brand, "color": "Red", "kind": kind}
    if group:
        gold["group"] = group
    return enrich.Item(i, title, bullets, desc, gold)


def test_the_full_record_is_valid_and_content_faults_name_their_key():
    it = item("p1", "Acme kettle")
    assert intake.check(FULL, it) == []
    errs = intake.check({**FULL, "seo_title": "x" * 61, "meta_description": "too short"}, it)
    assert [e.split(" ", 1)[0] for e in errs] == ["seo_title", "meta_description"], errs
    assert enrich.Item("p", "t", "b", "", {}).check({k: v for k, v in FULL.items() if k in record.KEYS}) == [], \
        "task 1's record is unchanged"  # fmt: skip


# ---- the data ----------------------------------------------------------------------------------


def pooled(brand: str, k: int) -> dict:
    return {"id": f"{brand}{k}", "title": f"{brand} Widget Model {k}, Large - Blue",
            "bullets": f"First fact {k}\nSecond fact\nThird fact", "description": "A widget.",
            "gold": {"brand": brand, "color": "Blue"}}  # fmt: skip


def test_a_relisting_keeps_the_facts_and_changes_the_words():
    import random

    it = pooled("Acme", 1)
    r = data.relist(it, random.Random(1))
    assert r["title"] != it["title"] and "Acme" in r["title"] and "Model 1" in r["title"]
    assert r["bullets"].splitlines() == list(reversed(it["bullets"].splitlines()))
    assert r["description"] == "", "dropped when there are bullets"


def test_the_mixes_have_their_shares_opaque_ids_and_no_mention_of_excluded_brands():
    pool = [pooled(f"B{b:03d}", k) for b in range(400) for k in range(14)]
    pool.append({**pooled("B001", 99), "title": "B001 case that fits ZZZ phones"})  # names a brand
    books = [{"id": f"{k:09d}X", "title": f"A Novel {k}", "bullets": "", "description": "A story.",
              "gold": {"brand": "Press", "color": ""}} for k in range(200)]  # fmt: skip
    out = data.intake(pool, books, n=200, seed=3)
    assert out == data.intake(pool, books, n=200, seed=3), "seeded: the same files every time"
    excluded = out["policy.json"]["excluded_brands"]
    assert len(excluded) == data.EXCLUDED_BRANDS
    for suffix, share in data.MIXES.items():
        items = out[f"items-{suffix}.jsonl"]
        kinds = [it["gold"]["kind"] for it in items]
        assert len(items) == 200 and sum(k != "new" for k in kinds) == round(200 * share)
        assert all(it["id"].startswith("p") and len(it["id"]) == 9 for it in items), "no ISBN or ASIN shows"
        catalog_titles = {c["title"] for c in out[f"catalog-{suffix}.jsonl"]}
        for it in items:
            if it["gold"]["kind"] == "catalog_duplicate":
                assert it["gold"]["source"] in {p["id"] for p in pool}
                assert any(it["gold"]["brand"] in t for t in catalog_titles), "its original is in the catalog"
            if it["gold"]["kind"] != "excluded_brand":
                assert it["gold"]["brand"] not in excluded
        groups = {}
        for it in items:
            if "group" in it["gold"]:
                groups.setdefault(it["gold"]["group"], []).append(it["gold"]["kind"])
        assert groups and all(g.count("new") == 1 and len(g) >= 2 for g in groups.values())


# ---- scoring -----------------------------------------------------------------------------------


def test_skips_records_and_feed_groups_are_scored():
    items = [
        item("n1", "Acme kettle"),
        item("n2", "Acme pot"),
        item("d1", "Acme pan", kind="catalog_duplicate"),
        item("x1", "Nope mug", kind="excluded_brand", brand="Nope"),
        item("g1", "Acme lid", group="g"),
        item("g2", "Lid by Acme", kind="feed_duplicate", group="g"),
    ]
    rows = {
        "n1": {"record": FULL},
        "n2": {"skip": "duplicate"},  # a new product skipped: wrong
        "d1": {"skip": "duplicate"},
        "x1": {"record": FULL},  # content written for a reject
        "g1": {"record": FULL},
        "g2": {"skip": "duplicate"},
    }
    s = intake.score(items, rows)
    assert s.passed == {"n1": True, "n2": False, "d1": True, "x1": False, "g1": True, "g2": True}
    assert s.records_for_rejects == 1
    both = intake.score(items, {**rows, "g2": {"record": FULL}})
    assert not both.passed["g1"] and not both.passed["g2"], "two records for one product fail every listing"
    assert both.records_for_rejects == 2
    assert not intake.score(items, {**rows, "d1": {}}).passed["d1"], "a reject needs a skip, not silence"


def test_score_files_tells_intake_by_its_gold(tmp_path):
    items = [item("n1", "Acme kettle"), item("x1", "Nope mug", kind="excluded_brand", brand="Nope")]
    (tmp_path / "items.jsonl").write_text("".join(json.dumps(it.__dict__) + "\n" for it in items))
    (tmp_path / "a.jsonl").write_text(json.dumps({"arm": "a", "id": "n1", "record": FULL, "skip": None}) + "\n"
                                      + json.dumps({"arm": "a", "id": "x1", "record": None, "skip": "excluded"}) + "\n")  # fmt: skip
    table, counts = score_files(tmp_path / "items.jsonl", [tmp_path / "a.jsonl"])
    assert "Records for rejects" in table
    assert counts["intake:a"]["succeeded"] == 2 and counts["intake:a"]["kinds"] == {"n1": "new", "x1": "excluded_brand"}


# ---- the graph ---------------------------------------------------------------------------------

CATALOG = [{"sku": "C1", "brand": "Acme", "title": "Acme Saucepan 2 qt, Steel", "color": "Red"},
           {"sku": "C2", "brand": "Acme", "title": "Acme Kettle 1.7 L", "color": "Red"}]  # fmt: skip
FEED = [
    item("n1", "Acme Stock Pot 8 qt"),  # new, though Acme has catalog entries
    item("d1", "Saucepan 2 qt, Steel - Acme", kind="catalog_duplicate"),
    item("x1", "Nope Coffee Mug", kind="excluded_brand", brand="Nope"),
    item("b1", "The Long Novel", kind="excluded_kind", brand="Press"),
    item("g1", "Acme Steamer Basket", group="g"),
    item("g2", "Steamer Basket - Acme", kind="feed_duplicate", group="g"),
]


def system(req) -> str:
    return req["messages"][0]["content"]


def intake_model(req) -> dict:
    sys_, user = system(req), req["messages"][-1]["content"]
    if sys_ == intake.EXTRACT:
        title = user.split("\n")[0]
        brand = "Nope" if "Nope" in title else "Press" if "Novel" in title else "Acme"
        category = intake.BOOKS if "Novel" in title else "Home & Kitchen"
        attrs = {"category": category, "brand": brand, "color": "Red", "specs": {"material": "steel"}, "model": None}
        return {"role": "assistant", "content": json.dumps(attrs)}
    if sys_ == intake.COMPARE:
        new = user.split("Products:")[0]
        products = user.split("Products:")[1].strip().splitlines()
        for k, p in enumerate(products, 1):
            if ("Saucepan" in new and "Saucepan" in p) or ("Steamer" in new and "Steamer" in p):
                return {"role": "assistant", "content": str(k)}
        return {"role": "assistant", "content": "0"}
    if sys_ == intake.WRITE:
        return {"role": "assistant", "content": json.dumps({k: FULL[k] for k in intake._WRITTEN})}
    raise AssertionError(f"unexpected prompt: {sys_[:40]}")


@pytest.fixture
async def client(aiohttp_client, tmp_path):
    server = TestServer(stub.app("m", intake_model))
    await server.start_server()
    path = tmp_path / "ledger.jsonl"
    url = str(server.make_url("")).rstrip("/")
    m = await aiohttp_client(meter.app(meter.Upstreams(openai=url, anthropic=url), path))
    session = aiohttp.ClientSession()
    yield Client(session, str(m.make_url("")), "r1"), path
    await session.close()
    await server.close()


async def test_the_graph_stops_rejects_before_their_content(client):
    c, path = client
    got = await intake.graph(c, "graph", FEED, enrich.Models("m", "m"), CATALOG, POLICY)
    assert {i: r.get("skip") or "record" for i, r in got.items()} == {
        "n1": "record", "d1": "duplicate", "x1": "excluded", "b1": "excluded", "g1": "record", "g2": "duplicate",
    }  # fmt: skip
    s = intake.score(FEED, got)
    assert all(s.passed.values()), s.passed
    steps = {}
    for r in ledger.read([path]):
        steps.setdefault(r.item, 0)
        steps[r.item] += 1
    assert steps["x1"] == steps["b1"] == 1, "a rule stops it after extract: one request, no content"
    assert steps["d1"] == 2 and steps["g2"] == 2, "extract and compare, no content"
    assert steps["n1"] == 3, "extract, compare (Acme has entries), write"


# ---- the agent's tools -------------------------------------------------------------------------


async def test_the_store_answers_by_brand_and_learns_what_agents_accept():
    store = intake.Store(CATALOG)
    results: dict = {}
    t = {x.name: x for x in intake.tools(store, results, FEED[4])}
    assert [p["sku"] for p in json.loads(await t["lookup_catalog"].fn(brand="ACME"))["products"]] == ["C1", "C2"]
    assert json.loads(await t["lookup_catalog"].fn(brand=""))["products"] == []
    bad = await t["skip_item"].fn(reason="dunno")
    assert "reason must be one of" in bad and "g1" not in results
    done = await t["submit_record"].fn(record=FULL)
    assert done.value == FULL and results["g1"] == {"record": FULL}
    assert store.lookup("Acme")[-1]["sku"] == "new:g1", "the next agent sees it"
    skip = await intake.tools(store, results, FEED[5])[1].fn(reason="duplicate")
    assert skip.message and results["g2"] == {"skip": "duplicate"}


# ---- the harness and the plans -----------------------------------------------------------------


def test_the_intake_workspace_takes_skips_and_records(tmp_path):
    ws = harness.intake_workspace(tmp_path / "ws", FEED[:2], CATALOG, POLICY)
    assert sorted(p.name for p in ws.iterdir()) == ["TASK.md", "catalog.jsonl", "products.jsonl", "record.py",
                                                   "validate.py"]  # fmt: skip
    task = (ws / "TASK.md").read_text(encoding="utf-8")
    assert "Nope" in task and '"skip": "duplicate"' in task and "seo_title" in task
    assert "catalog_duplicate" not in (ws / "products.jsonl").read_text(encoding="utf-8"), "no gold"
    run = lambda: subprocess.run([sys.executable, "validate.py"], cwd=ws, capture_output=True, text=True, check=False)
    assert "n1: missing" in run().stdout
    (ws / "records.jsonl").write_text(json.dumps({"id": "n1", "record": FULL}) + "\n"
                                      + json.dumps({"id": "d1", "skip": "duplicate"}) + "\n")  # fmt: skip
    ok = run()
    assert ok.returncode == 0, ok.stdout
    assert harness.collect_rows(ws) == {"n1": {"record": FULL}, "d1": {"skip": "duplicate"}}


def test_intake_plans_carry_the_mix_and_leave_out_task_1_variants():
    cfg = serial.Config(run="r", limit=5, llama_server="ls", device="", small=serial.Server("s", "s.gguf", 1),
                        large=serial.Server("l", "l.gguf", 2), large_harness=serial.Server("l", "l.gguf", 2),
                        thinking=3072, task="intake", items="data/intake/items-20.jsonl")  # fmt: skip
    steps = {s.arm: s for s in serial.plan(cfg)}
    assert "graph-12b-lean" not in steps
    argv = steps["graph-12b"].argv
    assert argv[argv.index("--task") + 1] == "intake" and argv[argv.index("--items") + 1].endswith("items-20.jsonl")
    hosted = serial.hosted_plan(serial.hosted_config("h", 5, 4, 8788, *serial.intake_items(85)), "m", "default")
    assert [s.arm for s in hosted] == ["graph-haiku", "agent-haiku", "claude-code-haiku"]
    assert all("data/intake/items-85.jsonl" in s.argv for s in hosted)
    task1 = serial.plan(replace(cfg, task="enrich"))
    assert "--task" not in task1[0].argv, "task 1's commands are as they were"
