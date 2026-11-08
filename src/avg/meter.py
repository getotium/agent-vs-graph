"""The meter: a pass-through proxy that writes every model request's token usage to the ledger.

Each arm (our own loop, a harness such as Claude Code or Hermes Agent, the graph runner) is
pointed at the meter instead of the model, with a base URL that names what it is doing:

    http://127.0.0.1:8787/t/<run>/<arm>/<task>/<item>

and the meter forwards the rest of the path to the real endpoint. Measuring at the wire means no
framework can hide, skip or double-count a request, and a harness that only lets you set a base
URL needs nothing more. Both wire formats are understood: OpenAI chat completions
(`.../v1/chat/completions`) and Anthropic Messages (`.../v1/messages`). Other paths (model lists,
token counting) are forwarded but not recorded, since they cost nothing.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp
from aiohttp import web

from . import cache, ledger, usage
from .llm import UPSTREAM_DOWN

# Hop-by-hop and length headers are the proxy's to set, not the client's or the upstream's.
_DROP = {"host", "content-length", "transfer-encoding", "connection", "content-encoding", "keep-alive"}


SESSION = web.AppKey("session", aiohttp.ClientSession)


@dataclass
class Upstreams:
    """Where each wire format is forwarded, e.g. a local llama-server for both, or
    https://api.anthropic.com for Messages."""

    openai: str
    anthropic: str
    # Model name → upstream, for chat completions: one meter in front of several local servers
    # (llama-server serves one model each), so the graph can send each step to its own size.
    models: dict[str, str] = field(default_factory=dict)

    def base(self, wire: str | None, model: str) -> str:
        if wire == "anthropic":
            return self.anthropic
        return self.models.get(model, self.openai)


def wire_of(tail: str) -> str | None:
    """Which wire format a forwarded path speaks, or None for paths that are not billed."""
    tail = tail.rstrip("/")
    if tail.endswith("chat/completions"):
        return "openai"
    if tail.endswith("messages") and not tail.endswith("count_tokens"):
        return "anthropic"
    return None


def prepare(wire: str | None, body: bytes) -> tuple[bytes, bool]:
    """The body to forward, and whether the request streams.

    A streamed OpenAI request is made to report its usage in the last chunk
    (stream_options.include_usage); without it the stream carries no token counts at all.
    """
    if wire is None or not body:
        return body, False
    try:
        req = json.loads(body)
    except json.JSONDecodeError:
        return body, False
    stream = bool(req.get("stream"))
    if wire == "openai" and stream:
        opts = req.setdefault("stream_options", {})
        if not opts.get("include_usage"):
            opts["include_usage"] = True
            body = json.dumps(req).encode()
    return body, stream


def model_of(body: bytes) -> str:
    """The model a request asks for, or "" when the body is not a JSON object naming one."""
    try:
        req = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    return req.get("model", "") if isinstance(req, dict) else ""


def prefix_of(wire: str, body: bytes) -> list[list]:
    """The request's prefix chain for replaying provider caches (cache.chain); [] if unreadable."""
    try:
        req = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    return cache.chain(wire, req) if isinstance(req, dict) else []


def parse(wire: str, stream: bool, content: bytes) -> usage.Usage:
    if wire == "openai":
        return usage.from_openai_stream(content) if stream else usage.from_openai(json.loads(content or b"{}"))
    return usage.from_anthropic_stream(content) if stream else usage.from_anthropic(json.loads(content or b"{}"))


def app(upstreams: Upstreams, ledger_path: Path) -> web.Application:
    async def proxy(request: web.Request) -> web.StreamResponse:
        m = request.match_info
        tail = m["tail"]
        wire = wire_of(tail)
        body, stream = prepare(wire, await request.read())
        model = model_of(body) if wire == "openai" and upstreams.models else ""
        url = upstreams.base(wire, model).rstrip("/") + "/" + tail
        if request.query_string:
            url += "?" + request.query_string

        headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP}
        session = request.app[SESSION]
        started = time.monotonic()

        try:
            up = await session.request(request.method, url, data=body, headers=headers)
        except (TimeoutError, aiohttp.ClientConnectionError) as e:
            # Marked, so the client counts a broken run rather than a failed item.
            return web.Response(status=502, headers={UPSTREAM_DOWN: "1"}, text=f"upstream unreachable: {e!r}")
        try:
            resp = web.StreamResponse(status=up.status)
            for k, v in up.headers.items():
                if k.lower() not in _DROP:
                    resp.headers[k] = v
            await resp.prepare(request)
            buf = bytearray()
            # A server that dies mid-response raises here; the client's connection then drops,
            # which it also counts as a broken run.
            async for chunk in up.content.iter_any():
                buf.extend(chunk)
                await resp.write(chunk)
            await resp.write_eof()
            status = up.status
        finally:
            up.release()

        if wire is not None:
            try:
                u = parse(wire, stream, bytes(buf))
            except (json.JSONDecodeError, UnicodeDecodeError):
                u = usage.Usage()
            ledger.append(
                ledger_path,
                ledger.Record(
                    run=m["run"],
                    arm=m["arm"],
                    task=m["task"],
                    item=m["item"],
                    wire=wire,
                    model=u.model,
                    input=u.input,
                    cache_read=u.cache_read,
                    cache_write=u.cache_write,
                    output=u.output,
                    latency_ms=round((time.monotonic() - started) * 1000),
                    status=status,
                    ts=time.time(),
                    streamed=stream,
                    extra={"prefix": prefix_of(wire, body)},
                ),
            )
        return resp

    async def session_ctx(a: web.Application):
        # Generous: a harness turn on a local model can take minutes.
        a[SESSION] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_read=900))
        yield
        await a[SESSION].close()

    a = web.Application(client_max_size=64 * 1024 * 1024)
    a.cleanup_ctx.append(session_ctx)
    a.router.add_route("*", "/t/{run}/{arm}/{task}/{item}/{tail:.*}", proxy)
    return a
