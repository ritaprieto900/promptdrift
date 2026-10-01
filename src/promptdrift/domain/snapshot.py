"""Baseline snapshots: the recorded "known-good" state of a suite.

A snapshot is a human-reviewable YAML file committed next to the suite —
jest snapshots, but for behavior. The models here are pure
data; YAML serialization lives in the adapters layer.

``wilson_interval`` lives here too: it is a property of rates, and both the
snapshot rates and the verdict engine need it — without a cycle.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

REPRESENTATIVE_OUTPUT_MAX_CHARS = 280

#: z-score for a ~95% two-sided confidence interval.
Z_95 = 1.959963984540054


def wilson_interval(passed: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, clamped to [0, 1].

    Degenerate proportions are exact: 0/total → lower bound 0, total/total →
    upper bound 1 (the formula only approaches these asymptotically).
    """
    if total <= 0:
        raise ValueError("total must be positive")
    p = passed / total
    z_squared = z * z
    denominator = 1 + z_squared / total
    center = p + z_squared / (2 * total)
    spread = z * math.sqrt(p * (1 - p) / total + z_squared / (4 * total * total))
    lower = max(0.0, (center - spread) / denominator)
    upper = min(1.0, (center + spread) / denominator)
    if passed == 0:
        lower = 0.0
    if passed == total:
        upper = 1.0
    return (lower, upper)


class SnapshotRate(BaseModel):
    """Pass/fail counts for one assertion across one run's samples."""

    model_config = ConfigDict(frozen=True)

    passed: int = Field(ge=0)
    total: int = Field(ge=1)

    @classmethod
    def from_pair(cls, pair: tuple[int, int]) -> SnapshotRate:
        passed, total = pair
        return cls(passed=passed, total=total)

    @property
    def rate(self) -> float:
        return self.passed / self.total

    def wilson(self, z: float = Z_95) -> tuple[float, float]:
        return wilson_interval(self.passed, self.total, z)


class SnapshotCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    samples: int
    mean_latency_ms: float = 0.0
    mean_prompt_tokens: float = 0.0
    mean_completion_tokens: float = 0.0
    representative_output: str = ""
    assertions: dict[str, SnapshotRate] = Field(default_factory=dict)


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: Literal[1] = 1
    suite: str
    model: str | None = None
    config_fingerprint: str
    recorded_at: datetime
    cases: list[SnapshotCase] = Field(default_factory=list)

    def case(self, case_id: str) -> SnapshotCase | None:
        for snapshot_case in self.cases:
            if snapshot_case.id == case_id:
                return snapshot_case
        return None
