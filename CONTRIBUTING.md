# Contributing to promptdrift

Thanks for helping make prompt changes reviewable. This document covers setup,
the architecture map, and the project's quality bar.

## Setup

```bash
git clone https://github.com/promptdrift/promptdrift
cd promptdrift
uv sync          # installs the dev group (pytest, ruff, pyright, ...)
uv run pytest    # must be fully green before any PR
```

Quality bar (all enforced in CI):

```bash
uv run ruff check .          # lint
uv run ruff format .         # formatting
uv run pyright               # types (0 errors)
uv run pytest --cov=promptdrift   # coverage gate ≥ 90%
```

## Architecture map

Dependencies point strictly downward; the domain layer imports nothing with I/O.

```text
CLI (cli/app.py)                    ← entry point, exit-code mapping
Services (services/)                ← orchestration: Runner, Differ, Reporter, Cost, Loader
Domain (domain/)                    ← PURE: suite, assertions, results, snapshot, verdict engine
Ports (ports.py)                    ← Provider / Cache protocols
Adapters (adapters/)                ← mock, openai_compat, sqlite cache, YAML snapshot store
```

Consequences worth preserving:

- Every verdict-path test runs offline on the mock provider. CI never touches a real
  endpoint; adapter HTTP behavior is simulated with respx.
- The verdict engine (`domain/verdict.py`) is pure math. Changes there must update
  `tests/unit/test_verdict.py`, including the hand-checked Wilson reference values.
- Report formats are pinned by golden files (`tests/golden/`). Regenerate deliberately:

  ```bash
  PROMPTDRIFT_REGEN_GOLDEN=1 uv run pytest tests/golden -q
  ```

- The JSON Schema is generated from the pydantic models. After touching any
  Suite/Case/provider/assertion model:

  ```bash
  uv run python scripts/gen_schema.py
  ```

  `tests/test_schema_sync.py` fails if you forget.

## Design invariants

These are product decisions, not implementation details. PRs that weaken them need
an explicit argument in the description:

1. **Noise alone can never fail the default gate.** A regression verdict requires
   Wilson intervals to separate (or a pure all-pass ⇄ all-fail flip).
2. **Prompt content changes are measured, never treated as staleness.** Only model,
   sampling params, and sample count feed the config fingerprint.
3. **Exit codes are a contract**: 0 pass, 1 gate/assertion failure, 2 config/runtime error.
4. **The demo must work with zero API keys and zero network.**
5. **Baselines are committed, human-reviewable YAML.** No binary or opaque state.

## Submitting

- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`).
- One logical change per PR; include tests for behavior changes.
- Good first contributions: see the M1/M2 items in the README roadmap — the `judge`
  assertion (rubric scoring), the GitHub Action, and the mkdocs site are all well-scoped.
