"""The one way our own runners (the graph and the minimal agent loop) call a model: OpenAI chat
completions, through the meter, with the request labelled by run, arm, task and item.

The harness arms (Claude Code, Hermes Agent) do not use this; they are pointed at the same meter
by base URL and make their own requests.
"""

from __future__ import annotations

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


@dataclass
class Client:
    session: aiohttp.ClientSession
    meter: str  # e.g. http://127.0.0.1:8787
    run: str
    # One cap for every request of every arm. Generous, because a thinking model's reasoning counts
    # against it: at 2,048, Gemma 4 12B ran out mid-thought on some agent turns and answered with
    # neither text nor a tool call, a failure of the cap rather than of the agent.
    max_tokens: int = 4096

    def url(self, arm: str, task: str, item: str) -> str:
        return f"{self.meter.rstrip('/')}/t/{self.run}/{arm}/{task}/{item}/v1/chat/completions"

    async def chat(
        self,
        arm: str,
        task: str,
        item: str,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        """One request; returns the assistant message. Temperature 0 so reruns are comparable."""
        body: dict = {"model": model, "messages": messages, "temperature": 0, "max_tokens": self.max_tokens}
        if tools:
            body["tools"] = tools
        try:
            async with self.session.post(self.url(arm, task, item), json=body) as resp:
                if resp.status >= 400:
                    text = (await resp.text())[:300]
                    if UPSTREAM_DOWN in resp.headers:
                        raise InfraError(f"model server unreachable: {text}")
                    if resp.status == 500 and "parse tool call arguments" in text:
                        raise BadToolCall(text)
                    raise ModelError(f"{resp.status}: {text}")
                data = await resp.json()
        except (TimeoutError, aiohttp.ClientConnectionError, aiohttp.ClientPayloadError) as e:
            raise InfraError(f"meter unreachable: {e!r}") from e
        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise ModelError(f"no message in response: {str(data)[:300]}") from e


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
