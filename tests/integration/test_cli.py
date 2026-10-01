"""CLI integration tests via typer's CliRunner — all offline (mock provider)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from promptdrift.cli.app import app
from tests.conftest import MOCK_SUITE_YAML

GOOD_REFUND = "您好，请打开订单页点击申请退款，3-5 个工作日到账。"

runner = CliRunner()


def write_gate_suite(root: Path, *, refund_text: str = GOOD_REFUND) -> Path:
    path = root / "promptest.yaml"
    path.write_text(MOCK_SUITE_YAML.replace(GOOD_REFUND, refund_text), encoding="utf-8")
    return path


def invoke(root: Path, *args: str) -> Result:
    return runner.invoke(app, ["--root", str(root), *args])


def test_init_scaffolds_and_gitignores(tmp_path: Path) -> None:
    result = invoke(tmp_path, "init")
    assert result.exit_code == 0, result.output
    suite_path = tmp_path / "promptest.yaml"
    assert suite_path.exists()
    assert "$schema:" in suite_path.read_text(encoding="utf-8")
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".promptest/cache.db*" in gitignore
    # idempotent-ish: second run without --force refuses
    conflict = invoke(tmp_path, "init")
    assert conflict.exit_code == 2
    forced = invoke(tmp_path, "init", "--force")
    assert forced.exit_code == 0


def test_run_starter_suite_offline(tmp_path: Path) -> None:
    invoke(tmp_path, "init")
    result = invoke(tmp_path, "run")
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".promptest" / "runs" / "latest-starter.json").exists()


def test_run_failing_assertion_exits_1(tmp_path: Path) -> None:
    write_gate_suite(tmp_path, refund_text="回答完全不对")
    result = invoke(tmp_path, "run")
    assert result.exit_code == 1
    relaxed = invoke(tmp_path, "run", "--no-fail")
    assert relaxed.exit_code == 0


def test_full_gate_cycle(tmp_path: Path) -> None:
    write_gate_suite(tmp_path)

    approved = invoke(tmp_path, "approve")
    assert approved.exit_code == 0, approved.output
    baseline = tmp_path / ".promptest" / "baselines" / "it-suite.snap.yaml"
    assert baseline.exists()

    first_diff = invoke(tmp_path, "diff")
    assert first_diff.exit_code == 0, first_diff.output
    assert "no baseline" not in first_diff.output

    regressed = invoke(tmp_path, "diff", "--md", str(tmp_path / "report.md"))
    assert regressed.exit_code == 0, regressed.output

    write_gate_suite(tmp_path, refund_text="回答完全不对")
    after_regression = invoke(tmp_path, "diff")
    assert after_regression.exit_code == 1, after_regression.output
    assert "🔴" in after_regression.output
    assert "gate FAILED" in after_regression.output

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Gate: ✅ PASSED" in report  # md was written during the passing diff

    reapproved = invoke(tmp_path, "approve")
    assert reapproved.exit_code == 0
    assert invoke(tmp_path, "diff").exit_code == 0


def test_diff_without_baseline_hints_approve(tmp_path: Path) -> None:
    write_gate_suite(tmp_path)
    result = invoke(tmp_path, "diff")
    assert result.exit_code == 0, result.output
    assert "approve" in result.output


def test_diff_require_baseline_exits_2(tmp_path: Path) -> None:
    write_gate_suite(tmp_path)
    result = invoke(tmp_path, "diff", "--require-baseline")
    assert result.exit_code == 2
    assert "no baseline" in result.output


def test_stale_baseline_exits_2(tmp_path: Path) -> None:
    write_gate_suite(tmp_path)
    assert invoke(tmp_path, "approve").exit_code == 0
    # changing sample count changes the fingerprint
    text = (tmp_path / "promptest.yaml").read_text(encoding="utf-8")
    (tmp_path / "promptest.yaml").write_text(
        text.replace("samples: 3", "samples: 5"), encoding="utf-8"
    )
    result = invoke(tmp_path, "diff")
    assert result.exit_code == 2
    assert "different configuration" in result.output


def test_show_latest_run_and_snapshot(tmp_path: Path) -> None:
    write_gate_suite(tmp_path)
    nothing = invoke(tmp_path, "show")
    assert nothing.exit_code == 0
    assert "no run recorded" in nothing.output

    invoke(tmp_path, "approve")
    snapshot_view = invoke(tmp_path, "show", "--snapshot")
    assert snapshot_view.exit_code == 0
    assert "config_fingerprint" in snapshot_view.output

    invoke(tmp_path, "run")
    run_view = invoke(tmp_path, "show")
    assert run_view.exit_code == 0
    assert "it-suite" in run_view.output


def test_cost_mock_reports_calls(tmp_path: Path) -> None:
    write_gate_suite(tmp_path)
    result = invoke(tmp_path, "cost")
    assert result.exit_code == 0, result.output
    assert "6 provider call(s)" in result.output  # 2 cases × 3 samples
    assert "pricing" in result.output  # mock has no prices → hint shown


def test_demo_end_to_end_offline(tmp_path: Path) -> None:
    result = invoke(tmp_path, "demo")
    assert result.exit_code == 0, result.output
    demo_dir = tmp_path / "promptdrift-demo"
    assert (demo_dir / "promptest.yaml").exists()
    assert (demo_dir / ".promptest" / "baselines" / "demo-support-agent.snap.yaml").exists()
    assert "step 4/4" in result.output
    assert "🔴" in result.output
    assert "exited 1" in result.output
    # demo reruns cleanly from scratch
    again = invoke(tmp_path, "demo")
    assert again.exit_code == 0, again.output


def test_schema_command_outputs_schema() -> None:
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0, result.output
    assert '"properties"' in result.output
    assert '"openai_compat"' in result.output


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip().startswith("promptdrift ")


@pytest.mark.parametrize(
    ("command", "expected_fragment"),
    [
        ("run", "no suite file found"),
        ("approve", "no suite file found"),
        ("cost", "no suite file found"),
    ],
)
def test_missing_suite_file_is_exit_2(tmp_path: Path, command: str, expected_fragment: str) -> None:
    result = invoke(tmp_path, command)
    assert result.exit_code == 2
    assert expected_fragment in result.output
