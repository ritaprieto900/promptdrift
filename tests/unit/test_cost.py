"""Tests for cost estimation."""

from __future__ import annotations

import pytest

from promptdrift.domain.suite import OpenAICompatConfig
from promptdrift.services.cost import estimate
from tests.conftest import suite_from_yaml_text

PRICED_SUITE = """
suite: priced
provider:
  openai_compat:
    model: glm-4.7
    base_url: https://open.bigmodel.cn/api/paas/v4
    api_key_env: TEST_KEY
    max_tokens: 256
    pricing: {prompt_per_1m: 1.0, completion_per_1m: 8.0}
samples: 4
cases:
  - id: c1
    messages: [{role: user, content: "{{word}}"}]
    vars: {word: "0123456789"}
    assertions: [{contains: "x"}]
  - id: c2
    messages: [{role: user, content: "abcdefghij"}]
    assertions: [{contains: "x"}]
"""

UNPRICED_MOCK = """
suite: unpriced
provider:
  mock:
    default: "ok"
samples: 2
cases:
  - id: c1
    messages: [{role: user, content: "hi"}]
    assertions: [{contains: "x"}]
"""


def test_estimate_counts_calls_and_estimates_tokens() -> None:
    result = estimate(suite_from_yaml_text(PRICED_SUITE))
    assert result.calls == 8  # 2 cases × 4 samples
    # rendered prompts are 10 chars/call → ceil(10/4)=3? no: 80 total chars / 4 = 20
    assert result.est_prompt_tokens == 20
    assert result.max_tokens_cap == 256
    assert result.prompt_per_1m == 1.0
    # lower bound: prompt cost only
    assert result.est_prompt_cost_usd == pytest.approx(20 / 1_000_000 * 1.0)


def test_estimate_without_pricing_only_counts_calls() -> None:
    result = estimate(suite_from_yaml_text(UNPRICED_MOCK))
    assert result.calls == 2
    assert result.est_prompt_tokens is None
    assert result.est_prompt_cost_usd is None


def test_openai_without_pricing_config() -> None:
    suite = suite_from_yaml_text(PRICED_SUITE)
    suite = suite.model_copy(
        update={
            "provider": OpenAICompatConfig(
                model="m",
                base_url="https://x/v1",
                api_key_env="K",
                pricing=None,
            )
        }
    )
    result = estimate(suite)
    assert result.calls == 8
    assert result.est_prompt_tokens is None
