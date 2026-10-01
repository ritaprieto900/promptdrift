"""YAML persistence for baseline snapshots.

Baselines live at ``<root>/.promptest/baselines/<suite>.snap.yaml`` and are
meant to be committed alongside the suite file — a diff of the snapshot file
in a PR *is* a human-readable record of the behavior change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from promptdrift.domain.results import Run
from promptdrift.domain.snapshot import (
    REPRESENTATIVE_OUTPUT_MAX_CHARS,
    Snapshot,
    SnapshotCase,
    SnapshotRate,
)
from promptdrift.domain.suite import Suite
from promptdrift.errors import SnapshotLoadError


def snapshot_path(root: Path, suite: str) -> Path:
    return root / ".promptest" / "baselines" / f"{suite}.snap.yaml"


def load_snapshot(root: Path, suite: str) -> Snapshot | None:
    path = snapshot_path(root, suite)
    if not path.exists():
        return None
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SnapshotLoadError(f"{path} is not valid YAML: {exc}") from exc
    try:
        return Snapshot.model_validate(raw)
    except ValueError as exc:
        raise SnapshotLoadError(f"{path} does not match the snapshot schema: {exc}") from exc


def save_snapshot(root: Path, snapshot: Snapshot) -> Path:
    path = snapshot_path(root, snapshot.suite)
    path.parent.mkdir(parents=True, exist_ok=True)
    dumped = snapshot.model_dump(mode="json")
    path.write_text(yaml.safe_dump(dumped, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def snapshot_from_run(run: Run, suite: Suite) -> Snapshot:
    """Capture a run as the new baseline, truncated for human review."""
    cases: list[SnapshotCase] = []
    for case_result in run.cases:
        mean_prompt, mean_completion = case_result.mean_tokens()
        representative = case_result.representative_output()
        if len(representative) > REPRESENTATIVE_OUTPUT_MAX_CHARS:
            representative = representative[:REPRESENTATIVE_OUTPUT_MAX_CHARS] + "…"
        cases.append(
            SnapshotCase(
                id=case_result.case_id,
                samples=len(case_result.samples),
                mean_latency_ms=round(case_result.mean_latency_ms(), 1),
                mean_prompt_tokens=round(mean_prompt, 1),
                mean_completion_tokens=round(mean_completion, 1),
                representative_output=representative,
                assertions={
                    aid: SnapshotRate.from_pair(pair) for aid, pair in case_result.rates().items()
                },
            )
        )
    return Snapshot(
        suite=run.suite,
        model=run.model,
        config_fingerprint=run.config_fingerprint,
        recorded_at=datetime.now(timezone.utc),
        cases=cases,
    )
