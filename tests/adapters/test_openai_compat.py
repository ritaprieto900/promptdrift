"""Tests for the OpenAI-compatible adapter — all HTTP mocked via respx.

These run the retry/backoff state machine without any network. CI never
talks to a real endpoint.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from promptdrift.adapters.openai_compat import OpenAICompatProvider
from promptdrift.domain.suite import OpenAICompatConfig
from promptdrift.errors import ProviderError
from promptdrift.ports import CompletionRequest

ENV_KEY = "PROMPTDRIFT_TEST_KEY"
BASE_URL = "https://api.test/v1"

CONFIG = OpenAICompatConfig(model="test-model", base_url=BASE_URL, api_key_env=ENV_KEY)

GOOD_RESPONSE = {
    "model": "test-model",
    "choices": [{"message": {"role": "assistant", "content": "hi there"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 7},
}


def make_request() -> CompletionRequest:
    return CompletionRequest(
        model="test-model",
        messages=(("user", "hello"),),
        temperature=0.5,
        max_tokens=32,
    )


async def test_success_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_KEY, "sk-test")
    with respx.mock(base_url="https://api.test") as mock:
        route = mock.post("/v1/chat/completions").respond(json=GOOD_RESPONSE)
        provider = OpenAICompatProvider(CONFIG)
        response = await provider.complete(make_request())
        await provider.aclose()
    assert route.called
    assert response.text == "hi there"
    assert response.prompt_tokens == 5
    assert response.completion_tokens == 7
    assert response.finish_reason == "stop"
    assert not response.cached


async def test_auth_header_and_payload_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_KEY, "sk-test")
    with respx.mock(base_url="https://api.test") as mock:
        route = mock.post("/v1/chat/completions").respond(json=GOOD_RESPONSE)
        provider = OpenAICompatProvider(CONFIG)
        await provider.complete(make_request())
        await provider.aclose()
    sent_request = route.calls.last.request
    assert sent_request.headers["Authorization"] == "Bearer sk-test"
    payload = json.loads(sent_request.content)
    assert payload["model"] == "test-model"
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert payload["temperature"] == 0.5
    assert payload["max_tokens"] == 32
    assert "top_p" not in payload  # None options are omitted
    assert "seed" not in payload


async def test_missing_api_key_names_the_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_KEY, raising=False)
    provider = OpenAICompatProvider(CONFIG)
    with pytest.raises(ProviderError, match="PROMPTDRIFT_TEST_KEY"):
        await provider.complete(make_request())


async def test_retry_on_429_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_KEY, "sk-test")
    with respx.mock(base_url="https://api.test") as mock:
        route = mock.post("/v1/chat/completions").mock(
            side_effect=[
                httpx.Response(429, json={"error": "rate limited"}),
                httpx.Response(200, json=GOOD_RESPONSE),
            ]
        )
        provider = OpenAICompatProvider(CONFIG)
        response = await provider.complete(make_request())
        await provider.aclose()
    assert route.call_count == 2
    assert response.text == "hi there"


async def test_client_errors_fail_fast_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_KEY, "sk-test")
    with respx.mock(base_url="https://api.test") as mock:
        route = mock.post("/v1/chat/completions").respond(
            status_code=400, json={"error": {"message": "bad request"}}
        )
        provider = OpenAICompatProvider(CONFIG)
        with pytest.raises(ProviderError, match="HTTP 400"):
            await provider.complete(make_request())
        await provider.aclose()
    assert route.call_count == 1


async def test_retries_exhausted_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_KEY, "sk-test")
    config = OpenAICompatConfig(
        model="test-model", base_url=BASE_URL, api_key_env=ENV_KEY, max_retries=1
    )
    with respx.mock(base_url="https://api.test") as mock:
        route = mock.post("/v1/chat/completions").mock(
            side_effect=[
                httpx.Response(503, json={"error": "down"}),
                httpx.Response(503, json={"error": "still down"}),
            ]
        )
        provider = OpenAICompatProvider(config)
        with pytest.raises(ProviderError, match="HTTP 503"):
            await provider.complete(make_request())
        await provider.aclose()
    assert route.call_count == 2


async def test_empty_choices_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_KEY, "sk-test")
    with respx.mock(base_url="https://api.test") as mock:
        mock.post("/v1/chat/completions").respond(json={"object": "list", "choices": []})
        provider = OpenAICompatProvider(CONFIG)
        with pytest.raises(ProviderError, match="no choices"):
            await provider.complete(make_request())
        await provider.aclose()


async def test_transport_error_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_KEY, "sk-test")
    config = OpenAICompatConfig(
        model="test-model", base_url=BASE_URL, api_key_env=ENV_KEY, max_retries=0
    )
    with respx.mock(base_url="https://api.test") as mock:
        mock.post("/v1/chat/completions").mock(side_effect=httpx.ConnectError("boom"))
        provider = OpenAICompatProvider(config)
        with pytest.raises(ProviderError, match="network error"):
            await provider.complete(make_request())
        await provider.aclose()
