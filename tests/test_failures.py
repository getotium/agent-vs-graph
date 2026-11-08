"""Failures that are the run's, not the model's: kept apart so a broken run never reads as a
low success rate, and a llama.cpp quirk never costs an agent an item."""

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from avg import agent, ledger, meter
from avg.ledger import Record
from avg.llm import BadToolCall, Client, InfraError, ModelError

CLOSED = "http://127.0.0.1:9"  # the discard port: nothing listens


async def server(handler) -> TestServer:
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    s = TestServer(app)
    await s.start_server()
    return s


async def call(base: str):
    async with aiohttp.ClientSession() as session:
        return await Client(session, base, "r").chat("arm", "t", "i", "m", [{"role": "user", "content": "hi"}])


async def test_unreachable_meter_is_a_broken_run():
    with pytest.raises(InfraError):
        await call(CLOSED)


async def test_meter_marks_an_unreachable_model_server(aiohttp_client, tmp_path):
    path = tmp_path / "ledger.jsonl"
    m = await aiohttp_client(meter.app(meter.Upstreams(openai=CLOSED, anthropic=CLOSED), path))
    resp = await m.post("/t/r/arm/t/i/v1/chat/completions", json={"model": "m", "messages": []})
    assert resp.status == 502 and "X-Avg-Upstream-Down" in resp.headers
    assert not path.exists(), "nothing was billed"
    with pytest.raises(InfraError, match="model server unreachable"):
        await call(str(m.make_url("")))


@pytest.mark.parametrize(
    "text,error",
    [
        ("Failed to parse tool call arguments as JSON: parse error", BadToolCall),
        ("out of memory", ModelError),
    ],
)
async def test_server_errors_are_the_models(text, error):
    async def fail(request):
        return web.Response(status=500, text=text)

    s = await server(fail)
    try:
        with pytest.raises(error) as got:
            await call(str(s.make_url("")).rstrip("/"))
        assert not isinstance(got.value, InfraError)
    finally:
        await s.close()


class Scripted:
    """A client whose replies are scripted: an exception is raised, a dict is returned."""

    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    async def chat(self, arm, task, item, model, messages, tools=None):
        self.seen.append(list(messages))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


async def test_a_dropped_tool_call_costs_a_turn_not_the_item():
    async def submit(record=None):
        return agent.Done("accepted", record)

    tool = agent.Tool("submit", "submit", {"type": "object"}, submit)
    ok = {
        "role": "assistant",
        "tool_calls": [{"id": "c", "function": {"name": "submit", "arguments": '{"record": 1}'}}],
    }
    client = Scripted(BadToolCall("500"), ok)
    out = await agent.run(client, "a", "t", "i", "m", "sys", "user", [tool], max_turns=3)
    assert (out.done, out.value, out.turns) == (True, 1, 2)
    assert client.seen[1][-1] == {"role": "user", "content": agent.BAD_CALL}, "the model is told what went wrong"


async def test_dropped_tool_calls_still_hit_the_turn_limit():
    client = Scripted(*(BadToolCall("500") for _ in range(3)))
    out = await agent.run(client, "a", "t", "i", "m", "sys", "user", [], max_turns=3)
    assert (out.done, out.reason) == (False, "turn limit")


def rec(run: str, arm: str) -> Record:
    return Record(run=run, arm=arm, task="t", item="i", wire="openai", model="m", input=1, cache_read=0,
                  cache_write=0, output=1, latency_ms=1, status=200)  # fmt: skip


def test_drop_removes_one_arm_of_one_run(tmp_path):
    path = tmp_path / "ledger.jsonl"
    for r in (rec("r", "a"), rec("r", "a"), rec("r", "b"), rec("other", "a")):
        ledger.append(path, r)
    assert ledger.arms(path, "r") == {"a", "b"}
    assert ledger.drop(path, "r", "a") == 2
    assert sorted((r.run, r.arm) for r in ledger.read([path])) == [("other", "a"), ("r", "b")]
    assert ledger.arms(tmp_path / "absent.jsonl", "r") == set()
