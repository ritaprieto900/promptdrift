"""The assertion registry: deterministic checks against a single sample.

Assertions are declared in suite YAML as single-key mappings, e.g.::

    assertions:
      - contains: "退款"
      - regex: "^您好"
      - json_schema: {"type": "object"}

Each assertion model owns:

- ``type_name``       the YAML key (and stable type tag in outcomes)
- ``assertion_id``    a *stable* identity derived from type + target, used as
                      the key in baseline snapshots across runs
- ``check()``         pure evaluation against one sample's output/usage/latency

Adding a new assertion type means: subclass :class:`BaseAssertion`, add it to
``ASSERTION_TYPES``, and the loader/CLI/schema pick it up. ``judge``
(LLM-as-judge rubric scoring) is evaluated by the Runner via the suite's
``judge`` provider rather than through ``check()``.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import ClassVar

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from pydantic import BaseModel, ConfigDict, Field, field_validator

from promptdrift.domain.results import AssertionOutcome, TokenUsage
from promptdrift.domain.templates import MissingTemplateVarError

__all__ = [
    "ASSERTION_TYPES",
    "AssertionSpec",
    "BaseAssertion",
    "CompletionTokensUnder",
    "Contains",
    "Equals",
    "IsJson",
    "JsonSchema",
    "LatencyUnder",
    "NotContains",
    "Regex",
]


def _slug(text: str, max_len: int = 32) -> str:
    """Lowercase, ASCII/CJK word slug with punctuation collapsed to dashes."""
    lowered = text.strip().lower()
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", lowered).strip("-")
    return slug[:max_len].rstrip("-") or "x"


def _snippet(output: str, limit: int = 120) -> str:
    flat = output.replace("\n", "\\n")
    if len(flat) <= limit:
        return flat
    return flat[:limit] + "…"


class BaseAssertion(BaseModel):
    """Common behavior for every assertion type."""

    type_name: ClassVar[str]
    #: Most assertions use the YAML key as the field name (``contains: "x"``);
    #: ones where the whole value is the model input (``judge: {rubric: ...}``)
    #: set this to True.
    value_is_model_input: ClassVar[bool] = False
    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def target_key(self) -> str:
        """A short string identifying *what* is being asserted, for IDs."""
        raise NotImplementedError

    @property
    def assertion_id(self) -> str:
        return f"{self.type_name}-{_slug(self.target_key)}"

    @property
    def target(self) -> object:
        return getattr(self, self.type_name)

    def check(self, output: str, usage: TokenUsage, latency_ms: float) -> AssertionOutcome:
        raise NotImplementedError

    def _outcome(self, passed: bool, detail: str | None) -> AssertionOutcome:
        return AssertionOutcome(
            assertion_id=self.assertion_id,
            assertion_type=self.type_name,
            passed=passed,
            detail=detail,
        )


class Equals(BaseAssertion):
    """Output must equal the target string exactly."""

    type_name: ClassVar[str] = "equals"
    equals: str

    @property
    def target_key(self) -> str:
        return self.equals

    def check(self, output: str, usage: TokenUsage, latency_ms: float) -> AssertionOutcome:
        if output == self.equals:
            return self._outcome(True, None)
        return self._outcome(False, f"expected exact match, got: {_snippet(output)!r}")


class Contains(BaseAssertion):
    """Output must contain the target substring."""

    type_name: ClassVar[str] = "contains"
    contains: str

    @property
    def target_key(self) -> str:
        return self.contains

    def check(self, output: str, usage: TokenUsage, latency_ms: float) -> AssertionOutcome:
        if self.contains in output:
            return self._outcome(True, None)
        return self._outcome(
            False, f"output does not contain {self.contains!r}; got: {_snippet(output)!r}"
        )


class NotContains(BaseAssertion):
    """Output must not contain the target substring."""

    type_name: ClassVar[str] = "not_contains"
    not_contains: str

    @property
    def target_key(self) -> str:
        return self.not_contains

    def check(self, output: str, usage: TokenUsage, latency_ms: float) -> AssertionOutcome:
        if self.not_contains not in output:
            return self._outcome(True, None)
        return self._outcome(False, f"output must not contain {self.not_contains!r}")


class Regex(BaseAssertion):
    """Output must match the pattern (``re.search``, DOTALL)."""

    type_name: ClassVar[str] = "regex"
    regex: str

    @field_validator("regex")
    @classmethod
    def _valid_pattern(cls, value: str) -> str:
        try:
            re.compile(value, re.DOTALL)
        except re.error as exc:
            raise ValueError(f"invalid regex {value!r}: {exc}") from exc
        return value

    @property
    def target_key(self) -> str:
        return self.regex

    def check(self, output: str, usage: TokenUsage, latency_ms: float) -> AssertionOutcome:
        if re.search(self.regex, output, re.DOTALL):
            return self._outcome(True, None)
        return self._outcome(
            False, f"output does not match /{self.regex}/; got: {_snippet(output)!r}"
        )


class IsJson(BaseAssertion):
    """Output must parse as JSON (strictly — no markdown fences stripped)."""

    type_name: ClassVar[str] = "is_json"
    is_json: bool = True

    @property
    def target_key(self) -> str:
        return "yes" if self.is_json else "no"

    def check(self, output: str, usage: TokenUsage, latency_ms: float) -> AssertionOutcome:
        try:
            json.loads(output)
        except json.JSONDecodeError as exc:
            return self._outcome(False, f"output is not valid JSON: {exc}")
        return self._outcome(True, None)


class JsonSchema(BaseAssertion):
    """Output must parse as JSON and validate against the JSON Schema."""

    type_name: ClassVar[str] = "json_schema"
    json_schema: dict[str, object]

    @property
    def target_key(self) -> str:
        blob = json.dumps(self.json_schema, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:8]

    def check(self, output: str, usage: TokenUsage, latency_ms: float) -> AssertionOutcome:
        try:
            parsed = json.loads(output)  # Any: JSON documents are dynamically typed
        except json.JSONDecodeError as exc:
            return self._outcome(False, f"output is not valid JSON: {exc}")
        try:
            validator_cls = validator_for(self.json_schema)
            validator_cls.check_schema(self.json_schema)
            errors = list(validator_cls(self.json_schema).iter_errors(parsed))
        except SchemaError as exc:
            return self._outcome(False, f"invalid schema in assertion: {exc.message}")
        if errors:
            first = errors[0]
            path = "/".join(str(part) for part in first.absolute_path) or "<root>"
            return self._outcome(False, f"schema violation at {path}: {first.message}")
        return self._outcome(True, None)


class LatencyUnder(BaseAssertion):
    """Sample latency must stay under the threshold (milliseconds)."""

    type_name: ClassVar[str] = "latency_under"
    latency_under: float = Field(gt=0)

    @property
    def target_key(self) -> str:
        if self.latency_under.is_integer():
            return str(int(self.latency_under))
        return str(self.latency_under)

    def check(self, output: str, usage: TokenUsage, latency_ms: float) -> AssertionOutcome:
        if latency_ms <= self.latency_under:
            return self._outcome(True, None)
        return self._outcome(
            False, f"latency {latency_ms:.0f}ms exceeded {self.latency_under:.0f}ms"
        )


class CompletionTokensUnder(BaseAssertion):
    """Completion token count must stay under the threshold."""

    type_name: ClassVar[str] = "completion_tokens_under"
    completion_tokens_under: int = Field(gt=0)

    @property
    def target_key(self) -> str:
        return str(self.completion_tokens_under)

    def check(self, output: str, usage: TokenUsage, latency_ms: float) -> AssertionOutcome:
        if usage.completion_tokens <= self.completion_tokens_under:
            return self._outcome(True, None)
        return self._outcome(
            False,
            f"completion used {usage.completion_tokens} tokens, budget is "
            f"{self.completion_tokens_under}",
        )


class Judge(BaseAssertion):
    """Score the output against a rubric with an LLM judge (1-5 scale).

    Unlike the deterministic assertions, a judge assertion is evaluated by
    the Runner through the suite's ``judge`` provider (a cheap model is
    typical), so ``check()`` is never called on it directly. One judge call
    per sample feeds the same multi-sample statistics as everything else:
    a judge that wavers shows up as ``unstable``, not as a gate failure.
    """

    type_name: ClassVar[str] = "judge"
    value_is_model_input: ClassVar[bool] = True
    rubric: str = Field(min_length=1)
    min_score: int = Field(default=3, ge=1, le=5)

    @property
    def target_key(self) -> str:
        return hashlib.sha1(self.rubric.encode("utf-8")).hexdigest()[:8]

    def check(self, output: str, usage: TokenUsage, latency_ms: float) -> AssertionOutcome:
        raise NotImplementedError(
            "judge assertions are evaluated by the Runner via the suite's `judge` provider"
        )


AssertionSpec = (
    Equals
    | Contains
    | NotContains
    | Regex
    | IsJson
    | JsonSchema
    | LatencyUnder
    | CompletionTokensUnder
    | Judge
)

ASSERTION_TYPES: dict[str, type[BaseAssertion]] = {
    cls.type_name: cls
    for cls in (
        Equals,
        Contains,
        NotContains,
        Regex,
        IsJson,
        JsonSchema,
        LatencyUnder,
        CompletionTokensUnder,
        Judge,
    )
}

# Re-exported so loader errors can reference it without a circular import.
__all__ += ["MissingTemplateVarError"]
