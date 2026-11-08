"""A stand-in model server for tests: answers both wire formats, streamed or not, with fixed
token counts, so the meter and everything after it can be checked without a GPU or an API key.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from aiohttp import web

# What every stub response reports. Chosen so no two numbers are equal and a field read from
# the wrong place shows up as a wrong count.
PROMPT, CACHED, CACHE_WRITE, OUTPUT = 120, 30, 7, 45


def _sse(events: list[dict], done: bool = False) -> bytes:
    out = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
    if done:
        out += "data: [DONE]\n\n"
    return out.encode()


# A scripted reply: given the chat request, the assistant message to answer with (content and/or
# tool_calls). Lets a test drive a runner through a conversation; the usage stays fixed.
Reply = Callable[[dict], dict]


def app(model: str = "stub-model", reply: Reply | None = None) -> web.Application:
    async def chat(request: web.Request) -> web.StreamResponse:
        req = await request.json()
        message = reply(req) if reply else {"role": "assistant", "content": "ok"}
        usage = {
            "prompt_tokens": PROMPT,
            "completion_tokens": OUTPUT,
            "total_tokens": PROMPT + OUTPUT,
            "prompt_tokens_details": {"cached_tokens": CACHED},
        }
        if not req.get("stream"):
            return web.json_response(
                {
                    "model": model,
                    "choices": [{"index": 0, "message": message}],
                    "usage": usage,
                }
            )
        chunks = [{"model": model, "choices": [{"index": 0, "delta": {"content": message.get("content") or ""}}]}]
        # Like OpenAI: usage only when the request asked for it.
        if (req.get("stream_options") or {}).get("include_usage"):
            chunks.append({"model": model, "choices": [], "usage": usage})
        return web.Response(body=_sse(chunks, done=True), content_type="text/event-stream")

    async def messages(request: web.Request) -> web.StreamResponse:
        req = await request.json()
        usage = {
            "input_tokens": PROMPT - CACHED,
            "cache_read_input_tokens": CACHED,
            "cache_creation_input_tokens": CACHE_WRITE,
            "output_tokens": OUTPUT,
        }
        if not req.get("stream"):
            return web.json_response(
                {"type": "message", "model": model, "content": [{"type": "text", "text": "ok"}], "usage": usage}
            )
        events = [
            {"type": "message_start", "message": {"model": model, "usage": {**usage, "output_tokens": 1}}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "ok"}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": OUTPUT}},
            {"type": "message_stop"},
        ]
        return web.Response(body=_sse(events), content_type="text/event-stream")

    async def models(_: web.Request) -> web.Response:
        return web.json_response({"data": [{"id": model}]})

    a = web.Application()
    a.router.add_post("/v1/chat/completions", chat)
    a.router.add_post("/v1/messages", messages)
    a.router.add_get("/v1/models", models)
    return a
