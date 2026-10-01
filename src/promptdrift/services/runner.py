"""Execute a suite: render templates, call the provider, check assertions.

Async throughout. A single shared semaphore caps in-flight provider calls at
``suite.concurrency`` regardless of how many cases × samples are in flight;
cases and their samples all run concurrently within that cap.

One failing provider call aborts the whole run (gather propagates): if the
endpoint is down, partial results would invite wrong conclusions. Judge
assertions are the exception to the pure-``check()`` path: they need a
provider round-trip per sample, handled here against the suite's judge
binding.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from promptdrift.domain.assertions import Judge
from promptdrift.domain.results import (
    AssertionOutcome,
    CaseResult,
    Run,
    SampleResult,
    TokenUsage,
)
from promptdrift.domain.suite import Case, Suite
from promptdrift.domain.templates import render
from promptdrift.ports import CompletionRequest, Provider
from promptdrift.services.judge import (
    JudgeBinding,
    build_judge_request,
    opt_float,
    opt_int,
    parse_judge_response,
)

__all__ = ["Runner"]


class Runner:
    def __init__(
        self,
        provider: Provider,
        judge: JudgeBinding | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._provider = provider
        self._judge = judge
        self._clock = clock

    async def run(self, suite: Suite) -> Run:
        run = Run.begin(suite.suite, suite.model_name, suite.fingerprint())
        started = self._clock()
        semaphore = asyncio.Semaphore(suite.concurrency)
        case_results = await asyncio.gather(
            *(self._run_case(suite, case, semaphore) for case in suite.cases)
        )
        run.cases = list(case_results)
        run.duration_ms = (self._clock() - started) * 1000
        return run

    async def _run_case(self, suite: Suite, case: Case, semaphore: asyncio.Semaphore) -> CaseResult:
        rendered = [(message.role, render(message.content, case.vars)) for message in case.messages]
        params = suite.provider.request_params()
        samples = await asyncio.gather(
            *(
                self._sample(rendered, params, case, suite.model_name, semaphore)
                for _ in range(suite.effective_samples(case))
            )
        )
        return CaseResult(case_id=case.id, model=suite.model_name, samples=list(samples))

    async def _sample(
        self,
        rendered_messages: list[tuple[str, str]],
        params: dict[str, object],
        case: Case,
        model: str,
        semaphore: asyncio.Semaphore,
    ) -> SampleResult:
        request = CompletionRequest(
            model=model,
            messages=tuple(rendered_messages),
            temperature=opt_float(params, "temperature"),
            max_tokens=opt_int(params, "max_tokens"),
            top_p=opt_float(params, "top_p"),
            seed=opt_int(params, "seed"),
        )
        async with semaphore:
            started = self._clock()
            response = await self._provider.complete(request)
            latency_ms = (self._clock() - started) * 1000
        usage = TokenUsage(
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
        )
        outcomes = [
            assertion.check(response.text, usage, latency_ms)
            for assertion in case.assertions
            if not isinstance(assertion, Judge)
        ]
        for judge_assertion in (a for a in case.assertions if isinstance(a, Judge)):
            outcomes.append(
                await self._run_judge(judge_assertion, rendered_messages, response.text)
            )
        return SampleResult(
            output=response.text,
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=response.finish_reason,
            cached=response.cached,
            outcomes=outcomes,
        )

    async def _run_judge(
        self,
        judge_assertion: Judge,
        rendered_messages: list[tuple[str, str]],
        output: str,
    ) -> AssertionOutcome:
        if self._judge is None:
            return AssertionOutcome(
                assertion_id=judge_assertion.assertion_id,
                assertion_type="judge",
                passed=False,
                detail=(
                    "case declares a `judge` assertion but the suite has no `judge:` provider block"
                ),
            )
        request = build_judge_request(judge_assertion, rendered_messages, output, self._judge)
        judge_response = await self._judge.provider.complete(request)
        return parse_judge_response(judge_response.text, judge_assertion)
