"""LLM-as-judge plumbing: build the grading request, parse the grading reply.

The judge protocol is a fixed system prompt, a rendered rubric + conversation
user message, and a strict JSON reply of the shape
``{"score": <1-5>, "reason": "..."}``. Parsing accepts the JSON either raw or
fenced, then falls back to a score regex; anything else is a failed outcome,
which multi-sample statistics report as ``unstable`` rather than swallowing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from promptdrift.domain.assertions import Judge
from promptdrift.domain.results import AssertionOutcome
from promptdrift.ports import CompletionRequest, Provider

if TYPE_CHECKING:
    from promptdrift.domain.results import TokenUsage  # noqa: F401

_SCORE_RE = re.compile(r'"score"\s*:\s*([1-5])')

JUDGE_SYSTEM_PROMPT = (
    "You are a strict evaluator. Score the assistant reply against the rubric "
    "on a 1-5 integer scale. Respond with ONLY a JSON object: "
    '{"score": <integer 1-5>, "reason": "<one short sentence>"}'
)


@dataclass(frozen=True)
class JudgeBinding:
    """The judge provider wired up with its model and sampling params."""

    provider: Provider
    model: str
    params: dict[str, object] = field(default_factory=dict)


def opt_float(params: dict[str, object], key: str) -> float | None:
    value = params.get(key)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raise TypeError(f"sampling parameter {key!r} must be numeric, got {type(value).__name__}")


def opt_int(params: dict[str, object], key: str) -> int | None:
    value = params.get(key)
    if value is None:
        return None
    if isinstance(value, int):
        return int(value)
    raise TypeError(f"sampling parameter {key!r} must be an integer, got {type(value).__name__}")


def build_judge_request(
    judge_assertion: Judge,
    rendered_messages: list[tuple[str, str]],
    output: str,
    binding: JudgeBinding,
) -> CompletionRequest:
    conversation = "\n".join(f"{role}: {content}" for role, content in rendered_messages)
    user_content = (
        f"## Rubric\n{judge_assertion.rubric}\n\n"
        f"## Conversation\n{conversation}\n\n"
        f"## Reply to score\n{output}"
    )
    return CompletionRequest(
        model=binding.model,
        messages=(("system", JUDGE_SYSTEM_PROMPT), ("user", user_content)),
        temperature=opt_float(binding.params, "temperature"),
        max_tokens=opt_int(binding.params, "max_tokens"),
        top_p=opt_float(binding.params, "top_p"),
        seed=opt_int(binding.params, "seed"),
    )


def parse_judge_response(text: str, judge_assertion: Judge) -> AssertionOutcome:
    """Turn the judge's reply into an AssertionOutcome for *judge_assertion*."""

    def outcome(passed: bool, detail: str) -> AssertionOutcome:
        return AssertionOutcome(
            assertion_id=judge_assertion.assertion_id,
            assertion_type="judge",
            passed=passed,
            detail=detail,
        )

    parsed: dict[str, object] | None = None
    try:
        candidate = json.loads(text)
        if isinstance(candidate, dict) and "score" in candidate:
            parsed = candidate
    except json.JSONDecodeError:
        match = _SCORE_RE.search(text)
        if match is not None:
            parsed = {"score": int(match.group(1)), "reason": ""}
    if parsed is None:
        snippet = text.strip().replace("\n", " ")[:160]
        return outcome(False, f"judge reply is not parseable JSON with a score: {snippet!r}")
    try:
        score = int(str(parsed["score"]))
    except (TypeError, ValueError):
        return outcome(False, f"judge score is not an integer: {parsed.get('score')!r}")
    if not 1 <= score <= 5:
        return outcome(False, f"judge score {score} is outside the 1-5 scale")
    reason = str(parsed.get("reason") or "").strip()
    detail = f"judge scored {score}/5 (min {judge_assertion.min_score})"
    if reason:
        detail += f": {reason}"
    return outcome(score >= judge_assertion.min_score, detail)


__all__ = [
    "JUDGE_SYSTEM_PROMPT",
    "JudgeBinding",
    "build_judge_request",
    "opt_float",
    "opt_int",
    "parse_judge_response",
]
