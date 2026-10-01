"""The verdict engine: statistical comparison of a run against a baseline.

Pure functions and models, no I/O. The semantics here are what make
promptdrift gates trustworthy instead of noisy:

- Per-assertion pass rates are compared with Wilson score intervals
  (z ≈ 1.96). A verdict of *regressed* or *improved* requires the intervals
  to separate — sampling noise alone can never fail a gate.
- An all-pass → all-fail (or reverse) flip is always significant, whatever
  the sample count.
- A previously pure (0% or 100%) baseline whose new samples now disagree
  with each other is ``unstable``: a warning by default, upgradeable to a
  gate failure with ``--fail-on flaky``.

Small samples are intentionally forgiving. With ``samples: 3`` a 3/3 → 2/3
drop is ``unstable``, not ``regressed``; raise the sample count to sharpen
the statistics. A mixed baseline likewise reduces detection power — approve
baselines from stable runs.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from promptdrift.domain.results import CaseResult, Run
from promptdrift.domain.snapshot import (
    Snapshot,
    SnapshotCase,
    SnapshotRate,
    wilson_interval,
)

__all__ = [
    "AssertionDiff",
    "CaseDiff",
    "FailOn",
    "SuiteDiff",
    "Verdict",
    "classify_assertion",
    "diff_case",
    "diff_run",
    "wilson_interval",
]


class Verdict(str, Enum):
    REGRESSED = "regressed"
    IMPROVED = "improved"
    STABLE = "stable"
    UNSTABLE = "unstable"
    NEW = "new"
    REMOVED = "removed"

    def __str__(self) -> str:
        return self.value

    @property
    def icon(self) -> str:
        return _ICONS[self]

    @property
    def severity(self) -> int:
        return _SEVERITY[self]


_ICONS: dict[Verdict, str] = {
    Verdict.REGRESSED: "🔴",
    Verdict.IMPROVED: "🟢",
    Verdict.UNSTABLE: "⚠️",
    Verdict.NEW: "🆕",
    Verdict.REMOVED: "➖",
    Verdict.STABLE: "✅",
}

# Higher severity wins when aggregating a case/suite verdict.
_SEVERITY: dict[Verdict, int] = {
    Verdict.REGRESSED: 4,
    Verdict.UNSTABLE: 3,
    Verdict.NEW: 2,
    Verdict.IMPROVED: 1,
    Verdict.REMOVED: 1,
    Verdict.STABLE: 0,
}


class FailOn(str, Enum):
    """What ``promptdrift diff`` treats as a gate failure."""

    REGRESSION = "regression"
    FLAKY = "flaky"
    ANY_FAIL = "any-fail"

    def __str__(self) -> str:
        return self.value


def classify_assertion(base: SnapshotRate | None, new: SnapshotRate) -> tuple[Verdict, str]:
    """Classify one assertion's new rate against its baseline rate.

    Returns ``(verdict, human-readable justification)``.
    """
    if base is None:
        return Verdict.NEW, "no baseline recorded for this assertion"
    base_lo, base_hi = base.wilson()
    new_lo, new_hi = new.wilson()
    if base.rate == 1.0 and new.rate == 0.0:
        return (
            Verdict.REGRESSED,
            f"all {new.total} samples failed (baseline {base.passed}/{base.total})",
        )
    if base.rate == 0.0 and new.rate == 1.0:
        return (
            Verdict.IMPROVED,
            f"all {new.total} samples passed (baseline {base.passed}/{base.total})",
        )
    if base_lo > new_hi:
        return Verdict.REGRESSED, (
            f"pass rate {base.rate:.0%} → {new.rate:.0%} falls beyond noise "
            f"(baseline interval [{base_lo:.0%}, {base_hi:.0%}])"
        )
    if new_lo > base_hi:
        return Verdict.IMPROVED, (
            f"pass rate {base.rate:.0%} → {new.rate:.0%} rises beyond noise "
            f"(baseline interval [{base_lo:.0%}, {base_hi:.0%}])"
        )
    if base.rate in (0.0, 1.0) and 0.0 < new.rate < 1.0:
        return Verdict.UNSTABLE, (
            f"samples disagree ({new.passed}/{new.total} passed) where baseline was {base.rate:.0%}"
        )
    return Verdict.STABLE, f"{base.rate:.0%} → {new.rate:.0%}, within noise"


class AssertionDiff(BaseModel):
    assertion_id: str
    assertion_type: str
    base: SnapshotRate | None = None
    new: SnapshotRate
    verdict: Verdict
    detail: str = ""


class CaseDiff(BaseModel):
    case_id: str
    verdict: Verdict
    assertions: list[AssertionDiff] = Field(default_factory=list)
    is_new_case: bool = False
    is_removed: bool = False
    representative_before: str = ""
    representative_after: str = ""

    @property
    def changed(self) -> bool:
        return self.verdict is not Verdict.STABLE


class SuiteDiff(BaseModel):
    suite: str
    has_baseline: bool
    verdict: Verdict = Verdict.STABLE
    score_before: float | None = None
    score_after: float = 0.0
    cases: list[CaseDiff] = Field(default_factory=list)

    def count(self, verdict: Verdict) -> int:
        return sum(1 for case in self.cases if case.verdict is verdict)

    @property
    def changed_cases(self) -> list[CaseDiff]:
        return [case for case in self.cases if case.changed]

    def gate(self, fail_on: FailOn) -> tuple[bool, str]:
        """Return ``(passed, reason)`` for the CI gate decision."""
        if not self.has_baseline:
            return True, "no baseline yet — run `promptdrift approve` to record one"
        reasons: list[str] = []
        regressed = self.count(Verdict.REGRESSED)
        unstable = self.count(Verdict.UNSTABLE)
        if fail_on is FailOn.REGRESSION:
            if regressed:
                reasons.append(f"{regressed} regressed case(s)")
        elif fail_on is FailOn.FLAKY:
            if regressed:
                reasons.append(f"{regressed} regressed case(s)")
            if unstable:
                reasons.append(f"{unstable} unstable case(s)")
        elif fail_on is FailOn.ANY_FAIL:
            imperfect = [
                case
                for case in self.cases
                if not case.is_removed
                and case.assertions
                and any(d.new.rate < 1.0 for d in case.assertions)
            ]
            if imperfect:
                reasons.append(f"{len(imperfect)} case(s) with imperfect pass rates")
        if reasons:
            return False, "; ".join(reasons)
        return True, "gate passed"


def _worst(verdicts: list[Verdict]) -> Verdict:
    if not verdicts:
        return Verdict.STABLE
    return max(verdicts, key=lambda v: v.severity)


def _run_case_score(case: CaseResult) -> float | None:
    rates = [SnapshotRate.from_pair(pair).rate for pair in case.rates().values()]
    if not rates:
        return None
    return sum(rates) / len(rates)


def _snapshot_case_score(case: SnapshotCase) -> float | None:
    rates = [rate.rate for rate in case.assertions.values()]
    if not rates:
        return None
    return sum(rates) / len(rates)


def _diff_one(
    assertion_id: str, assertion_type: str, base: SnapshotRate | None, new: SnapshotRate
) -> AssertionDiff:
    verdict, detail = classify_assertion(base, new)
    return AssertionDiff(
        assertion_id=assertion_id,
        assertion_type=assertion_type,
        base=base,
        new=new,
        verdict=verdict,
        detail=detail,
    )


def diff_case(run_case: CaseResult | None, baseline_case: SnapshotCase | None) -> CaseDiff:
    """Diff one case: run-side vs baseline-side. Either side may be absent."""
    if run_case is None:
        if baseline_case is None:  # pragma: no cover - callers guarantee this
            raise ValueError("diff_case needs at least one side")
        return CaseDiff(case_id=baseline_case.id, verdict=Verdict.REMOVED, is_removed=True)

    rates = run_case.rates()
    if baseline_case is None:
        assertions = [
            _diff_one(
                aid,
                run_case.assertion_type(aid) or "unknown",
                None,
                SnapshotRate.from_pair(pair),
            )
            for aid, pair in sorted(rates.items())
        ]
        return CaseDiff(
            case_id=run_case.case_id,
            verdict=_worst([d.verdict for d in assertions]) if assertions else Verdict.NEW,
            assertions=assertions,
            is_new_case=True,
            representative_after=run_case.representative_output(),
        )

    assertions = [
        _diff_one(
            aid,
            run_case.assertion_type(aid) or "unknown",
            baseline_case.assertions.get(aid),
            SnapshotRate.from_pair(pair),
        )
        for aid, pair in sorted(rates.items())
    ]
    return CaseDiff(
        case_id=run_case.case_id,
        verdict=_worst([d.verdict for d in assertions]),
        assertions=assertions,
        representative_before=baseline_case.representative_output,
        representative_after=run_case.representative_output(),
    )


def diff_run(run: Run, snapshot: Snapshot | None) -> SuiteDiff:
    """Diff a whole run against a snapshot (or produce a no-baseline diff)."""
    run_by_id = {case.case_id: case for case in run.cases}

    if snapshot is None:
        cases = [diff_case(run_case, None) for run_case in run.cases]
        after_scores = [score for case in run.cases if (score := _run_case_score(case)) is not None]
        return SuiteDiff(
            suite=run.suite,
            has_baseline=False,
            verdict=_worst([case.verdict for case in cases]),
            score_before=None,
            score_after=sum(after_scores) / len(after_scores) if after_scores else 0.0,
            cases=cases,
        )

    baseline_by_id = {case.id: case for case in snapshot.cases}
    cases: list[CaseDiff] = []
    for run_case in run.cases:
        cases.append(diff_case(run_case, baseline_by_id.get(run_case.case_id)))
    for snapshot_case in snapshot.cases:
        if snapshot_case.id not in run_by_id:
            cases.append(diff_case(None, snapshot_case))

    comparable_scores = [
        score
        for run_case in run.cases
        if (snapshot_case := baseline_by_id.get(run_case.case_id)) is not None
        and (score := _snapshot_case_score(snapshot_case)) is not None
    ]
    after_scores = [score for case in run.cases if (score := _run_case_score(case)) is not None]

    return SuiteDiff(
        suite=run.suite,
        has_baseline=True,
        verdict=_worst([case.verdict for case in cases]),
        score_before=(
            sum(comparable_scores) / len(comparable_scores) if comparable_scores else None
        ),
        score_after=sum(after_scores) / len(after_scores) if after_scores else 0.0,
        cases=sorted(cases, key=lambda case: case.case_id),
    )
