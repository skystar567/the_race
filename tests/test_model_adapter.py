"""Adapter contract tests with a controlled transport; no real network calls."""

import json

import httpx
import pytest

from campus.model import DeepSeek, ModelError

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def response_payload(text: str, status: str = "completed") -> dict:
    return {
        "status": status,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


def sse(events: list[dict]) -> str:
    return "".join(f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                   for event in events)


def client_for(handler) -> DeepSeek:
    return DeepSeek(api_key="test-key", transport=httpx.MockTransport(handler))


async def test_structured_request_uses_one_model_and_json_schema():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json=response_payload('{"concepts": [], "relations": []}'))

    model = client_for(handler)
    result = await model.complete("规则", {"a": 1}, {"type": "object"})
    assert result == {"concepts": [], "relations": []}
    assert seen["url"].endswith("/responses")
    assert seen["auth"] == "Bearer test-key"
    payload = seen["payload"]
    assert payload["model"] == "deepseek-flash"
    assert payload["reasoning"] == {"effort": "high"}
    assert payload["text"]["format"]["type"] == "json_schema"
    assert "tools" not in payload
    assert "previous_response_id" not in payload


@pytest.mark.parametrize(
    "status,code",
    [("incomplete", "truncated"), ("failed", "failed")],
)
async def test_incomplete_and_failed_status_are_classified(status, code):
    async def handler(request):
        return httpx.Response(200, json=response_payload("{}", status))

    with pytest.raises(ModelError) as caught:
        await client_for(handler).complete("规则", {}, {"type": "object"})
    assert caught.value.code == code


@pytest.mark.parametrize(
    "status,code,retryable",
    [(401, "authentication", False), (403, "authentication", False),
     (429, "temporary", True), (503, "temporary", True), (400, "request", False)],
)
async def test_http_failures_are_classified(status, code, retryable):
    async def handler(request):
        return httpx.Response(status, json={"error": "upstream detail must not leak"})

    with pytest.raises(ModelError) as caught:
        await client_for(handler).complete("规则", {}, {"type": "object"})
    assert caught.value.code == code
    assert caught.value.retryable is retryable
    assert "upstream detail" not in str(caught.value)


async def test_empty_and_non_json_output_are_classified():
    async def empty(request):
        return httpx.Response(200, json=response_payload("   "))

    with pytest.raises(ModelError) as caught:
        await client_for(empty).complete("规则", {}, {"type": "object"})
    assert caught.value.code == "empty_output"

    async def prose(request):
        return httpx.Response(200, json=response_payload("这不是 JSON"))

    with pytest.raises(ModelError) as caught:
        await client_for(prose).complete("规则", {}, {"type": "object"})
    assert caught.value.code == "invalid_output"


async def test_missing_credentials_fail_before_any_request():
    model = DeepSeek(api_key="", transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    with pytest.raises(ModelError) as caught:
        await model.complete("规则", {}, {"type": "object"})
    assert caught.value.code == "configuration"


async def test_stream_yields_deltas_and_requires_the_terminal_event():
    events = [
        {"type": "response.output_text.delta", "delta": "进程"},
        {"type": "response.output_text.delta", "delta": "是执行单位"},
        {"type": "response.completed", "response": response_payload("进程是执行单位")},
    ]

    async def handler(request):
        return httpx.Response(200, content=sse(events).encode(), headers={"content-type": "text/event-stream"})

    chunks = [chunk async for chunk in client_for(handler).stream("规则", {})]
    assert chunks == ["进程", "是执行单位"]


async def test_stream_without_terminal_event_is_interrupted():
    events = [{"type": "response.output_text.delta", "delta": "部分"}]

    async def handler(request):
        return httpx.Response(200, content=sse(events).encode(), headers={"content-type": "text/event-stream"})

    with pytest.raises(ModelError) as caught:
        _ = [chunk async for chunk in client_for(handler).stream("规则", {})]
    assert caught.value.code == "interrupted"


async def test_stream_final_text_mismatch_is_invalid():
    events = [
        {"type": "response.output_text.delta", "delta": "abc"},
        {"type": "response.completed", "response": response_payload("abd")},
    ]

    async def handler(request):
        return httpx.Response(200, content=sse(events).encode(), headers={"content-type": "text/event-stream"})

    with pytest.raises(ModelError) as caught:
        _ = [chunk async for chunk in client_for(handler).stream("规则", {})]
    assert caught.value.code == "invalid_output"


async def test_stream_http_failure_is_classified():
    async def handler(request):
        return httpx.Response(401)

    with pytest.raises(ModelError) as caught:
        _ = [chunk async for chunk in client_for(handler).stream("规则", {})]
    assert caught.value.code == "authentication"
