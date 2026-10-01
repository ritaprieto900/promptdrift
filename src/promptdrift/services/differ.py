"""Run → SuiteDiff orchestration, including the baseline staleness check."""

from __future__ import annotations

from promptdrift.domain.results import Run
from promptdrift.domain.snapshot import Snapshot
from promptdrift.domain.verdict import SuiteDiff, diff_run
from promptdrift.errors import StaleBaselineError

__all__ = ["compare", "ensure_comparable"]


def ensure_comparable(run: Run, snapshot: Snapshot) -> None:
    """Raise :class:`StaleBaselineError` unless run and snapshot are comparable.

    A fingerprint mismatch means the model, sampling parameters, or sample
    count changed since the baseline was approved. Comparing anyway would
    conflate configuration drift with prompt drift.
    """
    if run.config_fingerprint != snapshot.config_fingerprint:
        raise StaleBaselineError(
            "the baseline was recorded for a different configuration (model, sampling "
            "parameters, or sample count changed since the last `promptdrift approve`).\n"
            f"  baseline fingerprint: {snapshot.config_fingerprint}\n"
            f"  current fingerprint:  {run.config_fingerprint}\n"
            "Record a fresh baseline with `promptdrift approve`."
        )


def compare(run: Run, snapshot: Snapshot | None) -> SuiteDiff:
    """Diff a run against an optional baseline snapshot."""
    if snapshot is not None:
        ensure_comparable(run, snapshot)
    return diff_run(run, snapshot)
