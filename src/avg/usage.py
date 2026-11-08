"""Token usage read from model responses, in both wire formats.

Every arm talks to its model through the meter, and the meter needs one thing from each
response: how many tokens it cost. OpenAI-style and Anthropic-style APIs report that
differently, and differently again when streaming, so the parsing lives here as pure functions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class Usage:
    """Tokens one request cost. `input` is new input only: cached reads and cache writes are
    counted separately because they are priced separately."""

    input: int = 0
    cache_read: int = 0
    cache_write: int = 0
    output: int = 0
    model: str = ""

    @property
    def prompt(self) -> int:
        """Every input token the model read, however it was priced."""
        return self.input + self.cache_read + self.cache_write


def from_openai(body: dict) -> Usage:
    """A chat-completions response, or the last chunk of a stream with usage included.

    OpenAI's prompt_tokens includes cached tokens; they are moved out of `input` here.
    llama.cpp reports cache hits the same way when it reports them at all.
    """
    u = body.get("usage") or {}
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
    return Usage(
        input=max((u.get("prompt_tokens") or 0) - cached, 0),
        cache_read=cached,
        output=u.get("completion_tokens") or 0,
        model=body.get("model") or "",
    )


def from_anthropic(body: dict) -> Usage:
    """A Messages response. Anthropic's input_tokens already excludes cache reads and writes."""
    u = body.get("usage") or {}
    return Usage(
        input=u.get("input_tokens") or 0,
        cache_read=u.get("cache_read_input_tokens") or 0,
        cache_write=u.get("cache_creation_input_tokens") or 0,
        output=u.get("output_tokens") or 0,
        model=body.get("model") or "",
    )


def _events(sse: bytes):
    """The JSON payloads of a server-sent event stream, skipping anything that is not JSON."""
    for line in sse.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if not data or data == "[DONE]":
            continue
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def from_openai_stream(sse: bytes) -> Usage:
    """The usage of a streamed chat completion: the last chunk that carries a usage object.

    OpenAI sends it only when the request asks (stream_options.include_usage), which the meter
    adds to every streamed request it forwards.
    """
    usage, model = Usage(), ""
    for ev in _events(sse):
        model = ev.get("model") or model
        if ev.get("usage"):
            usage = from_openai(ev)
    usage.model = usage.model or model
    return usage


def from_anthropic_stream(sse: bytes) -> Usage:
    """The usage of a streamed Messages response.

    message_start carries the input side; message_delta carries the output count (cumulative,
    so the last one wins) and, on some servers, a restated input side.
    """
    usage = Usage()
    for ev in _events(sse):
        kind = ev.get("type")
        if kind == "message_start":
            msg = ev.get("message") or {}
            usage = from_anthropic(msg)
        elif kind == "message_delta":
            u = ev.get("usage") or {}
            usage.output = u.get("output_tokens", usage.output) or usage.output
            for src, dst in (
                ("input_tokens", "input"),
                ("cache_read_input_tokens", "cache_read"),
                ("cache_creation_input_tokens", "cache_write"),
            ):
                if u.get(src):
                    setattr(usage, dst, u[src])
    return usage
