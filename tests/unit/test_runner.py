"""Tests for Runner internals that the lifecycle tests don't reach."""

from __future__ import annotations

import pytest

from promptdrift.adapters.mock import MockProvider
from promptdrift.domain.results import TokenUsage
from promptdrift.domain.suite import MockConfig
from promptdrift.ports import CompletionRequest
from promptdrift.services.judge import opt_float, opt_int
from promptdrift.services.runner import Runner
from tests.conftest import suite_from_yaml_text

SAMPLING_SUITE = """
suite: sampling
provider:
  openai_compat:
    model: m
    temperature: 0.3
    max_tokens: 128
    top_p: 0.9
    seed: 7
samples: 1
cases:
  - id: c
    messages: [{role: user, content: "hi"}]
    assertions: []
"""


def test_opt_helpers_convert_and_guard() -> None:
    params: dict[str, object] = {"a": 1.5, "b": 3, "n": None}
    assert opt_float(params, "a") == 1.5
    assert opt_float(params, "b") == 3.0
    assert opt_float(params, "n") is None
    assert opt_int(params, "b") == 3
    assert opt_int(params, "n") is None
    with pytest.raises(TypeError, match="must be numeric"):
        opt_float({"x": "fast"}, "x")
    with pytest.raises(TypeError, match="must be an integer"):
        opt_int({"x": 1.5}, "x")


async def test_request_carries_sampling_params() -> None:
    suite = suite_from_yaml_text(SAMPLING_SUITE)
    captured: list[CompletionRequest] = []

    class CaptureProvider(MockProvider):
        async def complete(self, request: CompletionRequest):
            captured.append(request)
            return await super().complete(request)

    provider = CaptureProvider(MockConfig(default="hello"))
    run = await Runner(provider).run(suite)
    assert run.case("c") is not None
    request = captured[0]
    assert request.temperature == 0.3
    assert request.max_tokens == 128
    assert request.top_p == 0.9
    assert request.seed == 7


async def test_usage_totals_aggregate() -> None:
    suite = suite_from_yaml_text(
        """
suite: agg
provider:
  mock:
    default: "0123456789"
samples: 2
cases:
  - id: c
    messages: [{role: user, content: "hi"}]
    assertions: []
"""
    )
    provider = MockProvider(MockConfig(default="0123456789"))
    run = await Runner(provider).run(suite)
    usage = run.total_usage()
    # prompt "hi" (2 chars → 1 token) × 2 samples; completion 10 chars → 3 tokens × 2
    assert usage.prompt_tokens == 2
    assert usage.completion_tokens == 6
    case = run.case("c")
    assert case is not None
    prompt, completion = case.mean_tokens()
    assert prompt == 1.0
    assert completion == 3.0
    assert case.mean_latency_ms() >= 0.0
    assert isinstance(case.samples[0].usage, TokenUsage)
