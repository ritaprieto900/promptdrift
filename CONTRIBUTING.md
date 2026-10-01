# Contributing

Issues and PRs are welcome. This file covers setup, how the codebase is organized, and the
rules that keep the tool trustworthy.

## Setup

```bash
git clone https://github.com/ritaprieto900/promptdrift
cd promptdrift
uv sync          # installs the dev group: pytest, ruff, pyright, respx, ...
uv run pytest    # must be green before any PR
```

CI enforces the same gates you should run locally:

```bash
uv run ruff check .               # lint
uv run ruff format .              # formatting
uv run pyright                    # types, zero errors
uv run pytest --cov=promptdrift   # coverage gate at 90%
```

## Code layout

Dependencies point downward only. The domain layer imports nothing that does I/O.

```
CLI (cli/app.py)        entry points, exit-code mapping
Services (services/)    orchestration: Runner, Differ, Reporter, Cost, Loader, Judge
Domain (domain/)        pure: suite, assertions, results, snapshot, verdict engine
Ports (ports.py)        Provider / Cache protocols
Adapters (adapters/)    mock, openai_compat, sqlite cache, YAML snapshot store
```

Two consequences worth knowing before you change things:

- Every verdict-path test runs offline on the mock provider. Adapter HTTP behavior is
  simulated with respx, so CI never touches a real endpoint.
- Report formats are pinned by golden files in `tests/golden/`. If you change a format on
  purpose, regenerate with `PROMPTDRIFT_REGEN_GOLDEN=1 uv run pytest tests/golden -q`.

The JSON Schema in `schema/` is generated from the pydantic models. After touching any
Suite/Case/provider/assertion model, run `uv run python scripts/gen_schema.py`;
`tests/test_schema_sync.py` fails if you forget.

## Design rules

These are product decisions, and PRs that weaken them need to argue why in the description.

1. Noise alone can never fail the default gate. A regression verdict requires Wilson
   intervals to separate, or an all-pass to all-fail flip.
2. Prompt content changes are measured, never treated as staleness. Only model, sampling
   params, sample count, and judge model feed the config fingerprint.
3. Exit codes are a contract: 0 pass, 1 gate or assertion failure, 2 config or runtime error.
4. The demo must work with zero API keys and zero network.
5. Baselines are committed, human-reviewable YAML. No binary or opaque state.

## Submitting

Use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`), one logical
change per PR, tests included for behavior changes. Good first contributions are usually
the smaller roadmap items in the README; ask in an issue before picking up anything that
touches the verdict engine.
