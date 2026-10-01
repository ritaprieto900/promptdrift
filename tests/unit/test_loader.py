"""Tests for suite loader error paths and suite-file resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from promptdrift.errors import SuiteLoadError
from promptdrift.services.loader import load_suite, resolve_suite_path, suite_from_dict


def test_non_dict_top_level_rejected() -> None:
    with pytest.raises(SuiteLoadError, match="expected a YAML mapping"):
        suite_from_dict(["not", "a", "mapping"])


def test_invalid_yaml_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("key: [unclosed", encoding="utf-8")
    with pytest.raises(SuiteLoadError, match="not valid YAML"):
        load_suite(path)


def test_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(SuiteLoadError, match="cannot read"):
        load_suite(tmp_path / "missing.yaml")


def test_resolve_explicit_relative_path(tmp_path: Path) -> None:
    suite = tmp_path / "mysuite.yaml"
    suite.write_text("content", encoding="utf-8")
    resolved = resolve_suite_path(tmp_path, Path("mysuite.yaml"))
    assert resolved == suite


def test_resolve_default_filename(tmp_path: Path) -> None:
    (tmp_path / "promptest.yaml").write_text("x", encoding="utf-8")
    assert resolve_suite_path(tmp_path, None) == tmp_path / "promptest.yaml"


def test_resolve_falls_back_to_named_suite(tmp_path: Path) -> None:
    (tmp_path / "billing.promptest.yaml").write_text("x", encoding="utf-8")
    assert resolve_suite_path(tmp_path, None) == tmp_path / "billing.promptest.yaml"


def test_resolve_nothing_found(tmp_path: Path) -> None:
    with pytest.raises(SuiteLoadError, match="no suite file found"):
        resolve_suite_path(tmp_path, None)
