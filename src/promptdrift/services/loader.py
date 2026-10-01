"""Suite loading: YAML file → validated model, with human-readable failures.

Suite files are edited by hand, so this module's whole job is turning
pydantic's validation noise into a short list of ``file: what: why`` lines a
human can act on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from promptdrift.domain.suite import Suite
from promptdrift.errors import SuiteLoadError

DEFAULT_SUITE_FILENAME = "promptest.yaml"


def suite_from_dict(raw: object, source: str = "<suite>") -> Suite:
    """Validate a raw mapping into a :class:`Suite`."""
    if not isinstance(raw, dict):
        raise SuiteLoadError(f"{source}: expected a YAML mapping at the top level")
    data: dict[str, Any] = dict(raw)
    data.pop("$schema", None)  # editor-completion hint, not part of the model
    try:
        return Suite.model_validate(data)
    except ValidationError as exc:
        lines = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error["loc"]) or "<root>"
            lines.append(f"  - {loc}: {error['msg']}")
        raise SuiteLoadError(f"{source} failed validation:\n" + "\n".join(lines)) from exc


def load_suite(path: Path) -> Suite:
    """Read and validate a suite YAML file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SuiteLoadError(f"cannot read suite file {path}: {exc}") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SuiteLoadError(f"{path} is not valid YAML: {exc}") from exc
    return suite_from_dict(raw, source=str(path))


def resolve_suite_path(root: Path, explicit: Path | None) -> Path:
    """Find the suite file: explicit path, else ``promptest.yaml``, else a
    uniquely-named ``*.promptest.yaml`` in *root*."""
    if explicit is not None:
        return explicit if explicit.is_absolute() else root / explicit
    default = root / DEFAULT_SUITE_FILENAME
    if default.exists():
        return default
    candidates = sorted(root.glob("*.promptest.yaml"))
    if candidates:
        return candidates[0]
    raise SuiteLoadError(
        f"no suite file found in {root}: expected {DEFAULT_SUITE_FILENAME} "
        "(create one with `promptdrift init`)"
    )
