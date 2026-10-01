"""Golden-file tests pinning the report formats (markdown + terminal).

Regenerate after an intentional format change:

    PROMPTDRIFT_REGEN_GOLDEN=1 uv run pytest tests/golden -q
"""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console

from promptdrift.domain.verdict import FailOn, Verdict, diff_run
from promptdrift.services.reporter import markdown_report, render_diff
from tests.conftest import make_case_result, make_run, make_snapshot

GOLDEN_DIR = Path(__file__).parent / "files"

# A fixed scenario exercising every verdict:
#   faq      → new case
#   greeting → regressed (pure flip 3/3 → 0/3)
#   legacy   → removed from the suite
#   refund   → unstable (3/3 → 1/3)
#   tone     → stable (2/3 → 3/3 is within noise)
RUN = make_run(
    [
        make_case_result("faq", {"contains-welcome": (3, 3)}, output="欢迎回来！有什么可以帮你？"),
        make_case_result("greeting", {"contains-hello": (0, 3)}, output="42"),
        make_case_result("refund", {"contains-申请退款": (1, 3)}, output="可能是退款吧。"),
        make_case_result("tone", {"regex-polite": (3, 3)}, output="请您稍等，马上为您处理。"),
    ]
)
SNAPSHOT = make_snapshot(
    [
        ("refund", {"contains-申请退款": (3, 3)}, "您好，请打开订单页点击申请退款。"),
        ("greeting", {"contains-hello": (3, 3)}, "hello!"),
        ("legacy", {"contains-old": (3, 3)}, "legacy behavior"),
        ("tone", {"regex-polite": (2, 3)}, "好的。"),
    ]
)
DIFF = diff_run(RUN, SNAPSHOT)


def _assert_golden(name: str, content: str) -> None:
    path = GOLDEN_DIR / name
    if os.environ.get("PROMPTDRIFT_REGEN_GOLDEN"):
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return
    assert path.exists(), f"golden missing: {path} (regenerate with PROMPTDRIFT_REGEN_GOLDEN=1)"
    assert content == path.read_text(encoding="utf-8")


def test_scenario_produces_expected_verdicts() -> None:
    """Sanity: the fixed scenario really covers all six verdicts."""
    by_id = {case.case_id: case.verdict for case in DIFF.cases}
    assert by_id == {
        "faq": Verdict.NEW,
        "greeting": Verdict.REGRESSED,
        "legacy": Verdict.REMOVED,
        "refund": Verdict.UNSTABLE,
        "tone": Verdict.STABLE,
    }
    assert DIFF.verdict is Verdict.REGRESSED


def test_markdown_report_golden() -> None:
    _assert_golden("markdown_report.md", markdown_report(RUN, DIFF, FailOn.REGRESSION))


def test_markdown_report_full_golden() -> None:
    _assert_golden(
        "markdown_report_full.md",
        markdown_report(RUN, DIFF, FailOn.REGRESSION, full=True),
    )


def test_terminal_report_golden() -> None:
    console = Console(record=True, width=110, no_color=True, highlight=False, legacy_windows=False)
    render_diff(console, RUN, DIFF, FailOn.REGRESSION)
    _assert_golden("terminal_report.txt", console.export_text() + "\n")
