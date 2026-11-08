"""Usage parsing on response shapes the stub does not produce: missing fields, other servers."""

from avg import usage


def test_openai_without_cache_details():
    u = usage.from_openai({"model": "m", "usage": {"prompt_tokens": 10, "completion_tokens": 4}})
    assert (u.input, u.cache_read, u.output, u.model) == (10, 0, 4, "m")


def test_missing_usage_counts_nothing():
    assert usage.from_openai({}).prompt == 0
    assert usage.from_anthropic({}).prompt == 0
    assert usage.from_openai_stream(b"data: [DONE]\n\n").output == 0


def test_openai_stream_takes_the_usage_chunk_and_the_model():
    sse = (
        b'data: {"model":"m","choices":[{"delta":{"content":"x"}}]}\n\n'
        b'data: {"choices":[],"usage":{"prompt_tokens":9,"completion_tokens":3}}\n\n'
        b"data: [DONE]\n\n"
    )
    u = usage.from_openai_stream(sse)
    assert (u.input, u.output, u.model) == (9, 3, "m")


def test_anthropic_stream_restated_input_wins():
    # Some servers (llama.cpp among them) send 0 input in message_start and the real count
    # in message_delta.
    sse = (
        b'event: message_start\ndata: {"type":"message_start","message":{"model":"m","usage":{"input_tokens":0,"output_tokens":1}}}\n\n'
        b'data: {"type":"message_delta","usage":{"input_tokens":50,"output_tokens":12}}\n\n'
        b"data: not json\n\n"
    )
    u = usage.from_anthropic_stream(sse)
    assert (u.input, u.output, u.model) == (50, 12, "m")
