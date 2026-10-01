"""Rendering: rich terminal output and PR-ready markdown reports.

Rendering is a pure function of (run, diff, fail_on, full). The markdown
report's exact shape is pinned by golden-file tests — changing the format
here means regenerating those goldens.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from rich.console import Console
from rich.table import Table
from rich.text import Text

from promptdrift.domain.results import Run
from promptdrift.domain.suite import Suite
from promptdrift.domain.verdict import FailOn, SuiteDiff, Verdict

_OUTPUT_PREVIEW_CHARS = 400

_VERDICT_STYLE = {
    Verdict.REGRESSED: "bold red",
    Verdict.IMPROVED: "bold green",
    Verdict.UNSTABLE: "bold yellow",
    Verdict.NEW: "bold cyan",
    Verdict.REMOVED: "dim",
    Verdict.STABLE: "green",
}

_COUNT_ORDER = (
    Verdict.REGRESSED,
    Verdict.UNSTABLE,
    Verdict.IMPROVED,
    Verdict.NEW,
    Verdict.REMOVED,
    Verdict.STABLE,
)


def package_version() -> str:
    try:
        return version("promptdrift")
    except PackageNotFoundError:  # pragma: no cover - only for un-installed trees
        return "0.0.0+unknown"


def _counts_line(diff: SuiteDiff) -> str:
    parts = [f"{diff.count(v)} {v.value}" for v in _COUNT_ORDER if diff.count(v)]
    return " · ".join(parts) if parts else "no cases"


def _score_line(diff: SuiteDiff) -> str:
    if diff.score_before is None:
        return f"score {diff.score_after:.0%}"
    return f"score {diff.score_before:.0%} → {diff.score_after:.0%}"


def render_run(console: Console, run: Run, suite: Suite) -> None:
    """Terminal report for a plain ``run`` (no baseline comparison)."""
    table = Table(
        title=f"suite {suite.suite!r} · provider {suite.provider_id} · model {run.model}",
        title_justify="left",
    )
    table.add_column("case")
    table.add_column("assertion")
    table.add_column("rate", justify="right")
    for case_result in run.cases:
        rates = case_result.rates()
        if not rates:
            table.add_row(
                case_result.case_id, Text("— no assertions —", style="dim"), Text("", style="dim")
            )
            continue
        for index, (assertion_id, (passed, total)) in enumerate(sorted(rates.items())):
            rate_text = Text(f"{passed}/{total}")
            rate_text.stylize("green" if passed == total else "red" if passed == 0 else "yellow")
            table.add_row(
                case_result.case_id if index == 0 else "",
                assertion_id,
                rate_text,
            )
    console.print(table)
    console.print(Text(_run_footer(run), style="dim"))


def _run_footer(run: Run) -> str:
    usage = run.total_usage()
    total_samples = sum(len(case.samples) for case in run.cases)
    cached = sum(1 for case in run.cases for sample in case.samples if sample.cached)
    cached_note = f" · {cached} cached" if cached else ""
    return (
        f"{len(run.cases)} cases · {total_samples} samples · "
        f"{usage.prompt_tokens} prompt / {usage.completion_tokens} completion tokens · "
        f"{run.duration_ms:.0f} ms{cached_note}"
    )


def render_diff(
    console: Console, run: Run, diff: SuiteDiff, fail_on: FailOn, *, full: bool = False
) -> None:
    """Terminal report for ``diff`` (run compared against the baseline)."""
    summary = Text.assemble(
        (f"promptdrift {diff.suite}", "bold"),
        ("  ·  ", "dim"),
        (_counts_line(diff), "dim"),
        ("  ·  ", "dim"),
        (_score_line(diff), "dim"),
    )
    console.print(summary)

    table = Table(title=f"model {run.model}", title_justify="left")
    table.add_column("case")
    table.add_column("assertion")
    table.add_column("before", justify="right")
    table.add_column("after", justify="right")
    table.add_column("verdict")
    table.add_column("note")
    for case in diff.cases:
        if case.is_removed:
            table.add_row(
                case.case_id,
                Text("(removed from suite)", style="dim"),
                "",
                "",
                Text(f"{Verdict.REMOVED.icon} removed", style=_VERDICT_STYLE[Verdict.REMOVED]),
                "",
            )
            continue
        if not case.assertions:
            table.add_row(
                case.case_id,
                Text("— no assertions —", style="dim"),
                "",
                "",
                Text(f"{Verdict.STABLE.icon} stable", style=_VERDICT_STYLE[Verdict.STABLE]),
                "",
            )
            continue
        for index, assertion in enumerate(case.assertions):
            before = f"{assertion.base.passed}/{assertion.base.total}" if assertion.base else "—"
            note = "" if assertion.verdict is Verdict.STABLE else assertion.detail
            if not full and assertion.verdict is Verdict.STABLE and len(case.assertions) > 1:
                continue  # compact view: hide stable assertions of mixed cases
            table.add_row(
                case.case_id if index == 0 else "",
                assertion.assertion_id,
                before,
                f"{assertion.new.passed}/{assertion.new.total}",
                Text(
                    f"{assertion.verdict.icon} {assertion.verdict.value}",
                    style=_VERDICT_STYLE[assertion.verdict],
                ),
                Text(note, style="dim"),
            )
    console.print(table)

    gate_passed, gate_reason = diff.gate(fail_on)
    if not diff.has_baseline:
        console.print(
            Text(
                "no baseline yet — run `promptdrift approve` to record one; "
                "gating activates after that",
                style="yellow",
            )
        )
        return
    style = "bold green" if gate_passed else "bold red"
    mark = "✅" if gate_passed else "❌"
    console.print(
        Text(f"{mark} gate {'passed' if gate_passed else 'FAILED'} — {gate_reason}", style=style)
    )


def _md_escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _preview(text: str) -> str:
    flat = text.strip()
    if len(flat) > _OUTPUT_PREVIEW_CHARS:
        flat = flat[:_OUTPUT_PREVIEW_CHARS] + "…"
    return flat


def markdown_report(run: Run, diff: SuiteDiff, fail_on: FailOn, *, full: bool = False) -> str:
    """PR-comment-ready markdown report."""
    gate_passed, gate_reason = diff.gate(fail_on)
    lines: list[str] = []
    lines.append(f"### promptdrift — `{diff.suite}`")
    lines.append("")
    lines.append(
        f"**Gate: {'✅ PASSED' if gate_passed else '❌ FAILED'}** "
        f"(fail-on: `{fail_on.value}`) — {gate_reason}"
    )
    lines.append("")
    lines.append(f"{_counts_line(diff)} · {_score_line(diff)} · model `{run.model or 'n/a'}`")
    lines.append("")
    lines.append("| Case | Assertion | Before | After | Verdict | Note |")
    lines.append("|---|---|---|---|---|---|")
    shown_cases = diff.cases if full else diff.changed_cases or []
    for case in shown_cases:
        if case.is_removed:
            lines.append(
                f"| {case.case_id} | *(removed from suite)* | — | — | "
                f"{Verdict.REMOVED.icon} removed | |"
            )
            continue
        if not case.assertions:
            lines.append(f"| {case.case_id} | *(no assertions)* | — | — | ✅ stable | |")
            continue
        for assertion in case.assertions:
            if not full and assertion.verdict is Verdict.STABLE and len(case.assertions) > 1:
                continue
            before = f"{assertion.base.passed}/{assertion.base.total}" if assertion.base else "—"
            lines.append(
                f"| {case.case_id} | `{_md_escape_cell(assertion.assertion_id)}` "
                f"| {before} | {assertion.new.passed}/{assertion.new.total} "
                f"| {assertion.verdict.icon} {assertion.verdict.value} "
                f"| {_md_escape_cell(assertion.detail or '')} |"
            )
    if not shown_cases:
        lines.append(
            "*No behavioral changes detected.*" if diff.has_baseline else "*Run recorded.*"
        )

    changed_with_outputs = [case for case in diff.cases if case.changed and not case.is_removed]
    if changed_with_outputs:
        lines.append("")
        lines.append("<details><summary>Representative outputs (changed cases)</summary>")
        lines.append("")
        for case in changed_with_outputs:
            lines.append(f"**{case.case_id}**")
            lines.append("")
            if case.representative_before:
                lines.append("Before:")
                lines.append("")
                lines.append(f"```\n{_preview(case.representative_before)}\n```")
                lines.append("")
            lines.append("After:")
            lines.append("")
            lines.append(f"```\n{_preview(case.representative_after)}\n```")
            lines.append("")
        lines.append("</details>")

    lines.append("")
    lines.append(
        f"<sub>Generated by [promptdrift](https://github.com/promptdrift/promptdrift) "
        f"v{package_version()} · flake-aware prompt regression gating · "
        f"{_score_line(diff)}</sub>"
    )
    return "\n".join(lines) + "\n"
