"""Offline scripted provider — the backbone of tests, demos, and CI.

The mock provider turns a suite's ``mock:`` config into deterministic (or
deliberately flaky, via ``variants``) completions without any network. It is
also how promptdrift tests itself: every unit and integration test runs on
this adapter.
"""

from __future__ import annotations

import math
from itertools import count

from promptdrift.domain.suite import MockConfig, MockRule
from promptdrift.ports import CompletionRequest, CompletionResponse

_APPROX_CHARS_PER_TOKEN = 4


def _tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / _APPROX_CHARS_PER_TOKEN))


class MockProvider:
    provider_id = "mock"

    def __init__(self, config: MockConfig):
        self._config = config
        self._rule_calls: dict[int, count] = {}
        self._default_calls = count()

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        last_user = ""
        for role, content in reversed(request.messages):
            if role == "user":
                last_user = content
                break
        text, prompt_text = self._respond(last_user)
        return CompletionResponse(
            text=text,
            model="mock",
            prompt_tokens=_tokens(prompt_text),
            completion_tokens=_tokens(text),
            finish_reason="stop",
        )

    def _respond(self, last_user: str) -> tuple[str, str]:
        """Return ``(completion_text, prompt_text_used_for_usage)``."""
        for index, rule in enumerate(self._config.rules):
            if rule.contains in last_user:
                return self._pick(rule, index), last_user
        if self._config.default_variants is not None:
            variants = self._config.default_variants
            return variants[next(self._default_calls) % len(variants)], last_user
        return self._config.default, last_user

    def _pick(self, rule: MockRule, index: int) -> str:
        if rule.variants is None:
            return rule.text or ""
        counter = self._rule_calls.setdefault(index, count())
        return rule.variants[next(counter) % len(rule.variants)]

    async def aclose(self) -> None:
        return None
