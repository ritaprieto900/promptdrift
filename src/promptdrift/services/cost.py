"""Cost estimation for a suite run.

Honesty rules: call counts are exact (including one judge call per sample
per judge assertion); token figures are estimates from a ~4 chars/token
heuristic and labeled as such; completion cost is never guessed (output
length is unknown before the run), so any money figure is a lower bound.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from promptdrift.domain.assertions import Judge
from promptdrift.domain.suite import OpenAICompatConfig, Suite
from promptdrift.domain.templates import render

_APPROX_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class CostEstimate:
    calls: int
    est_prompt_tokens: int | None = None
    max_tokens_cap: int | None = None
    prompt_per_1m: float | None = None
    completion_per_1m: float | None = None

    @property
    def est_prompt_cost_usd(self) -> float | None:
        """Lower bound: prompt cost only, completion cost unknown pre-run."""
        if self.est_prompt_tokens is None or self.prompt_per_1m is None:
            return None
        return self.est_prompt_tokens / 1_000_000 * self.prompt_per_1m


def estimate(suite: Suite) -> CostEstimate:
    calls = 0
    prompt_chars = 0
    for case in suite.cases:
        samples = suite.effective_samples(case)
        judge_count = sum(1 for assertion in case.assertions if isinstance(assertion, Judge))
        calls += samples * (1 + judge_count)
        per_call = sum(len(render(message.content, case.vars)) for message in case.messages)
        prompt_chars += per_call * samples
    provider = suite.provider
    if isinstance(provider, OpenAICompatConfig) and provider.pricing is not None:
        return CostEstimate(
            calls=calls,
            est_prompt_tokens=math.ceil(prompt_chars / _APPROX_CHARS_PER_TOKEN),
            max_tokens_cap=provider.max_tokens,
            prompt_per_1m=provider.pricing.prompt_per_1m,
            completion_per_1m=provider.pricing.completion_per_1m,
        )
    return CostEstimate(calls=calls)
