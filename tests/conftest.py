"""Shared fixtures and model factories for the promptdrift test suite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
import yaml

from promptdrift.domain.results import (
    AssertionOutcome,
    CaseResult,
    Run,
    SampleResult,
    TokenUsage,
)
from promptdrift.domain.snapshot import Snapshot, SnapshotCase, SnapshotRate
from promptdrift.domain.suite import Suite
from promptdrift.services.loader import suite_from_dict

MOCK_SUITE_YAML = """\
suite: it-suite
provider:
  mock:
    rules:
      - contains: "退款"
        text: "您好，请打开订单页点击申请退款，3-5 个工作日到账。"
      - contains: "发票"
        text: '{"order_id": "A1024", "invoice_status": "issued"}'
    default: "您好，请问有什么可以帮您？"
samples: 3
cases:
  - id: refund
    messages:
      - role: user
        content: "我想申请{{topic}}"
    vars:
      topic: 退款
    assertions:
      - contains: "申请退款"
      - contains: "3-5 个工作日"
  - id: invoice
    messages:
      - role: user
        content: "查发票"
    assertions:
      - is_json: true
"""

TEST_FINGERPRINT = "sha256:test-fingerprint"


def suite_from_yaml_text(text: str) -> Suite:
    raw: Any = yaml.safe_load(text)
    return suite_from_dict(raw, source="<test>")


@pytest.fixture
def mock_suite() -> Suite:
    return suite_from_yaml_text(MOCK_SUITE_YAML)


def make_case_result(
    case_id: str,
    rates: dict[str, tuple[int, int]],
    output: str = "representative output",
    model: str | None = "mock",
) -> CaseResult:
    """Build a CaseResult whose per-sample outcomes reproduce *rates*.

    All assertions in one case share the sample count (as in real runs).
    """
    if not rates:
        return CaseResult(
            case_id=case_id,
            model=model,
            samples=[
                SampleResult(
                    output=output,
                    usage=TokenUsage(prompt_tokens=3, completion_tokens=2),
                    latency_ms=11.0,
                )
            ],
        )
    totals = {total for _, total in rates.values()}
    assert len(totals) == 1, "factory requires equal totals across assertions"
    n = totals.pop()
    samples = [
        SampleResult(
            output=output,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
            latency_ms=100.0,
            outcomes=[
                AssertionOutcome(
                    assertion_id=aid,
                    assertion_type=aid.split("-", 1)[0],
                    passed=index < passed,
                )
                for aid, (passed, _) in rates.items()
            ],
        )
        for index in range(n)
    ]
    return CaseResult(case_id=case_id, model=model, samples=samples)


def make_run(cases: list[CaseResult], suite: str = "it-suite") -> Run:
    return Run(
        suite=suite,
        model="mock",
        config_fingerprint=TEST_FINGERPRINT,
        started_at=datetime.now(timezone.utc),
        duration_ms=42.0,
        cases=cases,
    )


def make_snapshot_cases(
    entries: list[tuple[str, dict[str, tuple[int, int]], str]],
) -> list[SnapshotCase]:
    return [
        SnapshotCase(
            id=case_id,
            samples=next(iter(rates.values()))[1] if rates else 1,
            mean_latency_ms=90.0,
            mean_prompt_tokens=10.0,
            mean_completion_tokens=5.0,
            representative_output=output,
            assertions={aid: SnapshotRate.from_pair(pair) for aid, pair in rates.items()},
        )
        for case_id, rates, output in entries
    ]


def make_snapshot(
    entries: list[tuple[str, dict[str, tuple[int, int]], str]], suite: str = "it-suite"
) -> Snapshot:
    return Snapshot(
        suite=suite,
        model="mock",
        config_fingerprint=TEST_FINGERPRINT,
        recorded_at=datetime.now(timezone.utc),
        cases=make_snapshot_cases(entries),
    )


@pytest.fixture
def case_result_factory():
    return make_case_result


@pytest.fixture
def run_factory():
    return make_run


@pytest.fixture
def snapshot_factory():
    return make_snapshot
