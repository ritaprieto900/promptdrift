"""Keep the checked-in JSON Schema in sync with the pydantic models.

The schema published at ``schema/promptest.schema.json`` powers editor
completion for suite files. If this test fails, regenerate it:

    uv run python -c "import json; from promptdrift.domain.suite import Suite; \\
open('schema/promptest.schema.json','w',encoding='utf-8').write(
json.dumps(Suite.model_json_schema(), indent=2, ensure_ascii=False) + '\\n')"
"""

from __future__ import annotations

import json
from pathlib import Path

from promptdrift.domain.suite import Suite

SCHEMA_PATH = Path(__file__).parents[1] / "schema" / "promptest.schema.json"


def test_checked_in_schema_matches_models() -> None:
    assert SCHEMA_PATH.exists(), f"missing {SCHEMA_PATH}"
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    current = Suite.model_json_schema()
    assert committed == current, (
        "schema/promptest.schema.json is stale — regenerate it with "
        "`uv run python scripts/gen_schema.py`"
    )


def test_schema_requires_suite_and_provider() -> None:
    schema = Suite.model_json_schema()
    assert "suite" in schema["required"]
    assert "provider" in schema["required"]
    assert "cases" in schema["required"]


def test_package_metadata_matches_version() -> None:
    import importlib.metadata

    from promptdrift import __version__ as v

    assert importlib.metadata.version("promptdrift-py") == v
