"""Tests for the deterministic assertion registry."""

from __future__ import annotations

from typing import ClassVar

import pytest

from promptdrift.domain.assertions import (
    CompletionTokensUnder,
    Contains,
    Equals,
    IsJson,
    JsonSchema,
    LatencyUnder,
    NotContains,
    Regex,
)
from promptdrift.domain.results import TokenUsage

USAGE = TokenUsage(prompt_tokens=10, completion_tokens=20)


def check(assertion: object, output: str, latency_ms: float = 50.0, usage: TokenUsage = USAGE):
    return assertion.check(output, usage, latency_ms)  # type: ignore[attr-defined]


class TestContains:
    def test_pass_and_fail(self) -> None:
        assertion = Contains(contains="退款")
        assert check(assertion, "请申请退款，谢谢").passed
        outcome = check(assertion, "无法办理")
        assert not outcome.passed
        assert "退款" in (outcome.detail or "")

    def test_stable_id_from_target(self) -> None:
        assert Contains(contains="退款").assertion_id == "contains-退款"
        assert Contains(contains="hello world").assertion_id == "contains-hello-world"


class TestNotContains:
    def test_pass_and_fail(self) -> None:
        assert check(NotContains(not_contains="抱歉"), "好的").passed
        assert not check(NotContains(not_contains="抱歉"), "抱歉做不到").passed


class TestEquals:
    def test_exact_match_no_trim(self) -> None:
        assert check(Equals(equals="ok"), "ok").passed
        assert not check(Equals(equals="ok"), "ok ").passed


class TestRegex:
    def test_anchor_and_multiline(self) -> None:
        assertion = Regex(regex=r"^步骤 1")
        assert check(assertion, "步骤 1：打开订单页\n步骤 2：等待审核").passed
        assert not check(assertion, "先做别的\n步骤 1：太晚了").passed

    def test_dotall_crosses_newlines(self) -> None:
        assertion = Regex(regex=r"开头.*结尾")
        assert check(assertion, "开头\n中间\n结尾").passed

    def test_invalid_pattern_rejected_at_load(self) -> None:
        with pytest.raises(ValueError, match="invalid regex"):
            Regex(regex="([unclosed")


class TestIsJson:
    def test_pass_and_fail(self) -> None:
        assert check(IsJson(is_json=True), '{"a": 1}').passed
        outcome = check(IsJson(is_json=True), "not json {")
        assert not outcome.passed
        assert "JSON" in (outcome.detail or "")


class TestJsonSchema:
    SCHEMA: ClassVar[dict] = {"type": "object", "required": ["order_id"]}

    def test_valid_document(self) -> None:
        assert check(JsonSchema(json_schema=self.SCHEMA), '{"order_id": "A1"}').passed

    def test_violation_reports_path(self) -> None:
        outcome = check(JsonSchema(json_schema=self.SCHEMA), '{"wrong": 1}')
        assert not outcome.passed
        assert "order_id" in (outcome.detail or "")

    def test_non_json_output(self) -> None:
        assert not check(JsonSchema(json_schema=self.SCHEMA), "hello").passed

    def test_id_is_schema_hash(self) -> None:
        a = JsonSchema(json_schema={"type": "object", "required": ["a"]})
        b = JsonSchema(json_schema={"required": ["a"], "type": "object"})
        assert a.assertion_id == b.assertion_id
        assert a.assertion_id.startswith("json_schema-")
        assert len(a.assertion_id) == len("json_schema-") + 8


class TestLatencyUnder:
    def test_boundary_is_inclusive(self) -> None:
        assertion = LatencyUnder(latency_under=200)
        assert check(assertion, "x", latency_ms=200.0).passed
        assert not check(assertion, "x", latency_ms=200.1).passed

    def test_detail_reports_actual(self) -> None:
        outcome = check(LatencyUnder(latency_under=100), "x", latency_ms=350.0)
        assert "350" in (outcome.detail or "")


class TestCompletionTokensUnder:
    def test_budget(self) -> None:
        assertion = CompletionTokensUnder(completion_tokens_under=100)
        assert check(assertion, "x", usage=TokenUsage(prompt_tokens=1, completion_tokens=99)).passed
        outcome = check(assertion, "x", usage=TokenUsage(prompt_tokens=1, completion_tokens=101))
        assert not outcome.passed
        assert "101" in (outcome.detail or "")


def test_assertion_ids_are_unique_per_distinct_target() -> None:
    ids = {
        Contains(contains="a").assertion_id,
        Contains(contains="b").assertion_id,
        NotContains(not_contains="a").assertion_id,
    }
    assert len(ids) == 3


def test_cjk_target_survives_slug() -> None:
    assert Contains(contains="申请退款").assertion_id == "contains-申请退款"
