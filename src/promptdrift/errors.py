"""Exception hierarchy for promptdrift.

Every error raised deliberately by this package derives from
:class:`PromptdriftError`, so embedders can catch one type. The CLI maps
these to documented exit codes; library users handle them directly.
"""

from __future__ import annotations


class PromptdriftError(Exception):
    """Base class for all promptdrift errors."""


class SuiteLoadError(PromptdriftError):
    """A suite file could not be read or did not validate."""


class StaleBaselineError(PromptdriftError):
    """The on-disk baseline was recorded for a different execution config.

    Raised on ``config_fingerprint`` mismatch. Re-run ``promptdrift approve``
    to record a fresh baseline for the new configuration.
    """


class SnapshotLoadError(PromptdriftError):
    """A baseline snapshot file exists but could not be parsed."""


class ProviderError(PromptdriftError):
    """A provider adapter failed to produce a completion (auth, HTTP, ...)."""
