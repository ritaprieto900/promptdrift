"""Ports: the interfaces that services depend on and adapters implement.

The domain and services layers import only these protocols and records,
never a concrete adapter — which is what lets the whole verdict pipeline
run offline against the mock provider in tests.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    """A normalized chat-completion request, provider-agnostic."""

    model: str
    messages: tuple[tuple[str, str], ...]  # (role, content) pairs
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    seed: int | None = None

    def cache_key(self, provider_id: str) -> str:
        """Stable content hash identifying this call within *provider_id*."""
        payload = {
            "provider": provider_id,
            "model": self.model,
            "messages": [list(pair) for pair in self.messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "seed": self.seed,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CompletionResponse:
    """A normalized completion. ``cached`` is set by caching wrappers."""

    text: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str | None = None
    cached: bool = False


class Provider(Protocol):
    """Anything that can turn a :class:`CompletionRequest` into a completion.

    Implementations must be safe to call concurrently (asyncio tasks share
    one provider instance).
    """

    provider_id: str

    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    async def aclose(self) -> None: ...


class Cache(Protocol):
    """A store of :class:`CompletionResponse` keyed by :meth:`cache_key`."""

    def get(self, key: str) -> CompletionResponse | None: ...

    def put(self, key: str, response: CompletionResponse) -> None: ...

    def close(self) -> None: ...
