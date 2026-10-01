"""Execute a suite: render templates, call the provider, check assertions.

Async throughout. A single shared semaphore caps in-flight provider calls at
``suite.concurrency`` regardless of how many cases × samples are in flight;
cases and their samples all run concurrently within that cap.

One failing provider call aborts the whole run (gather propagates): if the
endpoint is down, partial results would invite wrong conclusions.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from promptdrift.domain.results import CaseResult, Run, SampleResult, TokenUsage
from promptdrift.domain.suite import Case, Suite
from promptdrift.domain.templates import render
from promptdrift.ports import CompletionRequest, Provider


def _opt_float(params: dict[str, object], key: str) -> float | None:
    value = params.get(key)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raise TypeError(f"sampling parameter {key!r} must be numeric, got {type(value).__name__}")


def _opt_int(params: dict[str, object], key: str) -> int | None:
    value = params.get(key)
    if value is None:
        return None
    if isinstance(value, int):
        return int(value)
    raise TypeError(f"sampling parameter {key!r} must be an integer, got {type(value).__name__}")


class Runner:
    def __init__(self, provider: Provider, clock: Callable[[], float] = time.monotonic):
        self._provider = provider
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
            temperature=_opt_float(params, "temperature"),
            max_tokens=_opt_int(params, "max_tokens"),
            top_p=_opt_float(params, "top_p"),
            seed=_opt_int(params, "seed"),
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
            assertion.check(response.text, usage, latency_ms) for assertion in case.assertions
        ]
        return SampleResult(
            output=response.text,
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=response.finish_reason,
            cached=response.cached,
            outcomes=outcomes,
        )
