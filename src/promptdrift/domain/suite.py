"""Suite: the declarative definition of what to test.

A suite file (``promptest.yaml`` or any ``*.yaml``) is data, validated into
these models before anything executes. Validation errors are shaped to be
readable by humans editing YAML.

The *config fingerprint* is the load-bearing idea here: it hashes only the
fields that define what "comparable to the baseline" means (model, sampling
params, sample count) and deliberately excludes prompt text, vars, mock rule
text, and assertion targets. Those later categories are *prompt changes* —
the thing this tool exists to measure — so they must show up as diffs, not
as staleness errors.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from promptdrift.domain.assertions import ASSERTION_TYPES, AssertionSpec, BaseAssertion
from promptdrift.domain.templates import missing_vars

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _check_slug(kind: str, value: str) -> str:
    if not _SLUG_RE.match(value):
        raise ValueError(
            f"{kind} {value!r} must be kebab-case matching [a-z0-9][a-z0-9_-]* "
            "(it is used as a file/key identity)"
        )
    return value


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class Pricing(BaseModel):
    """Per-million-token prices, used by ``promptdrift cost`` estimates."""

    model_config = ConfigDict(extra="forbid")

    prompt_per_1m: float = Field(ge=0)
    completion_per_1m: float = Field(ge=0)


class BaseProviderConfig(BaseModel):
    @property
    def provider_id(self) -> str:
        raise NotImplementedError

    @property
    def model_name(self) -> str:
        raise NotImplementedError

    def request_params(self) -> dict[str, object]:
        """Sampling parameters forwarded to the CompletionRequest."""
        raise NotImplementedError

    def identity(self) -> dict[str, object]:
        """Fields defining baseline comparability (see module docstring)."""
        raise NotImplementedError


class OpenAICompatConfig(BaseProviderConfig):
    """Any OpenAI-compatible endpoint: OpenAI, GLM, DeepSeek, Qwen, Moonshot, ..."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["openai_compat"] = "openai_compat"
    model: str
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, gt=0, le=1)
    seed: int | None = None
    timeout_seconds: float = Field(default=120, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)
    pricing: Pricing | None = None

    @property
    def provider_id(self) -> str:
        return "openai_compat"

    @property
    def model_name(self) -> str:
        return self.model

    def request_params(self) -> dict[str, object]:
        return {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "seed": self.seed,
        }

    def identity(self) -> dict[str, object]:
        return {
            "type": self.type,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "seed": self.seed,
        }


class MockRule(BaseModel):
    """Return canned text when the rule matches the last user message."""

    model_config = ConfigDict(extra="forbid")

    contains: str
    text: str | None = None
    variants: list[str] | None = None

    @model_validator(mode="after")
    def _exactly_one_shape(self) -> MockRule:
        if (self.text is None) == (self.variants is None):
            raise ValueError("mock rule needs exactly one of `text` or `variants`")
        if self.variants is not None and len(self.variants) < 2:
            raise ValueError("`variants` needs at least 2 entries (that is its purpose)")
        return self


class MockConfig(BaseProviderConfig):
    """Offline scripted provider — no API key, fully deterministic.

    The first rule whose ``contains`` matches the last user message wins.
    ``variants`` cycle per call, which is how you simulate flakiness.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["mock"] = "mock"
    rules: list[MockRule] = Field(default_factory=list)
    default: str = ""
    default_variants: list[str] | None = None

    @model_validator(mode="after")
    def _one_default_shape(self) -> MockConfig:
        if self.default and self.default_variants is not None:
            raise ValueError("use either `default` or `default_variants`, not both")
        return self

    @property
    def provider_id(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock"

    def request_params(self) -> dict[str, object]:
        return {}

    def identity(self) -> dict[str, object]:
        # Mock rule text is behavior *content* — a "prompt change" when edited,
        # deliberately excluded so diffs measure it instead of erroring.
        return {"type": self.type}


ProviderConfig = Annotated[OpenAICompatConfig | MockConfig, Field(discriminator="type")]


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str | None = None
    messages: list[Message] = Field(min_length=1)
    vars: dict[str, str] = Field(default_factory=dict)
    samples: int | None = Field(default=None, ge=1, le=20)
    assertions: list[AssertionSpec] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _slug_id(cls, value: str) -> str:
        return _check_slug("case id", value)

    @field_validator("vars", mode="before")
    @classmethod
    def _stringify_vars(cls, value: object) -> object:
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        return value

    @field_validator("assertions", mode="before")
    @classmethod
    def _parse_single_key_assertions(cls, value: object) -> object:
        """Accept YAML's ``- contains: "x"`` shape, one key per list item."""
        if not isinstance(value, list):
            return value
        parsed: list[BaseAssertion] = []
        for index, item in enumerate(value):
            if isinstance(item, BaseAssertion):
                parsed.append(item)
                continue
            if not isinstance(item, dict) or len(item) != 1:
                raise ValueError(
                    f"assertions[{index}] must be a single-key mapping like "
                    f'`contains: "..."`; supported keys: {sorted(ASSERTION_TYPES)}'
                )
            ((key, raw),) = item.items()
            assertion_cls = ASSERTION_TYPES.get(str(key))
            if assertion_cls is None:
                raise ValueError(
                    f"assertions[{index}]: unknown assertion {key!r}; "
                    f"supported: {sorted(ASSERTION_TYPES)}"
                )
            # In YAML, the key names the field: `- contains: "x"` means the
            # Contains model with contains="x".
            parsed.append(assertion_cls.model_validate({str(key): raw}))
        return parsed

    @model_validator(mode="after")
    def _validate_content(self) -> Case:
        for index, message in enumerate(self.messages):
            absent = missing_vars(message.content, self.vars)
            if absent:
                raise ValueError(
                    f"case {self.id!r}: messages[{index}].content references "
                    f"{{{{{absent[0]}}}}} but vars defines: {sorted(self.vars) or 'nothing'}"
                )
        ids = [assertion.assertion_id for assertion in self.assertions]
        duplicates = sorted({aid for aid in ids if ids.count(aid) > 1})
        if duplicates:
            raise ValueError(
                f"case {self.id!r}: duplicate assertion ids {duplicates} — "
                "assertion targets within a case must be distinct"
            )
        return self


class Suite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    suite: str
    description: str | None = None
    provider: ProviderConfig
    samples: int = Field(default=3, ge=1, le=20)
    concurrency: int = Field(default=4, ge=1, le=32)
    cases: list[Case] = Field(min_length=1)

    @field_validator("provider", mode="before")
    @classmethod
    def _unwrap_provider_key(cls, value: object) -> object:
        """Accept the YAML shape ``provider: {mock: {...}}`` — the single key
        names the provider type, so fold it into the ``type`` discriminator."""
        if isinstance(value, dict) and len(value) == 1 and "type" not in value:
            ((key, inner),) = value.items()
            if key in ("mock", "openai_compat"):
                if not isinstance(inner, dict):
                    raise ValueError(f"provider.{key} must be a mapping of provider options")
                return {"type": key, **inner}
        return value

    @field_validator("suite")
    @classmethod
    def _slug_suite(cls, value: str) -> str:
        return _check_slug("suite name", value)

    @model_validator(mode="after")
    def _unique_case_ids(self) -> Suite:
        ids = [case.id for case in self.cases]
        duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})
        if duplicates:
            raise ValueError(f"duplicate case ids: {duplicates}")
        return self

    @property
    def provider_id(self) -> str:
        return self.provider.provider_id

    @property
    def model_name(self) -> str:
        return self.provider.model_name

    def effective_samples(self, case: Case) -> int:
        return case.samples if case.samples is not None else self.samples

    def fingerprint(self) -> str:
        """Hash of everything that defines baseline comparability."""
        payload = {
            "version": self.version,
            "suite": self.suite,
            "samples": self.samples,
            "provider_identity": self.provider.identity(),
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()
