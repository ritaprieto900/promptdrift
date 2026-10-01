"""Tests for the minimal ``{{var}}`` template engine."""

from __future__ import annotations

import pytest

from promptdrift.domain.templates import (
    MissingTemplateVarError,
    missing_vars,
    referenced_vars,
    render,
)


def test_substitutes_named_vars() -> None:
    assert render("你好 {{name}}", {"name": "世界"}) == "你好 世界"


def test_coerces_values_to_str() -> None:
    assert render("订单 {{n}} 个", {"n": 3}) == "订单 3 个"


def test_whitespace_tolerant() -> None:
    assert render("{{ topic }}!", {"topic": "x"}) == "x!"


def test_multiple_occurrences_and_order() -> None:
    assert render("{{a}}-{{b}}-{{a}}", {"a": "1", "b": "2"}) == "1-2-1"


def test_unmatched_braces_pass_through() -> None:
    template = '{"key": "{{value}}", "literal": "{"}'
    assert render(template, {"value": "1"}) == '{"key": "1", "literal": "{"}'


def test_triple_braces_degrade_to_literal_plus_substitution() -> None:
    assert render("{{{a}}}", {"a": "x"}) == "{x}"


def test_missing_var_raises_with_helpful_message() -> None:
    with pytest.raises(MissingTemplateVarError) as excinfo:
        render("{{topic}}", {"other": "1"})
    message = str(excinfo.value)
    assert "topic" in message
    assert "other" in message


def test_missing_var_with_no_vars_defined() -> None:
    with pytest.raises(MissingTemplateVarError) as excinfo:
        render("{{topic}}", {})
    assert "<none defined>" in str(excinfo.value)


def test_referenced_vars_dedupes_in_order() -> None:
    assert referenced_vars("{{b}} {{a}} {{b}}") == ["b", "a"]


def test_missing_vars_returns_only_unknown() -> None:
    assert missing_vars("{{a}} {{b}} {{c}}", ["a", "c"]) == ["b"]
