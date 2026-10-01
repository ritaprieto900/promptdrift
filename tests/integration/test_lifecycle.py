"""End-to-end lifecycle: run → approve → diff → regress → re-approve.

Everything runs on the mock provider — the full product loop without a
network, which is also the guarantee our own CI depends on.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from promptdrift.adapters import build_provider
from promptdrift.adapters.snapshot_store import load_snapshot, save_snapshot, snapshot_from_run
from promptdrift.domain.verdict import FailOn, Verdict
from promptdrift.errors import StaleBaselineError
from promptdrift.services.differ import compare
from promptdrift.services.loader import load_suite
from promptdrift.services.persistence import load_latest_run, save_run
from promptdrift.services.runner import Runner
from tests.conftest import MOCK_SUITE_YAML

GOOD_REFUND = "您好，请打开订单页点击申请退款，3-5 个工作日到账。"
BAD_REFUND = "好的。"


def write_suite(root: Path, *, refund_text: str = GOOD_REFUND, samples: int = 3) -> Path:
    text = MOCK_SUITE_YAML.replace(GOOD_REFUND, refund_text).replace(
        "samples: 3", f"samples: {samples}"
    )
    path = root / "promptest.yaml"
    path.write_text(text, encoding="utf-8")
    return path


async def _run(root: Path):
    suite = load_suite(root / "promptest.yaml")
    provider = build_provider(suite.provider)
    try:
        return suite, await Runner(provider).run(suite)
    finally:
        await provider.aclose()


async def test_full_lifecycle(tmp_path: Path) -> None:
    root = tmp_path
    write_suite(root)

    # 1. first run — no baseline yet
    suite, run1 = await _run(root)
    assert suite.fingerprint().startswith("sha256:")
    snapshot = snapshot_from_run(run1, suite)
    save_snapshot(root, snapshot)

    # 2. identical re-run — everything stable, gate passes
    _suite2, run2 = await _run(root)
    diff2 = compare(run2, load_snapshot(root, suite.suite))
    assert diff2.verdict is Verdict.STABLE
    assert diff2.gate(FailOn.REGRESSION) == (True, "gate passed")
    assert diff2.score_before == pytest.approx(1.0)
    assert diff2.score_after == pytest.approx(1.0)

    # 3. prompt regression — mock answer loses its substance.
    # Fingerprint is unchanged (mock text is behavior, measured by the diff).
    write_suite(root, refund_text=BAD_REFUND)
    suite3, run3 = await _run(root)
    assert suite3.fingerprint() == suite.fingerprint()
    diff3 = compare(run3, load_snapshot(root, suite.suite))
    assert diff3.gate(FailOn.REGRESSION)[0] is False
    by_id = {case.case_id: case for case in diff3.cases}
    assert by_id["refund"].verdict is Verdict.REGRESSED
    assert by_id["invoice"].verdict is Verdict.STABLE
    assert diff3.verdict is Verdict.REGRESSED

    # 4. re-approve the regressed state, gate clears
    save_snapshot(root, snapshot_from_run(run3, suite3))
    _suite4, run4 = await _run(root)
    diff4 = compare(run4, load_snapshot(root, suite3.suite))
    assert diff4.gate(FailOn.REGRESSION)[0] is True

    # 5. changing sample count stales the baseline instead of comparing
    write_suite(root, refund_text=BAD_REFUND, samples=5)
    _suite5, run5 = await _run(root)
    with pytest.raises(StaleBaselineError):
        compare(run5, load_snapshot(root, suite3.suite))


async def test_persistence_roundtrip(tmp_path: Path) -> None:
    root = tmp_path
    write_suite(root)
    suite, run = await _run(root)
    save_run(root, run)
    loaded = load_latest_run(root, suite.suite)
    assert loaded is not None
    assert loaded.suite == run.suite
    assert loaded.cases[0].rates() == run.cases[0].rates()
    assert load_latest_run(root, "no-such-suite") is None


async def test_template_vars_render_per_case(tmp_path: Path) -> None:
    """vars flow through to the provider; assertions see the rendered output."""
    raw = yaml.safe_load(
        """
suite: var-suite
provider:
  mock:
    rules:
      - contains: "VIP"
        text: "尊贵的 VIP 用户您好"
    default: "您好"
samples: 1
cases:
  - id: vip
    messages:
      - role: user
        content: "我是{{level}}用户"
    vars:
      level: VIP
    assertions:
      - contains: "尊贵的 VIP"
"""
    )
    raw_suite_path = tmp_path / "promptest.yaml"
    raw_suite_path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    suite = load_suite(raw_suite_path)
    provider = build_provider(suite.provider)
    try:
        run = await Runner(provider).run(suite)
    finally:
        await provider.aclose()
    case = run.case("vip")
    assert case is not None
    assert case.samples[0].output == "尊贵的 VIP 用户您好"
    assert all(outcome.passed for outcome in case.samples[0].outcomes)
