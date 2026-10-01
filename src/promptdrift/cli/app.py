"""The promptdrift command line interface.

Deliberately thin: every capability lives in the library API, commands here
only load configs, orchestrate services, render output, and map outcomes to
documented exit codes (0 pass, 1 gate/assertion failure, 2 usage or runtime
error).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from promptdrift import __version__
from promptdrift.adapters import CachedProvider, SqliteCache, build_provider
from promptdrift.adapters.snapshot_store import (
    load_snapshot,
    save_snapshot,
    snapshot_from_run,
)
from promptdrift.cli.scaffold import STARTER_SUITE_YAML, demo_suite_yaml
from promptdrift.domain.results import Run
from promptdrift.domain.suite import Suite
from promptdrift.domain.verdict import FailOn, diff_run
from promptdrift.errors import PromptdriftError, SuiteLoadError
from promptdrift.ports import Provider
from promptdrift.services.cost import estimate
from promptdrift.services.differ import compare
from promptdrift.services.junit import junit_xml
from promptdrift.services.loader import load_suite, resolve_suite_path
from promptdrift.services.persistence import load_latest_run, save_run
from promptdrift.services.reporter import markdown_report, render_diff, render_run
from promptdrift.services.runner import Runner

app = typer.Typer(
    name="promptdrift",
    help="Flake-aware prompt regression testing and CI gating for LLM prompts.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)
console = Console()


@dataclass
class CliState:
    root: Path
    no_cache: bool
    verbose: bool


@contextmanager
def _errors_to_exit() -> Iterator[None]:
    """Map promptdrift errors to exit code 2 with a readable message."""
    try:
        yield
    except PromptdriftError as exc:
        console.print(Text(f"error: {exc}", style="bold red"))
        raise typer.Exit(2) from exc


def _state(ctx: typer.Context) -> CliState:
    state = ctx.obj
    assert isinstance(state, CliState)  # callback always populates it
    return state


@app.callback()
def _callback(
    ctx: typer.Context,
    root: Path | None = typer.Option(
        None, "--root", "-C", help="Project directory (defaults to the current directory)."
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Ignore the response cache for this invocation."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="More detail in output."),
) -> None:
    ctx.obj = CliState(root=(root or Path.cwd()).resolve(), no_cache=no_cache, verbose=verbose)


def _cache_db_path(root: Path) -> Path:
    return root / ".promptest" / "cache.db"


async def _execute_suite(root: Path, suite_obj: Suite, *, use_cache: bool) -> Run:
    provider = build_provider(suite_obj.provider)
    cache: SqliteCache | None = None
    effective: Provider = provider
    if use_cache and suite_obj.provider_id != "mock":
        cache = SqliteCache(_cache_db_path(root))
        effective = CachedProvider(provider, cache)
    try:
        return await Runner(effective).run(suite_obj)
    finally:
        await provider.aclose()
        if cache is not None:
            cache.close()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _markdown_for_run(run_obj: Run) -> str:
    """Markdown report for a baseline-less run (kept minimal on purpose)."""
    diff_obj = diff_run(run_obj, None)
    return markdown_report(run_obj, diff_obj, FailOn.REGRESSION)


_GITIGNORE_ENTRIES = [".promptest/cache.db*", ".promptest/runs/"]


def _ensure_gitignore(root: Path) -> None:
    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    missing = [line for line in _GITIGNORE_ENTRIES if line not in existing]
    if not missing:
        return
    block = "" if existing.endswith("\n") or not existing else "\n"
    if "# promptdrift" not in existing:
        block += "\n# promptdrift runtime artifacts (baselines stay committed)\n"
    block += "\n".join(missing) + "\n"
    gitignore.write_text(existing + block, encoding="utf-8")


@app.command()
def init(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Overwrite an existing promptest.yaml."),
) -> None:
    """Scaffold a starter suite that runs offline on the mock provider."""
    with _errors_to_exit():
        state = _state(ctx)
        target = state.root / "promptest.yaml"
        if target.exists() and not force:
            raise SuiteLoadError(f"{target} already exists; pass --force to overwrite")
        _write_text(target, STARTER_SUITE_YAML)
        _ensure_gitignore(state.root)
        console.print(f"[green]created[/green] {target}")
        console.print(
            Panel.fit(
                "1. [bold]promptdrift run[/bold]      execute the suite (offline, mock provider)\n"
                "2. [bold]promptdrift approve[/bold]  record this behavior as the baseline\n"
                "3. [bold]promptdrift diff[/bold]     gate future changes against it\n"
                "\nTo test a real model, switch `provider:` to `openai_compat:` and export "
                "its API key — see the comments in promptest.yaml.",
                title="next steps",
                border_style="green",
            )
        )


@app.command()
def run(
    ctx: typer.Context,
    suite: Path | None = typer.Option(None, "--suite", "-s", help="Suite YAML file."),
    json_out: Path | None = typer.Option(None, "--json", help="Write run JSON here."),
    junit_out: Path | None = typer.Option(None, "--junit", help="Write JUnit XML here."),
    md_out: Path | None = typer.Option(None, "--md", help="Write a markdown report here."),
    no_fail: bool = typer.Option(
        False, "--no-fail", help="Exit 0 even when assertions fail (gating is `diff`'s job)."
    ),
) -> None:
    """Run the suite once, no baseline comparison. Exit 1 if assertions fail."""
    with _errors_to_exit():
        state = _state(ctx)
        suite_obj = load_suite(resolve_suite_path(state.root, suite))
        run_obj = asyncio.run(_execute_suite(state.root, suite_obj, use_cache=not state.no_cache))
        save_run(state.root, run_obj)
        render_run(console, run_obj, suite_obj)
        if json_out is not None:
            _write_text(
                json_out, json.dumps(run_obj.model_dump(mode="json"), indent=2, ensure_ascii=False)
            )
            console.print(f"[dim]run JSON → {json_out}[/dim]")
        if junit_out is not None:
            _write_text(junit_out, junit_xml(run_obj))
            console.print(f"[dim]JUnit XML → {junit_out}[/dim]")
        if md_out is not None:
            _write_text(md_out, _markdown_for_run(run_obj))
            console.print(f"[dim]markdown → {md_out}[/dim]")
        failed = any(
            not outcome.passed
            for case in run_obj.cases
            for sample in case.samples
            for outcome in sample.outcomes
        )
        if failed and not no_fail:
            raise typer.Exit(1)


@app.command()
def diff(
    ctx: typer.Context,
    suite: Path | None = typer.Option(None, "--suite", "-s", help="Suite YAML file."),
    fail_on: FailOn = typer.Option(
        FailOn.REGRESSION,
        "--fail-on",
        help="What counts as a gate failure: regression | flaky | any-fail.",
    ),
    require_baseline: bool = typer.Option(
        False, "--require-baseline", help="Exit 2 when no baseline exists (recommended in CI)."
    ),
    md_out: Path | None = typer.Option(None, "--md", help="Write the markdown report here."),
    full: bool = typer.Option(False, "--full", help="Show every assertion, not just changes."),
) -> None:
    """Run and compare against the baseline. Exit 1 when the gate fails."""
    with _errors_to_exit():
        state = _state(ctx)
        suite_obj = load_suite(resolve_suite_path(state.root, suite))
        snapshot = load_snapshot(state.root, suite_obj.suite)
        if snapshot is None and require_baseline:
            raise SuiteLoadError(
                f"no baseline for suite {suite_obj.suite!r} at "
                f"{state.root / '.promptest' / 'baselines'} — run `promptdrift approve` "
                "locally and commit the snapshot, or drop --require-baseline."
            )
        run_obj = asyncio.run(_execute_suite(state.root, suite_obj, use_cache=not state.no_cache))
        diff_obj = compare(run_obj, snapshot)
        save_run(state.root, run_obj)
        render_diff(console, run_obj, diff_obj, fail_on, full=full)
        if md_out is not None:
            _write_text(md_out, markdown_report(run_obj, diff_obj, fail_on, full=full))
            console.print(f"[dim]markdown → {md_out}[/dim]")
        if snapshot is None:
            return
        passed, _reason = diff_obj.gate(fail_on)
        if not passed:
            raise typer.Exit(1)


@app.command()
def approve(
    ctx: typer.Context,
    suite: Path | None = typer.Option(None, "--suite", "-s", help="Suite YAML file."),
) -> None:
    """Run fresh and record the result as the suite's baseline.

    Commit the snapshot file (`.promptest/baselines/*.snap.yaml`) to git —
    a PR that touches it is a reviewed behavior change.
    """
    with _errors_to_exit():
        state = _state(ctx)
        suite_obj = load_suite(resolve_suite_path(state.root, suite))
        run_obj = asyncio.run(_execute_suite(state.root, suite_obj, use_cache=not state.no_cache))
        snapshot = snapshot_from_run(run_obj, suite_obj)
        previous = load_snapshot(state.root, suite_obj.suite)
        if previous is not None:
            console.print(
                f"[dim]replacing baseline recorded {previous.recorded_at.isoformat()} "
                f"({len(previous.cases)} cases)[/dim]"
            )
        path = save_snapshot(state.root, snapshot)
        console.print(f"[green]baseline recorded[/green] → {path}")
        console.print(
            f"{len(snapshot.cases)} cases · fingerprint {snapshot.config_fingerprint[:19]}… · "
            "commit this file so CI can gate against it"
        )


@app.command()
def show(
    ctx: typer.Context,
    suite: Path | None = typer.Option(None, "--suite", "-s", help="Suite YAML file."),
    snapshot_flag: bool = typer.Option(False, "--snapshot", help="Show the baseline snapshot."),
) -> None:
    """Show the latest run (default) or the baseline snapshot."""
    with _errors_to_exit():
        state = _state(ctx)
        suite_obj = load_suite(resolve_suite_path(state.root, suite))
        if snapshot_flag:
            path = state.root / ".promptest" / "baselines" / f"{suite_obj.suite}.snap.yaml"
            if not path.exists():
                console.print("[yellow]no baseline recorded yet[/yellow]")
                return
            console.print(Syntax(path.read_text(encoding="utf-8"), "yaml", word_wrap=True))
            return
        run_obj = load_latest_run(state.root, suite_obj.suite)
        if run_obj is None:
            console.print(
                f"[yellow]no run recorded for {suite_obj.suite!r} yet — "
                "run `promptdrift run`[/yellow]"
            )
            return
        render_run(console, run_obj, suite_obj)


@app.command()
def cost(
    ctx: typer.Context,
    suite: Path | None = typer.Option(None, "--suite", "-s", help="Suite YAML file."),
) -> None:
    """Estimate provider calls (and cost when prices are configured)."""
    with _errors_to_exit():
        state = _state(ctx)
        suite_obj = load_suite(resolve_suite_path(state.root, suite))
        result = estimate(suite_obj)
        console.print(f"[bold]{suite_obj.suite}[/bold]: {result.calls} provider call(s)")
        if result.est_prompt_tokens is not None and result.prompt_per_1m is not None:
            prompt_cost = result.est_prompt_cost_usd or 0.0
            cap = (
                f"completion capped at {result.max_tokens_cap} tokens"
                if result.max_tokens_cap
                else "completion length unknown until the run"
            )
            console.print(
                f"≈{result.est_prompt_tokens} prompt tokens ≈ ${prompt_cost:.4f} "
                "(lower bound — completion cost not included; " + cap + ")"
            )
            assert result.completion_per_1m is not None
            console.print(
                f"prices: ${result.prompt_per_1m}/1M prompt, "
                f"${result.completion_per_1m}/1M completion"
            )
        else:
            console.print(
                "[dim]add `pricing: {prompt_per_1m: ..., completion_per_1m: ...}` to an "
                "openai_compat provider for token/cost estimates[/dim]"
            )


@app.command("schema")
def schema_cmd() -> None:
    """Print the JSON Schema for suite files (for editor completion)."""
    from promptdrift.domain.suite import Suite

    console.print_json(json.dumps(Suite.model_json_schema(), ensure_ascii=False))


@app.command()
def version() -> None:
    """Print the promptdrift version."""
    console.print(f"promptdrift {__version__}")


@app.command()
def demo(
    ctx: typer.Context,
    target: Path = typer.Option(
        Path("promptdrift-demo"), "--dir", help="Directory for the generated demo files."
    ),
) -> None:
    """Full offline walkthrough: run → approve → regress → diff. No API key."""
    with _errors_to_exit():
        state = _state(ctx)
        demo_root = target if target.is_absolute() else state.root / target
        demo_root.mkdir(parents=True, exist_ok=True)
        suite_path = demo_root / "promptest.yaml"

        console.rule("[bold]promptdrift demo — everything below runs offline")
        suite_path.write_text(demo_suite_yaml(regressed=False), encoding="utf-8")
        console.print(f"demo suite written to {suite_path}\n")

        console.rule("step 1/4 — run the suite fresh")
        suite_obj = load_suite(suite_path)
        first_run = asyncio.run(_execute_suite(demo_root, suite_obj, use_cache=False))
        save_run(demo_root, first_run)
        render_run(console, first_run, suite_obj)

        console.rule("step 2/4 — approve: record this behavior as the baseline")
        baseline = save_snapshot(demo_root, snapshot_from_run(first_run, suite_obj))
        console.print(f"baseline recorded → {baseline}\n")

        console.rule("step 3/4 — someone 'improves' the prompt")
        suite_path.write_text(demo_suite_yaml(regressed=True), encoding="utf-8")
        console.print(
            "the refund answer was rewritten and lost its structured steps — "
            "the suite file changed, the baseline did not\n"
        )

        console.rule("step 4/4 — diff: catch the drift")
        regressed_suite = load_suite(suite_path)
        second_run = asyncio.run(_execute_suite(demo_root, regressed_suite, use_cache=False))
        save_run(demo_root, second_run)
        snapshot = load_snapshot(demo_root, regressed_suite.suite)
        assert snapshot is not None
        diff_obj = compare(second_run, snapshot)
        render_diff(console, second_run, diff_obj, FailOn.REGRESSION)
        gate_passed, _ = diff_obj.gate(FailOn.REGRESSION)
        exit_code = 0 if gate_passed else 1
        console.print(
            f"\n[bold red]in CI, `promptdrift diff` just exited {exit_code}[/bold red] — the "
            "merge would be blocked until the prompt change is reviewed and the baseline is "
            "re-approved."
        )
        console.print(
            Panel.fit(
                f"demo files: {demo_root}\n"
                "  promptest.yaml          the suite (now in its regressed state)\n"
                "  .promptest/baselines/   the baseline — commit this in real projects\n\n"
                "next: [bold]promptdrift init[/bold] in your own project, point `provider:` "
                "at a real model, and replace the mock rules with your prompts.\n"
                "cleanup: delete the demo directory whenever you like.",
                title="what just happened",
                border_style="cyan",
            )
        )


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
