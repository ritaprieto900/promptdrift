"""Repo-integrity: every example suite must parse and fingerprint cleanly."""

from __future__ import annotations

from pathlib import Path

import pytest

from promptdrift.services.loader import load_suite

EXAMPLES = Path(__file__).parents[2] / "examples"

EXAMPLE_SUITES = sorted(EXAMPLES.glob("*/promptest.yaml"))


def test_examples_exist() -> None:
    assert len(EXAMPLE_SUITES) >= 2


@pytest.mark.parametrize("suite_path", EXAMPLE_SUITES, ids=lambda p: p.parent.name)
def test_example_suite_loads(suite_path: Path) -> None:
    suite = load_suite(suite_path)
    assert suite.fingerprint().startswith("sha256:")
    assert suite.cases
