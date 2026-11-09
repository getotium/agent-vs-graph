"""The one way our own runners (the graph and the minimal agent loop) call a model, through the
meter, with the request labelled by run, arm, task and item.

Two wires. Local models get OpenAI chat completions. A hosted Anthropic model gets the native
Messages API, so its prompt caching can be used the way an Anthropic customer would use it; the
runners still speak in OpenAI-shaped messages and tool calls, translated here both ways.

The harness arms (Claude Code, Hermes Agent) do not use this; they are pointed at the same meter
by base URL and make their own requests.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

import aiohttp


class ModelError(RuntimeError):
    """The model refused or failed a request: counted against the item."""


class BadToolCall(ModelError):
    """The model wrote a tool call whose arguments are not JSON, and llama-server refused the whole
    reply (a 500) instead of returning the call. A hosted API returns it and the loop recovers, so
    the agent treats this as a failed turn, not a failed item."""


class InfraError(RuntimeError):
    """The meter or the model server could not be reached: the run is broken, not the item. Never
    caught per item, so a crash stops the arm loudly instead of reading as a low success rate."""


# The meter's mark on a response it made itself because the upstream did not answer.
UPSTREAM_DOWN = "X-Avg-Upstream-Down"


ANTHROPIC_API = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
KEY_ENV = "ANTHROPIC_API_KEY"  # where a hosted run's key comes from: the environment, never a flag
# Anthropic statuses that mean "try again shortly", not "this request is wrong": rate limited,
# server error, overloaded. Retried with the server's retry-after, so a busy minute never reads as
# a failed item. The meter still records each refusal.
RETRY = {429, 500, 529}


@dataclass
class Client:
    session: aiohttp.ClientSession
    meter: str  # e.g. http://127.0.0.1:8787
    run: str
    # One cap for every request of every arm. Generous, because a thinking model's reasoning counts
    # against it: at 2,048, Gemma 4 12B ran out mid-thought on some agent turns and answered with
    # neither text nor a tool call, a failure of the cap rather than of the agent.
    max_tokens: int = 4096
    wire: str = "openai"  # or "anthropic": the native Messages API
    api_key: str = ""  # anthropic: sent to the meter, which passes it on; never recorded
    # anthropic: where the prompt is marked for caching. "system" marks the shared system prompt
    # (and the tools before it); "conversation" also turns on automatic caching of the growing
    # message history, the documented pattern for agent loops.
    cache: str = "system"
    # anthropic: "off" sends thinking disabled; "default" leaves the model's own default (Haiku
    # 5.5: adaptive thinking at medium effort).
    thinking: str = "off"
    tries: int = 6
    backoff_s: float = 2.0  # the first wait when the server gives no retry-after; doubles each time

    def url(self, arm: str, task: str, item: str) -> str:
        path = "v1/messages" if self.wire == "anthropic" else "v1/chat/completions"
        return f"{self.meter.rstrip('/')}/t/{self.run}/{arm}/{task}/{item}/{path}"

    async def chat(
        self,
        arm: str,
        task: str,
        item: str,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        think: bool = True,
    ) -> dict:
        """One request; returns the assistant message in OpenAI's shape. Locally, temperature 0 so
        reruns are comparable; a hosted Anthropic model takes only its default sampling. `think`
        False turns thinking off for this request whatever the run's condition: a graph can choose
        per step."""
        if self.wire == "anthropic":
            thinking = self.thinking if think else "off"
            body = to_anthropic(model, messages, tools, self.max_tokens, self.cache, thinking)
            headers = {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION}
            return from_anthropic(await self._post(self.url(arm, task, item), body, headers))
        body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": self.max_tokens}
        if tools:
            body["tools"] = tools
        if not think:
            # llama.cpp hands this to the chat template; Gemma 4's switches its thinking phase on it.
            body["chat_template_kwargs"] = {"enable_thinking": False}
        data = await self._post(self.url(arm, task, item), body, {})
        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise ModelError(f"no message in response: {str(data)[:300]}") from e

    async def _post(self, url: str, body: dict, headers: dict) -> dict:
        wait = self.backoff_s
        for attempt in range(1, self.tries + 1):
            try:
                async with self.session.post(url, json=body, headers=headers) as resp:
                    if resp.status < 400:
                        return await resp.json()
                    text = (await resp.text())[:300]
                    if UPSTREAM_DOWN in resp.headers:
                        raise InfraError(f"model server unreachable: {text}")
                    if self.wire == "openai" and resp.status == 500 and "parse tool call arguments" in text:
                        raise BadToolCall(text)
                    if resp.status in (401, 403) and self.wire == "anthropic":
                        raise InfraError(f"the API refused the key ({resp.status}): {text}")
                    if self.wire == "anthropic" and resp.status in RETRY and attempt < self.tries:
                        after = resp.headers.get("retry-after", "")
                        await asyncio.sleep(float(after) if after.replace(".", "", 1).isdigit() else wait)
                        wait *= 2
                        continue
                    raise ModelError(f"{resp.status}: {text}")
            except (TimeoutError, aiohttp.ClientConnectionError, aiohttp.ClientPayloadError) as e:
                raise InfraError(f"meter unreachable: {e!r}") from e
        raise ModelError("unreachable")  # the loop always returns or raises


def to_anthropic(
    model: str, messages: list[dict], tools: list[dict] | None, max_tokens: int, cache: str, thinking: str = "off"
) -> dict:
    """An OpenAI-shaped conversation as a Messages request. Thinking "off" is sent explicitly,
    since Claude Haiku 5.5 thinks by default; "default" sends nothing and lets it."""
    system = [m["content"] for m in messages if m["role"] == "system"]
    out: list[dict] = []

    def add(role: str, block: dict) -> None:
        # Consecutive same-role blocks share one message: tool results follow a tool use as one
        # user turn, as the API requires.
        if out and out[-1]["role"] == role:
            out[-1]["content"].append(block)
        else:
            out.append({"role": role, "content": [block]})

    for m in messages:
        if m["role"] == "user":
            add("user", {"type": "text", "text": m["content"]})
        elif m["role"] == "tool":
            add("user", {"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""), "content": m["content"]})
        elif m["role"] == "assistant":
            if m.get("content"):
                add("assistant", {"type": "text", "text": m["content"]})
            for call in m.get("tool_calls") or []:
                fn = call.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                add("assistant", {"type": "tool_use", "id": call.get("id", ""), "name": fn.get("name", ""),
                                  "input": args if isinstance(args, dict) else {}})  # fmt: skip
    body: dict = {"model": model, "max_tokens": max_tokens, "messages": out}
    if thinking == "off":
        body["thinking"] = {"type": "disabled"}
    if system:
        body["system"] = [{"type": "text", "text": "\n\n".join(system), "cache_control": {"type": "ephemeral"}}]
    if tools:
        body["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                          "input_schema": t["function"].get("parameters") or {"type": "object"}}
                         for t in tools]  # fmt: skip
    if cache == "conversation":
        body["cache_control"] = {"type": "ephemeral"}
    return body


def from_anthropic(data: dict) -> dict:
    """A Messages response as an OpenAI-shaped assistant message."""
    if data.get("stop_reason") == "refusal":
        raise ModelError("the model refused")
    blocks = data.get("content")
    if not isinstance(blocks, list):
        raise ModelError(f"no content in response: {str(data)[:300]}")
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    calls = [{"id": b.get("id", ""), "type": "function",
              "function": {"name": b.get("name", ""), "arguments": json.dumps(b.get("input") or {})}}
             for b in blocks if b.get("type") == "tool_use"]  # fmt: skip
    msg: dict = {"role": "assistant", "content": text or None}
    if calls:
        msg["tool_calls"] = calls
    return msg


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json(text: str | None) -> dict | None:
    """The JSON object in a model's reply, tolerating a code fence or prose around it; None if
    there is no object to be had. Small models wrap JSON in fences however they are asked."""
    if not text:
        return None
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        v = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return v if isinstance(v, dict) else None
