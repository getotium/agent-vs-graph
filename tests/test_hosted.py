"""Hosted runs: our arms on Anthropic's native Messages API, Claude Code against the hosted API, and
the vendor's own counts used as the bill. No network: a stand-in plays the API."""

from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from avg import agent, cli, harness, prices, report, serial
from avg.ledger import Record
from avg.llm import Client, InfraError, ModelError, from_anthropic, to_anthropic

SHEET = Path(__file__).parent.parent / "prices" / "default.yaml"
TOOL = {"type": "function", "function": {"name": "submit", "description": "Submit.", "parameters": {"type": "object"}}}


def test_a_conversation_becomes_a_messages_request():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "listing"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "function": {"name": "submit", "arguments": '{"record": 1}'}},
            {"id": "c2", "function": {"name": "submit", "arguments": "not json"}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        {"role": "tool", "tool_call_id": "c2", "content": "bad"},
    ]  # fmt: skip
    body = to_anthropic("m", messages, [TOOL], 4096, "system")
    assert body["system"] == [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}]
    assert body["thinking"] == {"type": "disabled"}, "the hosted runs are the thinking-off condition"
    assert "temperature" not in body, "Haiku 5.5 refuses non-default sampling"
    assert "cache_control" not in body, "a graph step caches only its shared system prompt"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert body["messages"][1]["content"] == [
        {"type": "tool_use", "id": "c1", "name": "submit", "input": {"record": 1}},
        {"type": "tool_use", "id": "c2", "name": "submit", "input": {}},
    ]
    assert [b["tool_use_id"] for b in body["messages"][2]["content"]] == ["c1", "c2"], "results share one user turn"
    assert body["tools"] == [{"name": "submit", "description": "Submit.", "input_schema": {"type": "object"}}]
    assert to_anthropic("m", messages, None, 4096, "conversation")["cache_control"] == {"type": "ephemeral"}


def test_a_messages_reply_becomes_an_assistant_message():
    reply = {"stop_reason": "tool_use", "content": [
        {"type": "text", "text": "Checking."},
        {"type": "tool_use", "id": "t1", "name": "submit", "input": {"record": {"a": 1}}},
    ]}  # fmt: skip
    msg = from_anthropic(reply)
    assert msg["content"] == "Checking."
    assert msg["tool_calls"] == [
        {"id": "t1", "type": "function", "function": {"name": "submit", "arguments": '{"record": {"a": 1}}'}}
    ]
    assert from_anthropic({"content": [{"type": "text", "text": "{}"}]}) == {"role": "assistant", "content": "{}"}
    with pytest.raises(ModelError, match="refused"):
        from_anthropic({"stop_reason": "refusal", "content": []})


class FakeAPI:
    """Plays the Messages API: answers with `replies` in order; an int is an error status."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    async def handle(self, request):
        self.requests.append((request.path, dict(request.headers), await request.json()))
        r = self.replies.pop(0)
        if isinstance(r, int):
            return web.json_response({"type": "error"}, status=r, headers={"retry-after": "0"})
        return web.json_response(r)


async def serve(api: FakeAPI) -> TestServer:
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", api.handle)
    s = TestServer(app)
    await s.start_server()
    return s


async def test_the_agent_loop_runs_on_the_messages_api():
    submit = {"content": [{"type": "tool_use", "id": "t1", "name": "submit", "input": {"record": 7}}]}
    api = FakeAPI(429, submit)  # rate limited once, then answered
    s = await serve(api)

    async def tool_fn(record=None):
        return agent.Done("accepted", record)

    try:
        async with aiohttp.ClientSession() as session:
            client = Client(session, str(s.make_url("")).rstrip("/"), "r", wire="anthropic", api_key="sk-test",
                            cache="conversation", backoff_s=0)  # fmt: skip
            out = await agent.run(client, "agent-haiku", "t", "i", "claude-haiku-5-5", "sys", "go",
                                  [agent.Tool("submit", "Submit.", {"type": "object"}, tool_fn)])  # fmt: skip
    finally:
        await s.close()
    assert (out.done, out.value) == (True, 7)
    assert len(api.requests) == 2, "the 429 was retried, not counted against the item"
    path, headers, body = api.requests[-1]
    assert path == "/t/r/agent-haiku/t/i/v1/messages"
    assert headers["x-api-key"] == "sk-test" and headers["anthropic-version"] == "2023-06-01"
    assert body["cache_control"] == {"type": "ephemeral"}, "an agent caches its growing conversation"


@pytest.mark.parametrize("status,error", [(401, InfraError), (400, ModelError)])
async def test_a_refused_key_breaks_the_run_and_a_bad_request_fails_the_item(status, error):
    s = await serve(FakeAPI(status))
    try:
        async with aiohttp.ClientSession() as session:
            client = Client(session, str(s.make_url("")).rstrip("/"), "r", wire="anthropic", api_key="k")
            with pytest.raises(error):
                await client.chat("a", "t", "i", "m", [{"role": "user", "content": "hi"}])
    finally:
        await s.close()


def test_claude_code_runs_only_where_its_thinking_matches_the_condition():
    cfg = serial.hosted_config("h1", 50, 4, 8788)
    off = serial.hosted_plan(cfg, "claude-haiku-5-5", "off")
    assert [s.arm for s in off] == ["graph-haiku", "agent-haiku"], "Claude Code cannot turn thinking off"
    shipped = serial.hosted_plan(cfg, "claude-haiku-5-5", "default")
    assert [s.arm for s in shipped] == [
        "graph-haiku",
        "graph-haiku-lean",
        "agent-haiku",
        "claude-code-haiku",
        "claude-code-skill-haiku",
    ]
    assert shipped[0].argv[shipped[0].argv.index("--thinking") + 1] == "default"
    lean = shipped[1].argv
    assert lean[lean.index("--no-thinking") + 1] == "describe" and "--no-thinking" not in shipped[0].argv


@pytest.mark.parametrize("wire,reply", [
    ("anthropic", {"content": [{"type": "text", "text": "ok"}]}),
    ("openai", {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}),
])  # fmt: skip
async def test_one_request_can_turn_thinking_off(wire, reply):
    api = FakeAPI(reply, reply)
    s = await serve(api)
    try:
        async with aiohttp.ClientSession() as session:
            client = Client(session, str(s.make_url("")).rstrip("/"), "r", wire=wire, api_key="k", thinking="default")
            msgs = [{"role": "user", "content": "hi"}]
            await client.chat("a", "t", "i", "m", msgs)
            await client.chat("a", "t", "i", "m", msgs, think=False)
    finally:
        await s.close()
    (_, _, thinks), (_, _, quiet) = api.requests
    if wire == "anthropic":
        assert "thinking" not in thinks and quiet["thinking"] == {"type": "disabled"}
    else:
        assert "chat_template_kwargs" not in thinks
        assert quiet["chat_template_kwargs"] == {"enable_thinking": False}, "the template's switch, per request"


def test_thinking_off_is_sent_and_the_default_is_left_alone():
    msgs = [{"role": "user", "content": "hi"}]
    assert to_anthropic("m", msgs, None, 10, "system", "off")["thinking"] == {"type": "disabled"}
    assert "thinking" not in to_anthropic("m", msgs, None, 10, "system", "default")


def test_thinking_tokens_are_recorded_when_the_server_reports_them():
    from avg import usage

    a = usage.from_anthropic({"usage": {"output_tokens": 300, "output_tokens_details": {"thinking_tokens": 200}}})
    o = usage.from_openai({"usage": {"completion_tokens": 50, "completion_tokens_details": {"reasoning_tokens": 0}}})
    assert (a.output, a.thinking, o.thinking) == (300, 200, 0), "zero is reported, not missing"
    assert usage.from_openai({"usage": {"completion_tokens": 50}}).thinking == -1, "not reported"

    def rec(item, extra):
        return Record(run="r", arm="a", task="t", item=item, wire="anthropic", model="m", input=1, cache_read=0,
                      cache_write=0, output=300, latency_ms=1, status=200, extra=extra)  # fmt: skip

    [g] = report.group([rec("x", {"thinking": 200}), rec("y", {"thinking": 100})])
    assert g.thinking_per_item() == 150
    [partial] = report.group([rec("x", {"thinking": 200}), rec("y", {})])
    assert partial.thinking_per_item() is None, "a partial count would read as a low one"


def test_the_hosted_plan_needs_no_servers_and_never_carries_the_key():
    steps = serial.hosted_plan(serial.hosted_config("h1", 50, 4, 8788), "claude-haiku-5-5", "default")
    assert all(s.servers == [] for s in steps)
    assert "--wire" in steps[0].argv and "--hosted" in steps[-1].argv and "--skill" in steps[-1].argv
    assert all("http://127.0.0.1:8788" in s.argv for s in steps), "its own meter port, clear of a local run's"
    assert not any(a.startswith("sk-") for s in steps for a in s.argv)


def test_hosted_claude_code_uses_the_key_and_only_the_key(tmp_path):
    inv = harness.claude_code(tmp_path, "http://m", "claude-haiku-5-5", 10, api_key="sk-test")
    assert inv.env["ANTHROPIC_API_KEY"] == "sk-test" and "ANTHROPIC_AUTH_TOKEN" not in inv.env
    local = harness.claude_code(tmp_path, "http://m", "gemma", 10)
    assert local.env["ANTHROPIC_AUTH_TOKEN"] == "local" and "ANTHROPIC_API_KEY" not in local.env
    assert "sk-test" not in " ".join(inv.argv)
    assert (harness.harness_of("claude-code-haiku"), harness.harness_of("agent-haiku")) == ("claude-code", "")


def test_a_hosted_run_needs_the_key_in_the_environment(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        cli.main(["hosted", "--run", "h1"])


def test_the_vendors_own_count_is_the_bill():
    haiku = prices.load(SHEET)["claude-haiku-5-5"]

    def rec(model, cache_read, cache_write):
        return Record(run="r", arm="agent-haiku", task="t", item="a", wire="anthropic", model=model, input=100,
                      cache_read=cache_read, cache_write=cache_write, output=10, latency_ms=1, status=200)  # fmt: skip

    [g] = report.group([rec("claude-haiku-5-5", 900, 50)])
    units, unknown = g.billed(haiku)
    assert (units["a"][0].cache_read, units["a"][0].cache_write, unknown) == (900, 50, 0), "taken as recorded"
    [local] = report.group([rec("gemma-4-12b", 900, 50)])
    units, unknown = local.billed(haiku)
    assert units["a"][0].cache_read == 0 and unknown == 1, "a local model's cache hits are not Anthropic's"
    md = report.render([g], [haiku], set(), [1_000])
    assert "answered by claude-haiku-5-5 itself" in md
