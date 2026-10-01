"""Tests for the statistical verdict engine — the heart of promptdrift.

The reference values here were cross-checked by hand against the Wilson
score interval formula; they pin the *semantics*, not just the arithmetic:
noise alone must never produce a regression verdict.
"""

from __future__ import annotations

import pytest

from promptdrift.domain.snapshot import SnapshotRate, wilson_interval
from promptdrift.domain.verdict import (
    FailOn,
    SuiteDiff,
    Verdict,
    classify_assertion,
    diff_case,
    diff_run,
)
from tests.conftest import make_case_result, make_run, make_snapshot


class TestWilsonInterval:
    # Reference values computed with Z_95 = 1.959963984540054.
    def test_known_values(self) -> None:
        lo, hi = wilson_interval(3, 3)
        assert lo == pytest.approx(0.43850, abs=5e-5)
        assert hi == pytest.approx(1.0, abs=1e-4)

        lo, hi = wilson_interval(0, 3)
        assert lo == 0.0
        assert hi == pytest.approx(0.56150, abs=5e-5)

        lo, hi = wilson_interval(5, 5)
        assert lo == pytest.approx(0.56552, abs=5e-5)
        assert hi == 1.0

        lo, hi = wilson_interval(0, 5)
        assert lo == 0.0
        assert hi == pytest.approx(0.43448, abs=5e-5)

    def test_symmetry_around_half(self) -> None:
        lo, hi = wilson_interval(2, 5)
        lo_flipped, hi_flipped = wilson_interval(3, 5)
        assert lo == pytest.approx(1 - hi_flipped, abs=1e-9)
        assert hi == pytest.approx(1 - lo_flipped, abs=1e-9)

    def test_clamped_to_unit_interval(self) -> None:
        for passed in range(11):
            lo, hi = wilson_interval(passed, 10)
            assert 0.0 <= lo <= hi <= 1.0

    def test_invalid_total_rejected(self) -> None:
        with pytest.raises(ValueError):
            wilson_interval(1, 0)


class TestClassifyAssertion:
    def test_no_baseline_is_new(self) -> None:
        verdict, _ = classify_assertion(None, SnapshotRate(passed=3, total=3))
        assert verdict is Verdict.NEW

    def test_pure_flip_to_fail_is_regressed_even_at_n1(self) -> None:
        verdict, detail = classify_assertion(
            SnapshotRate(passed=1, total=1), SnapshotRate(passed=0, total=1)
        )
        assert verdict is Verdict.REGRESSED
        assert "failed" in detail

    def test_pure_flip_to_pass_is_improved(self) -> None:
        verdict, _ = classify_assertion(
            SnapshotRate(passed=0, total=3), SnapshotRate(passed=3, total=3)
        )
        assert verdict is Verdict.IMPROVED

    def test_pure_to_mixed_is_unstable_not_regressed(self) -> None:
        """3/3 → 2/3 is the classic flake — a warning, never a gate failure."""
        verdict, detail = classify_assertion(
            SnapshotRate(passed=3, total=3), SnapshotRate(passed=2, total=3)
        )
        assert verdict is Verdict.UNSTABLE
        assert "disagree" in detail

    def test_unchanged_is_stable(self) -> None:
        verdict, _ = classify_assertion(
            SnapshotRate(passed=3, total=3), SnapshotRate(passed=3, total=3)
        )
        assert verdict is Verdict.STABLE

    def test_within_noise_is_stable(self) -> None:
        verdict, _ = classify_assertion(
            SnapshotRate(passed=2, total=3), SnapshotRate(passed=3, total=3)
        )
        assert verdict is Verdict.STABLE

    def test_significant_drop_at_n10_is_regressed(self) -> None:
        verdict, detail = classify_assertion(
            SnapshotRate(passed=10, total=10), SnapshotRate(passed=3, total=10)
        )
        assert verdict is Verdict.REGRESSED
        assert "beyond noise" in detail

    def test_significant_rise_at_n10_is_improved(self) -> None:
        verdict, _ = classify_assertion(
            SnapshotRate(passed=0, total=10), SnapshotRate(passed=7, total=10)
        )
        assert verdict is Verdict.IMPROVED

    def test_pure_to_slightly_mixed_at_n10_is_unstable(self) -> None:
        verdict, _ = classify_assertion(
            SnapshotRate(passed=10, total=10), SnapshotRate(passed=8, total=10)
        )
        assert verdict is Verdict.UNSTABLE

    def test_mixed_baseline_is_forgiving(self) -> None:
        """An already-noisy baseline can't support a regression claim."""
        verdict, _ = classify_assertion(
            SnapshotRate(passed=2, total=3), SnapshotRate(passed=0, total=3)
        )
        assert verdict is Verdict.STABLE


class TestDiffCase:
    def test_new_case(self) -> None:
        case_diff = diff_case(make_case_result("c", {"contains-a": (3, 3)}, output="hi"), None)
        assert case_diff.verdict is Verdict.NEW
        assert case_diff.is_new_case
        assert case_diff.representative_after == "hi"

    def test_removed_case(self) -> None:
        snapshot_case = make_snapshot([("c", {"contains-a": (3, 3)}, "old")]).cases[0]
        case_diff = diff_case(None, snapshot_case)
        assert case_diff.verdict is Verdict.REMOVED
        assert case_diff.is_removed

    def test_case_verdict_takes_the_worst_assertion(self) -> None:
        run_case = make_case_result("c", {"contains-a": (0, 3), "contains-b": (3, 3)})
        snapshot_case = make_snapshot(
            [("c", {"contains-a": (3, 3), "contains-b": (0, 3)}, "old")]
        ).cases[0]
        case_diff = diff_case(run_case, snapshot_case)
        verdicts = {d.verdict for d in case_diff.assertions}
        assert verdicts == {Verdict.REGRESSED, Verdict.IMPROVED}
        assert case_diff.verdict is Verdict.REGRESSED

    def test_representatives_captured(self) -> None:
        run_case = make_case_result("c", {"contains-a": (3, 3)}, output="new text")
        snapshot_case = make_snapshot([("c", {"contains-a": (3, 3)}, "old text")]).cases[0]
        case_diff = diff_case(run_case, snapshot_case)
        assert case_diff.representative_before == "old text"
        assert case_diff.representative_after == "new text"
        assert case_diff.verdict is Verdict.STABLE


class TestDiffRun:
    def test_without_baseline(self) -> None:
        run = make_run([make_case_result("a", {"contains-x": (3, 3)})])
        suite_diff = diff_run(run, None)
        assert not suite_diff.has_baseline
        assert suite_diff.score_before is None
        assert all(case.verdict is Verdict.NEW for case in suite_diff.cases)

    def test_removed_cases_are_reported_and_sorted(self) -> None:
        run = make_run([make_case_result("a", {"contains-x": (3, 3)})])
        snapshot = make_snapshot(
            [
                ("a", {"contains-x": (3, 3)}, "x"),
                ("legacy", {"contains-y": (3, 3)}, "y"),
            ]
        )
        suite_diff = diff_run(run, snapshot)
        assert [case.case_id for case in suite_diff.cases] == ["a", "legacy"]
        assert suite_diff.cases[1].verdict is Verdict.REMOVED

    def test_score_before_uses_comparable_cases_only(self) -> None:
        run = make_run([make_case_result("a", {"contains-x": (3, 3)})])
        snapshot = make_snapshot(
            [
                ("a", {"contains-x": (3, 3)}, "x"),
                ("legacy", {"contains-y": (0, 3)}, "y"),  # would drag the score
            ]
        )
        suite_diff = diff_run(run, snapshot)
        assert suite_diff.score_before == pytest.approx(1.0)
        assert suite_diff.score_after == pytest.approx(1.0)


class TestGate:
    def _diff(self, cases, baseline) -> SuiteDiff:
        return diff_run(make_run(cases), make_snapshot(baseline))

    def test_no_baseline_passes(self) -> None:
        suite_diff = diff_run(make_run([make_case_result("a", {"x": (3, 3)})]), None)
        passed, reason = suite_diff.gate(FailOn.REGRESSION)
        assert passed
        assert "no baseline" in reason

    def test_regression_fails_default_gate(self) -> None:
        suite_diff = self._diff(
            [make_case_result("a", {"contains-x": (0, 3)})],
            [("a", {"contains-x": (3, 3)}, "x")],
        )
        passed, reason = suite_diff.gate(FailOn.REGRESSION)
        assert not passed
        assert "1 regressed" in reason

    def test_unstable_passes_default_gate_but_fails_flaky(self) -> None:
        suite_diff = self._diff(
            [make_case_result("a", {"contains-x": (2, 3)})],
            [("a", {"contains-x": (3, 3)}, "x")],
        )
        assert suite_diff.gate(FailOn.REGRESSION)[0]
        passed, reason = suite_diff.gate(FailOn.FLAKY)
        assert not passed
        assert "unstable" in reason

    def test_any_fail_catches_imperfect_new_case(self) -> None:
        suite_diff = self._diff(
            [make_case_result("new-case", {"contains-x": (2, 3)})],
            [],
        )
        passed, reason = suite_diff.gate(FailOn.ANY_FAIL)
        assert not passed
        assert "imperfect" in reason

    def test_any_fail_passes_perfect_run(self) -> None:
        suite_diff = self._diff(
            [make_case_result("a", {"contains-x": (3, 3)})],
            [("a", {"contains-x": (3, 3)}, "x")],
        )
        assert suite_diff.gate(FailOn.ANY_FAIL)[0]

    def test_improvement_passes_all_gates(self) -> None:
        suite_diff = self._diff(
            [make_case_result("a", {"contains-x": (3, 3)})],
            [("a", {"contains-x": (0, 3)}, "x")],
        )
        for fail_on in FailOn:
            assert suite_diff.gate(fail_on)[0]
