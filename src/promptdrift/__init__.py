"""promptdrift — flake-aware prompt regression testing and CI gating.

Library use mirrors the CLI::

    import asyncio
    from pathlib import Path

    from promptdrift import Runner, build_provider, compare, load_suite, load_snapshot

    suite = load_suite(Path("promptest.yaml"))
    provider = build_provider(suite.provider)
    run = asyncio.run(Runner(provider).run(suite))
    snapshot = load_snapshot(Path("."), suite.suite)
    diff = compare(run, snapshot)
    passed, reason = diff.gate(FailOn.REGRESSION)
"""

from promptdrift.adapters import CachedProvider, SqliteCache, build_provider
from promptdrift.adapters.snapshot_store import (
    load_snapshot,
    save_snapshot,
    snapshot_from_run,
)
from promptdrift.domain.assertions import ASSERTION_TYPES, BaseAssertion, Judge
from promptdrift.domain.results import AssertionOutcome, CaseResult, Run, SampleResult
from promptdrift.domain.snapshot import (
    Snapshot,
    SnapshotCase,
    SnapshotRate,
    wilson_interval,
)
from promptdrift.domain.suite import Case, Message, MockConfig, MockRule, OpenAICompatConfig, Suite
from promptdrift.domain.verdict import (
    AssertionDiff,
    CaseDiff,
    FailOn,
    SuiteDiff,
    Verdict,
    classify_assertion,
    diff_run,
)
from promptdrift.errors import (
    PromptdriftError,
    ProviderError,
    SnapshotLoadError,
    StaleBaselineError,
    SuiteLoadError,
)
from promptdrift.ports import Cache, CompletionRequest, CompletionResponse, Provider
from promptdrift.services.differ import compare, ensure_comparable
from promptdrift.services.loader import load_suite, resolve_suite_path, suite_from_dict
from promptdrift.services.runner import Runner

__version__ = "0.1.0"

__all__ = [
    "ASSERTION_TYPES",
    "AssertionDiff",
    "AssertionOutcome",
    "BaseAssertion",
    "Cache",
    "CachedProvider",
    "Case",
    "CaseDiff",
    "CaseResult",
    "CompletionRequest",
    "CompletionResponse",
    "FailOn",
    "Judge",
    "Message",
    "MockConfig",
    "MockRule",
    "OpenAICompatConfig",
    "PromptdriftError",
    "Provider",
    "ProviderError",
    "Run",
    "Runner",
    "SampleResult",
    "Snapshot",
    "SnapshotCase",
    "SnapshotLoadError",
    "SnapshotRate",
    "SqliteCache",
    "StaleBaselineError",
    "Suite",
    "SuiteDiff",
    "SuiteLoadError",
    "Verdict",
    "__version__",
    "build_provider",
    "classify_assertion",
    "compare",
    "diff_run",
    "ensure_comparable",
    "load_snapshot",
    "load_suite",
    "resolve_suite_path",
    "save_snapshot",
    "snapshot_from_run",
    "suite_from_dict",
    "wilson_interval",
]
