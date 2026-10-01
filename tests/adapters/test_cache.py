"""Tests for the sqlite response cache and the read-through wrapper."""

from __future__ import annotations

from pathlib import Path

from promptdrift.adapters.cache import CachedProvider, SqliteCache
from promptdrift.ports import CompletionRequest, CompletionResponse


class CountingProvider:
    provider_id = "counting"

    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.calls += 1
        return CompletionResponse(
            text=f"out-{self.calls}", model="m", prompt_tokens=1, completion_tokens=2
        )

    async def aclose(self) -> None:
        self.closed = True


def make_request(text: str = "hello") -> CompletionRequest:
    return CompletionRequest(model="m", messages=(("user", text),))


def test_roundtrip(tmp_path: Path) -> None:
    cache = SqliteCache(tmp_path / "cache.db")
    response = CompletionResponse(text="hi", model="m", prompt_tokens=3, completion_tokens=4)
    cache.put("k", response)
    loaded = cache.get("k")
    assert loaded == response
    cache.close()


def test_missing_key_is_none(tmp_path: Path) -> None:
    cache = SqliteCache(tmp_path / "cache.db")
    assert cache.get("absent") is None
    cache.close()


def test_reopen_preserves_entries(tmp_path: Path) -> None:
    cache = SqliteCache(tmp_path / "cache.db")
    cache.put("k", CompletionResponse(text="persisted", model="m"))
    cache.close()
    reopened = SqliteCache(tmp_path / "cache.db")
    assert reopened.get("k") is not None and reopened.get("k") is not None
    assert (reopened.get("k") or CompletionResponse(text="")).text == "persisted"
    reopened.close()


def test_clear(tmp_path: Path) -> None:
    cache = SqliteCache(tmp_path / "cache.db")
    cache.put("k", CompletionResponse(text="x", model="m"))
    cache.clear()
    assert cache.get("k") is None
    cache.close()


async def test_cached_provider_read_through(tmp_path: Path) -> None:
    inner = CountingProvider()
    cache = SqliteCache(tmp_path / "cache.db")
    provider = CachedProvider(inner, cache)
    first = await provider.complete(make_request())
    second = await provider.complete(make_request())
    assert inner.calls == 1
    assert not first.cached
    assert second.cached
    assert second.text == first.text
    await provider.aclose()
    assert inner.closed
    cache.close()


async def test_cache_key_respects_content(tmp_path: Path) -> None:
    inner = CountingProvider()
    cache = SqliteCache(tmp_path / "cache.db")
    provider = CachedProvider(inner, cache)
    await provider.complete(make_request("a"))
    await provider.complete(make_request("b"))
    await provider.complete(make_request("a"))
    assert inner.calls == 2
    cache.close()


def test_cache_key_stable_and_provider_scoped() -> None:
    request = make_request("a")
    assert request.cache_key("p1") == request.cache_key("p1")
    assert request.cache_key("p1") != request.cache_key("p2")
