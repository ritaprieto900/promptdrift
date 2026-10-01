"""Tests for YAML snapshot persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from promptdrift.adapters.snapshot_store import (
    load_snapshot,
    save_snapshot,
    snapshot_from_run,
    snapshot_path,
)
from promptdrift.errors import SnapshotLoadError


def test_missing_snapshot_returns_none(tmp_path: Path, mock_suite) -> None:
    assert load_snapshot(tmp_path, mock_suite.suite) is None


def test_roundtrip_preserves_everything(
    tmp_path: Path, mock_suite, run_factory, case_result_factory
) -> None:
    run = run_factory(
        [
            case_result_factory("refund", {"contains-申请退款": (2, 3)}, output="答案"),
            case_result_factory("invoice", {"is_json-yes": (3, 3)}, output='{"a": 1}'),
        ]
    )
    snapshot = snapshot_from_run(run, mock_suite)
    path = save_snapshot(tmp_path, snapshot)
    assert path == snapshot_path(tmp_path, mock_suite.suite)

    loaded = load_snapshot(tmp_path, mock_suite.suite)
    assert loaded is not None
    assert loaded.suite == snapshot.suite
    assert loaded.config_fingerprint == snapshot.config_fingerprint
    assert loaded.model == snapshot.model
    assert len(loaded.cases) == 2
    refund = loaded.case("refund")
    assert refund is not None
    assert refund.assertions["contains-申请退款"].passed == 2
    assert refund.assertions["contains-申请退款"].total == 3
    assert refund.representative_output == "答案"
    invoice = loaded.case("invoice")
    assert invoice is not None
    assert invoice.mean_prompt_tokens == pytest.approx(10.0)


def test_long_outputs_are_truncated_for_review(
    tmp_path: Path, mock_suite, run_factory, case_result_factory
) -> None:
    from promptdrift.domain.snapshot import REPRESENTATIVE_OUTPUT_MAX_CHARS

    long_output = "很长的回答" * 200
    run = run_factory(
        [case_result_factory("refund", {"contains-申请退款": (3, 3)}, output=long_output)]
    )
    snapshot = snapshot_from_run(run, mock_suite)
    saved = snapshot.cases[0].representative_output
    assert len(saved) <= REPRESENTATIVE_OUTPUT_MAX_CHARS + 1  # + ellipsis
    assert saved.endswith("…")


def test_corrupt_yaml_raises_readable_error(tmp_path: Path, mock_suite) -> None:
    path = snapshot_path(tmp_path, mock_suite.suite)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("::: not yaml [", encoding="utf-8")
    with pytest.raises(SnapshotLoadError):
        load_snapshot(tmp_path, mock_suite.suite)


def test_invalid_snapshot_content_raises(tmp_path: Path, mock_suite) -> None:
    path = snapshot_path(tmp_path, mock_suite.suite)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("version: 9\nsuite: x\n", encoding="utf-8")
    with pytest.raises(SnapshotLoadError):
        load_snapshot(tmp_path, mock_suite.suite)


def test_rates_in_yaml_are_human_reviewable(
    tmp_path: Path, mock_suite, run_factory, case_result_factory
) -> None:
    run = run_factory([case_result_factory("refund", {"contains-申请退款": (3, 3)})])
    path = save_snapshot(tmp_path, snapshot_from_run(run, mock_suite))
    text = path.read_text(encoding="utf-8")
    assert "passed: 3" in text
    assert "total: 3" in text
    assert "contains-申请退款" in text
