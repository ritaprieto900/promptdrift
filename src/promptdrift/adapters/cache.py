"""Response caching: sqlite store + a read-through provider wrapper.

Cache hits make ``diff`` iteration nearly free: re-running unchanged cases
replays stored completions instead of spending tokens. Keys are content
hashes of (provider, model, messages, sampling params) — so *any* change to
the prompt or params naturally misses and re-runs.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path

from promptdrift.ports import Cache, CompletionRequest, CompletionResponse, Provider


class SqliteCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        self._conn.commit()

    def get(self, key: str) -> CompletionResponse | None:
        row = self._conn.execute("SELECT payload FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row[0])
            return CompletionResponse(
                text=data["text"],
                model=data.get("model", ""),
                prompt_tokens=int(data.get("prompt_tokens", 0)),
                completion_tokens=int(data.get("completion_tokens", 0)),
                finish_reason=data.get("finish_reason"),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def put(self, key: str, response: CompletionResponse) -> None:
        blob = json.dumps(asdict(response), ensure_ascii=False)
        self._conn.execute("INSERT OR REPLACE INTO cache (key, payload) VALUES (?, ?)", (key, blob))
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM cache")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class CachedProvider:
    """Read-through cache in front of any provider. Implements Provider."""

    def __init__(self, inner: Provider, cache: Cache):
        self._inner = inner
        self._cache = cache
        self.provider_id = inner.provider_id

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        key = request.cache_key(self._inner.provider_id)
        hit = self._cache.get(key)
        if hit is not None:
            return replace(hit, cached=True)
        response = await self._inner.complete(request)
        self._cache.put(key, response)
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()
