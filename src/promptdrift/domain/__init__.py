"""Pure domain layer: no I/O, no provider SDKs, fully testable offline.

Modules:
- ``templates``  minimal ``{{var}}`` interpolation
- ``suite``      Suite/Case/config models and the config fingerprint
- ``assertions`` the pluggable assertion registry
- ``snapshot``   baseline snapshot records + the Wilson interval
- ``results``    run records (what happened)
- ``verdict``    the statistical diff engine (what changed)
"""

from promptdrift.domain.assertions import ASSERTION_TYPES, AssertionSpec, BaseAssertion
from promptdrift.domain.results import (
    AssertionOutcome,
    CaseResult,
    Run,
    SampleResult,
    TokenUsage,
)
from promptdrift.domain.snapshot import (
    Snapshot,
    SnapshotCase,
    SnapshotRate,
    wilson_interval,
)
from promptdrift.domain.suite import (
    Case,
    Message,
    MockConfig,
    MockRule,
    OpenAICompatConfig,
    Pricing,
    Suite,
)
from promptdrift.domain.verdict import (
    AssertionDiff,
    CaseDiff,
    FailOn,
    SuiteDiff,
    Verdict,
    classify_assertion,
    diff_case,
    diff_run,
)

__all__ = [
    "ASSERTION_TYPES",
    "AssertionDiff",
    "AssertionOutcome",
    "AssertionSpec",
    "BaseAssertion",
    "Case",
    "CaseDiff",
    "CaseResult",
    "FailOn",
    "Message",
    "MockConfig",
    "MockRule",
    "OpenAICompatConfig",
    "Pricing",
    "Run",
    "SampleResult",
    "Snapshot",
    "SnapshotCase",
    "SnapshotRate",
    "Suite",
    "SuiteDiff",
    "TokenUsage",
    "Verdict",
    "classify_assertion",
    "diff_case",
    "diff_run",
    "wilson_interval",
]
