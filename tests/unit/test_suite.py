"""Tests for suite validation, template checks, and the config fingerprint."""

from __future__ import annotations

import pytest

from promptdrift.domain.suite import Suite
from promptdrift.errors import SuiteLoadError
from promptdrift.services.loader import suite_from_dict
from tests.conftest import MOCK_SUITE_YAML, suite_from_yaml_text

# ``tests.conftest`` import works because pytest adds the tests dir to sys.path
# via conftest.py discovery (no package needed).


def test_valid_mock_suite_loads(mock_suite: Suite) -> None:
    assert mock_suite.suite == "it-suite"
    assert mock_suite.provider_id == "mock"
    assert mock_suite.model_name == "mock"
    assert [case.id for case in mock_suite.cases] == ["refund", "invoice"]
    assert mock_suite.fingerprint().startswith("sha256:")


def test_unknown_assertion_key_rejected() -> None:
    raw = {
        "suite": "s",
        "provider": {"mock": {}},
        "cases": [
            {
                "id": "c",
                "messages": [{"role": "user", "content": "hi"}],
                "assertions": [{"fuzzy": "x"}],
            }
        ],
    }
    with pytest.raises(SuiteLoadError) as excinfo:
        suite_from_dict(raw)
    assert "unknown assertion 'fuzzy'" in str(excinfo.value)


def test_multi_key_assertion_rejected() -> None:
    raw = {
        "suite": "s",
        "provider": {"mock": {}},
        "cases": [
            {
                "id": "c",
                "messages": [{"role": "user", "content": "hi"}],
                "assertions": [{"contains": "a", "regex": "b"}],
            }
        ],
    }
    with pytest.raises(SuiteLoadError) as excinfo:
        suite_from_dict(raw)
    assert "single-key" in str(excinfo.value)


def test_missing_template_var_rejected_with_case_context() -> None:
    raw = {
        "suite": "s",
        "provider": {"mock": {}},
        "cases": [
            {
                "id": "c",
                "messages": [{"role": "user", "content": "hello {{name}}"}],
            }
        ],
    }
    with pytest.raises(SuiteLoadError) as excinfo:
        suite_from_dict(raw)
    assert "name" in str(excinfo.value)
    assert "case 'c'" in str(excinfo.value)


def test_duplicate_assertion_ids_rejected() -> None:
    raw = {
        "suite": "s",
        "provider": {"mock": {}},
        "cases": [
            {
                "id": "c",
                "messages": [{"role": "user", "content": "hi"}],
                "assertions": [{"contains": "same"}, {"contains": "same"}],
            }
        ],
    }
    with pytest.raises(SuiteLoadError) as excinfo:
        suite_from_dict(raw)
    assert "duplicate assertion ids" in str(excinfo.value)


def test_duplicate_case_ids_rejected() -> None:
    raw = {
        "suite": "s",
        "provider": {"mock": {}},
        "cases": [
            {"id": "c", "messages": [{"role": "user", "content": "hi"}]},
            {"id": "c", "messages": [{"role": "user", "content": "ho"}]},
        ],
    }
    with pytest.raises(SuiteLoadError) as excinfo:
        suite_from_dict(raw)
    assert "duplicate case ids" in str(excinfo.value)


def test_non_kebab_ids_rejected() -> None:
    raw = {
        "suite": "My Suite",
        "provider": {"mock": {}},
        "cases": [{"id": "c", "messages": [{"role": "user", "content": "hi"}]}],
    }
    with pytest.raises(SuiteLoadError) as excinfo:
        suite_from_dict(raw)
    assert "kebab-case" in str(excinfo.value)


def test_vars_are_stringified() -> None:
    raw = {
        "suite": "s",
        "provider": {"mock": {}},
        "cases": [
            {
                "id": "c",
                "messages": [{"role": "user", "content": "n={{n}}"}],
                "vars": {"n": 5},
            }
        ],
    }
    suite = suite_from_dict(raw)
    assert suite.cases[0].vars == {"n": "5"}


def test_schema_key_is_ignored() -> None:
    raw = {
        "$schema": "https://example.invalid/schema.json",
        "suite": "s",
        "provider": {"mock": {}},
        "cases": [{"id": "c", "messages": [{"role": "user", "content": "hi"}]}],
    }
    assert suite_from_dict(raw).suite == "s"


class TestFingerprint:
    def _base(self) -> dict:
        return {
            "suite": "s",
            "provider": {
                "mock": {
                    "rules": [{"contains": "hi", "text": "你好"}],
                    "default": "嗯",
                }
            },
            "samples": 3,
            "cases": [{"id": "c", "messages": [{"role": "user", "content": "hi"}]}],
        }

    def test_key_order_independent(self) -> None:
        import json as _json

        reordered = _json.loads(_json.dumps(self._base()))
        assert (
            suite_from_dict(self._base()).fingerprint() == suite_from_dict(reordered).fingerprint()
        )

    def test_mock_rule_text_does_not_stale_the_baseline(self) -> None:
        """Editing mock answers is a *prompt change* — diffs must measure it."""
        changed = self._base()
        changed["provider"]["mock"]["rules"][0]["text"] = "改成别的回答"
        assert suite_from_dict(self._base()).fingerprint() == suite_from_dict(changed).fingerprint()

    def test_prompt_text_and_vars_do_not_stale_the_baseline(self) -> None:
        changed = self._base()
        changed["cases"][0]["messages"][0]["content"] = "变了的问题"
        changed["cases"][0]["vars"] = {"x": "y"}
        assert suite_from_dict(self._base()).fingerprint() == suite_from_dict(changed).fingerprint()

    def test_sample_count_changes_fingerprint(self) -> None:
        changed = self._base()
        changed["samples"] = 5
        assert suite_from_dict(self._base()).fingerprint() != suite_from_dict(changed).fingerprint()

    def test_model_change_changes_fingerprint(self) -> None:
        def with_provider(provider: dict) -> dict:
            raw = self._base()
            raw["provider"] = provider
            return raw

        a = with_provider({"openai_compat": {"model": "glm-4.7"}})
        b = with_provider({"openai_compat": {"model": "glm-4.7-air"}})
        assert suite_from_dict(a).fingerprint() != suite_from_dict(b).fingerprint()

    def test_pricing_change_does_not_change_fingerprint(self) -> None:
        def with_provider(provider: dict) -> dict:
            raw = self._base()
            raw["provider"] = provider
            return raw

        a = with_provider({"openai_compat": {"model": "m"}})
        b = with_provider(
            {
                "openai_compat": {
                    "model": "m",
                    "pricing": {"prompt_per_1m": 1.0, "completion_per_1m": 2.0},
                }
            }
        )
        assert suite_from_dict(a).fingerprint() == suite_from_dict(b).fingerprint()


def test_mock_suite_from_fixture_yaml() -> None:
    suite = suite_from_yaml_text(MOCK_SUITE_YAML)
    assert suite.effective_samples(suite.cases[0]) == 3
    assert suite.effective_samples(suite.cases[1]) == 3
