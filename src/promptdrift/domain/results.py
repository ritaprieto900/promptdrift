"""Run-side domain records: what actually happened when a suite executed.

These models are pure data with derived-value helpers. Nothing here performs
I/O; persistence lives in the adapters layer.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class AssertionOutcome(BaseModel):
    """The result of checking one assertion against one sample."""

    assertion_id: str
    assertion_type: str
    passed: bool
    detail: str | None = None


class SampleResult(BaseModel):
    """One completion for one case, plus per-assertion verdicts on it."""

    output: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    finish_reason: str | None = None
    cached: bool = False
    outcomes: list[AssertionOutcome] = Field(default_factory=list)


class CaseResult(BaseModel):
    """All samples for one case, with aggregate helpers."""

    case_id: str
    model: str | None = None
    samples: list[SampleResult] = Field(default_factory=list)

    def rates(self) -> dict[str, tuple[int, int]]:
        """Map ``assertion_id -> (passed, total)`` across all samples."""
        passed: dict[str, int] = {}
        total: dict[str, int] = {}
        for sample in self.samples:
            for outcome in sample.outcomes:
                total[outcome.assertion_id] = total.get(outcome.assertion_id, 0) + 1
                if outcome.passed:
                    passed[outcome.assertion_id] = passed.get(outcome.assertion_id, 0) + 1
        return {aid: (passed.get(aid, 0), count) for aid, count in total.items()}

    def assertion_type(self, assertion_id: str) -> str | None:
        for sample in self.samples:
            for outcome in sample.outcomes:
                if outcome.assertion_id == assertion_id:
                    return outcome.assertion_type
        return None

    def mean_latency_ms(self) -> float:
        if not self.samples:
            return 0.0
        return sum(s.latency_ms for s in self.samples) / len(self.samples)

    def mean_tokens(self) -> tuple[float, float]:
        """Return ``(mean_prompt_tokens, mean_completion_tokens)``."""
        if not self.samples:
            return (0.0, 0.0)
        n = len(self.samples)
        return (
            sum(s.usage.prompt_tokens for s in self.samples) / n,
            sum(s.usage.completion_tokens for s in self.samples) / n,
        )

    def representative_output(self) -> str:
        return self.samples[0].output if self.samples else ""


class Run(BaseModel):
    """One execution of one suite."""

    suite: str
    model: str | None
    config_fingerprint: str
    started_at: datetime
    duration_ms: float
    cases: list[CaseResult] = Field(default_factory=list)

    @classmethod
    def begin(cls, suite: str, model: str | None, config_fingerprint: str) -> Run:
        return cls(
            suite=suite,
            model=model,
            config_fingerprint=config_fingerprint,
            started_at=datetime.now(timezone.utc),
            duration_ms=0.0,
        )

    def total_usage(self) -> TokenUsage:
        prompt = 0
        completion = 0
        for case_result in self.cases:
            for sample in case_result.samples:
                prompt += sample.usage.prompt_tokens
                completion += sample.usage.completion_tokens
        return TokenUsage(prompt_tokens=prompt, completion_tokens=completion)

    def case(self, case_id: str) -> CaseResult | None:
        for case_result in self.cases:
            if case_result.case_id == case_id:
                return case_result
        return None
