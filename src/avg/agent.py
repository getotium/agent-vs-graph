"""The minimal agent loop: the mechanism with nothing hidden.

Send the conversation and the tool schemas; if the model calls tools, run them, append the
results and send the whole conversation again; stop when a tool says the work is done, when the
model answers without calling a tool, or at the turn limit. Every turn re-sends every earlier
turn, which is the cost being measured, so nothing here trims or summarises the history: that
would be a different agent, and a PR that adds one as its own arm is welcome.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .llm import BadToolCall, Client

BAD_CALL = "Your last reply called a tool with arguments that were not valid JSON. Call it again with valid JSON."


@dataclass
class Done:
    """Returned by a tool to end the loop: the agent's work is accepted."""

    message: str
    value: object = None


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema of the arguments
    fn: Callable[..., Awaitable[str | Done]]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


@dataclass
class Outcome:
    done: bool
    value: object = None
    turns: int = 0
    reason: str = ""  # why the loop stopped without being done
    messages: list[dict] = field(default_factory=list)


async def run(
    client: Client,
    arm: str,
    task: str,
    item: str,
    model: str,
    system: str,
    user: str,
    tools: list[Tool],
    max_turns: int = 8,
) -> Outcome:
    by_name = {t.name: t for t in tools}
    schemas = [t.schema() for t in tools]
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for turn in range(1, max_turns + 1):
        try:
            reply = await client.chat(arm, task, item, model, messages, tools=schemas)
        except BadToolCall:
            # The server dropped the reply, so there is no call to answer: say what went wrong, as
            # a tool error would, and let the model try again within the same turn limit.
            messages.append({"role": "user", "content": BAD_CALL})
            continue
        calls = reply.get("tool_calls") or []
        messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls} if calls
                        else {"role": "assistant", "content": reply.get("content") or ""})  # fmt: skip
        if not calls:
            return Outcome(False, turns=turn, reason="answered without calling a tool", messages=messages)
        done: Done | None = None
        for call in calls:
            result = await _call(by_name, call)
            if isinstance(result, Done):
                done, result = result, result.message
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
        if done:
            return Outcome(True, done.value, turns=turn, messages=messages)
    return Outcome(False, turns=max_turns, reason="turn limit", messages=messages)


async def _call(by_name: dict[str, Tool], call: dict) -> str | Done:
    """Run one tool call. A bad call is answered with an error the model can read and fix, as any
    agent framework does, rather than ending the loop."""
    fn = call.get("function") or {}
    tool = by_name.get(fn.get("name", ""))
    if tool is None:
        return f"error: no tool named {fn.get('name')!r}; the tools are {', '.join(by_name)}"
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except json.JSONDecodeError as e:
        return f"error: the arguments are not valid JSON ({e})"
    if not isinstance(args, dict):
        return "error: the arguments must be a JSON object"
    try:
        return await tool.fn(**args)
    except TypeError as e:
        return f"error: wrong arguments for {tool.name}: {e}"
