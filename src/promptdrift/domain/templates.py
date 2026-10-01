"""Minimal ``{{var}}`` interpolation for prompt text.

Deliberately not Jinja, and not anything Turing-complete: suite files are
*data*, not programs. A template may only substitute named variables;
everything else — including stray braces — stays literal text. This keeps
suite files trivially reviewable in diffs and free of an execution surface
inside your own test definitions.

Rules:
- ``{{name}}`` is replaced with ``str(vars[name])``.
- Variable names follow ``[A-Za-z_][A-Za-z0-9_]*``.
- Referencing an undefined variable is a hard error at load time.
- Unmatched braces (e.g. JSON payloads, ``{{{a}}}``) pass through untouched.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

_VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class MissingTemplateVarError(ValueError):
    """A template references a variable the case does not define."""


def referenced_vars(text: str) -> list[str]:
    """Return the distinct variable names referenced by *text*, in order."""
    return list(dict.fromkeys(match.group(1) for match in _VAR.finditer(text)))


def missing_vars(text: str, known: Iterable[str]) -> list[str]:
    """Return referenced variable names that are absent from *known*."""
    known_names = set(known)
    return [name for name in referenced_vars(text) if name not in known_names]


def render(text: str, variables: Mapping[str, object]) -> str:
    """Substitute ``{{var}}`` occurrences in *text*."""

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            available = ", ".join(sorted(variables)) or "<none defined>"
            raise MissingTemplateVarError(
                f"template references {{{{{name}}}}} but the case defines no such var "
                f"(available: {available})"
            )
        return str(variables[name])

    return _VAR.sub(substitute, text)
