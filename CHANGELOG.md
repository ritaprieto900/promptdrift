# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-01

### Changed

- Published on PyPI as `promptdrift-py`; PyPI's name-confusion policy blocks the
  bare name (the empty project `prompt-drift` is edit distance 1). The install
  command, CLI binary, and Python imports remain `promptdrift`.

### Added

- `judge` assertion: LLM-as-judge rubric scoring on a 1-5 scale. The suite-level `judge:`
  block configures a separate (usually cheaper) grading model, its scores feed the same
  multi-sample statistics as deterministic assertions, and unparseable judge replies fail
  the sample rather than the gate.
- mkdocs documentation site and a ready-to-copy GitHub Actions workflow for consumer repos.

### Added — M0

- Core domain: `Suite`/`Case` models with readable YAML validation, `{{var}}` templating,
  and a config fingerprint that guards baseline comparability.
- Verdict engine: multi-sample pass rates compared with Wilson score intervals; verdicts
  `regressed` / `improved` / `stable` / `unstable` / `new` / `removed`; gates
  `--fail-on regression|flaky|any-fail`.
- Deterministic assertions: `equals`, `contains`, `not_contains`, `regex`, `is_json`,
  `json_schema`, `latency_under`, `completion_tokens_under`.
- Providers: `openai_compat` (OpenAI/GLM/DeepSeek/Qwen/Moonshot via `base_url`, retries
  with backoff) and an offline `mock` (rules, variant cycling for flaky simulation).
- Response cache (sqlite, read-through) and per-run cost estimation.
- Baseline snapshots as committed, human-reviewable YAML.
- CLI: `init`, `run`, `diff`, `approve`, `show`, `cost`, `demo`, `schema`, `version`;
  JUnit XML and markdown report output; exit codes 0 pass / 1 gate failure / 2 error.
- Published JSON Schema for suite files (editor completion).
- Offline test suite, ruff and pyright clean, CI matrix Python 3.10-3.13 on
  Linux/macOS/Windows.

[0.1.0]: https://github.com/ritaprieto900/promptdrift/releases/tag/v0.1.0
