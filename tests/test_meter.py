"""The meter end to end: a client talks to the meter, the meter to the stub model, and the
ledger must hold exactly what the stub reported, in both wire formats, streamed or not."""

import json

import pytest
from aiohttp.test_utils import TestServer

from avg import ledger, meter, stub


@pytest.fixture
async def rig(aiohttp_client, tmp_path):
    model = TestServer(stub.app("stub-model"))
    await model.start_server()
    base = str(model.make_url("")).rstrip("/")
    path = tmp_path / "ledger.jsonl"
    client = await aiohttp_client(meter.app(meter.Upstreams(openai=base, anthropic=base), path))
    yield client, path
    await model.close()


def records(path):
    return list(ledger.read([path])) if path.exists() else []


@pytest.mark.parametrize(
    "wire,url,body,want",
    [
        (
            "openai",
            "/v1/chat/completions",
            {"model": "m", "messages": [{"role": "user", "content": "hi"}]},
            # prompt_tokens includes the cached ones; the meter separates them.
            {"input": stub.PROMPT - stub.CACHED, "cache_read": stub.CACHED, "cache_write": 0, "output": stub.OUTPUT},
        ),
        (
            "anthropic",
            "/v1/messages",
            {"model": "m", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]},
            {
                "input": stub.PROMPT - stub.CACHED,
                "cache_read": stub.CACHED,
                "cache_write": stub.CACHE_WRITE,
                "output": stub.OUTPUT,
            },
        ),
    ],
)
@pytest.mark.parametrize("stream", [False, True])
async def test_records_usage(rig, wire, url, body, want, stream):
    client, path = rig
    resp = await client.post(f"/t/r1/graph/enrich/item-7{url}", json={**body, "stream": stream})
    assert resp.status == 200
    text = await resp.text()
    assert "ok" in text, "the response passes through to the client"

    [rec] = records(path)
    assert (rec.run, rec.arm, rec.task, rec.item, rec.wire) == ("r1", "graph", "enrich", "item-7", wire)
    assert {
        "input": rec.input,
        "cache_read": rec.cache_read,
        "cache_write": rec.cache_write,
        "output": rec.output,
    } == want
    assert rec.model == "stub-model"
    assert rec.streamed is stream
    [[h, chars]] = rec.extra["prefix"]  # one message: one boundary, hashed, no text kept
    assert len(h) == 16 and chars > 0 and "hi" not in json.dumps(rec.extra)


async def test_unbilled_paths_pass_through_unrecorded(rig):
    client, path = rig
    resp = await client.get("/t/r1/graph/enrich/all/v1/models")
    assert resp.status == 200
    assert (await resp.json())["data"][0]["id"] == "stub-model"
    assert records(path) == []


def test_prepare_asks_a_stream_for_its_usage():
    body, stream = meter.prepare("openai", json.dumps({"stream": True}).encode())
    assert stream and json.loads(body)["stream_options"]["include_usage"] is True
    # Left alone: non-streamed requests, the other wire, and bodies that are not JSON.
    assert meter.prepare("openai", b'{"stream": false}') == (b'{"stream": false}', False)
    assert meter.prepare("anthropic", b'{"stream": true}') == (b'{"stream": true}', True)
    assert meter.prepare("openai", b"not json") == (b"not json", False)


@pytest.mark.parametrize(
    "tail,want",
    [
        ("v1/chat/completions", "openai"),
        ("chat/completions/", "openai"),
        ("v1/messages", "anthropic"),
        ("v1/messages/count_tokens", None),
        ("v1/models", None),
    ],
)
def test_wire_of(tail, want):
    assert meter.wire_of(tail) == want


async def test_routes_chat_completions_by_model(aiohttp_client, tmp_path):
    small, large = TestServer(stub.app("small")), TestServer(stub.app("large"))
    await small.start_server()
    await large.start_server()
    url = {"small": str(small.make_url("")).rstrip("/"), "large": str(large.make_url("")).rstrip("/")}
    path = tmp_path / "ledger.jsonl"
    up = meter.Upstreams(openai=url["large"], anthropic=url["large"], models=url)
    client = await aiohttp_client(meter.app(up, path))
    for model in ("small", "large", "unknown"):
        body = {"model": model, "messages": [{"role": "user", "content": "hi"}]}
        assert (await client.post("/t/r/graph/t/i/v1/chat/completions", json=body)).status == 200
    # The ledger's model is what answered: an unrouted model goes to the default upstream.
    assert [r.model for r in records(path)] == ["small", "large", "large"]
    await small.close()
    await large.close()


def test_model_of():
    assert meter.model_of(b'{"model": "m"}') == "m"
    assert meter.model_of(b"[1]") == "" and meter.model_of(b"nope") == ""
