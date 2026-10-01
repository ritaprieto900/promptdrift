"""OpenAI-compatible chat-completions adapter.

One adapter covers OpenAI, GLM, DeepSeek, Qwen, Moonshot and any other
endpoint that speaks ``POST {base_url}/chat/completions`` — which by 2026 is
the de-facto interchange format. Retries with exponential backoff + jitter on
429/5xx/transport errors; client errors (4xx) fail fast with the response
body included, because retrying a bad request never helps.
"""

from __future__ import annotations

import asyncio
import os
import random
from typing import Any

import httpx

from promptdrift.domain.suite import OpenAICompatConfig
from promptdrift.errors import ProviderError
from promptdrift.ports import CompletionRequest, CompletionResponse

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class OpenAICompatProvider:
    provider_id = "openai_compat"

    def __init__(
        self,
        config: OpenAICompatConfig,
        client: httpx.AsyncClient | None = None,
    ):
        self._config = config
        self._client = client or httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_seconds
        )
        self._owns_client = client is None

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        api_key = os.environ.get(self._config.api_key_env, "")
        if not api_key:
            raise ProviderError(
                f"environment variable {self._config.api_key_env!r} is not set; "
                f"it holds the API key for {self._config.base_url}. Export it, or use "
                "the mock provider for offline runs."
            )
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": role, "content": content} for role, content in request.messages],
        }
        for field in ("temperature", "max_tokens", "top_p", "seed"):
            value = getattr(request, field)
            if value is not None:
                payload[field] = value
        headers = {"Authorization": f"Bearer {api_key}"}

        attempt = 0
        while True:
            try:
                response = await self._client.post(
                    "/chat/completions", json=payload, headers=headers
                )
            except httpx.TransportError as exc:
                if attempt >= self._config.max_retries:
                    raise ProviderError(
                        f"network error calling {self._config.base_url}: {exc}"
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue
            if response.status_code == 200:
                return self._parse(response, request.model)
            if response.status_code in _RETRYABLE_STATUS and attempt < self._config.max_retries:
                await self._backoff(attempt)
                attempt += 1
                continue
            raise ProviderError(
                f"HTTP {response.status_code} from {self._config.base_url}/chat/completions: "
                f"{response.text[:300]}"
            )

    async def _backoff(self, failed_attempts: int) -> None:
        delay = min(2.0**failed_attempts, 8.0) * (0.5 + random.random() / 2)
        await asyncio.sleep(delay)

    def _parse(self, response: httpx.Response, requested_model: str) -> CompletionResponse:
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise ProviderError(f"endpoint returned non-JSON response: {exc}") from exc
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"endpoint response has no choices: {str(data)[:300]}")
        message = choices[0].get("message") or {}
        usage = data.get("usage") or {}
        return CompletionResponse(
            text=message.get("content") or "",
            model=str(data.get("model") or requested_model),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            finish_reason=choices[0].get("finish_reason"),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
