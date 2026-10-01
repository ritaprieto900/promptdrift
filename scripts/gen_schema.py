"""Regenerate schema/promptest.schema.json from the pydantic models.

Run after changing any Suite/Case/provider/assertion model:

    uv run python scripts/gen_schema.py
"""

from __future__ import annotations

import json
from pathlib import Path

from promptdrift.domain.suite import Suite

ROOT = Path(__file__).parents[1]
TARGET = ROOT / "schema" / "promptest.schema.json"


def main() -> None:
    schema = Suite.model_json_schema()
    TARGET.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {TARGET}")


if __name__ == "__main__":
    main()
