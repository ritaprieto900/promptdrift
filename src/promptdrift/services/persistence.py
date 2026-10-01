"""Persist the most recent run per suite (backs ``promptdrift show``).

This is a convenience cache, not a data store: baselines carry the durable
state, and the sqlite cache carries completions.
"""

from __future__ import annotations

import json
from pathlib import Path

from promptdrift.domain.results import Run
from promptdrift.errors import PromptdriftError


def runs_dir(root: Path) -> Path:
    return root / ".promptest" / "runs"


def save_run(root: Path, run: Run) -> Path:
    directory = runs_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"latest-{run.suite}.json"
    path.write_text(
        json.dumps(run.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_latest_run(root: Path, suite: str) -> Run | None:
    path = runs_dir(root) / f"latest-{suite}.json"
    if not path.exists():
        return None
    try:
        return Run.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError) as exc:
        raise PromptdriftError(f"{path} is not a readable run record: {exc}") from exc
