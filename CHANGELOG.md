# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — M0

- Core domain: `Suite`/`Case` models with readable YAML validation, minimal
  `{{var}}` templating, config fingerprint guarding baseline comparability.
- Verdict engine: multi-sample pass rates compared with Wilson score intervals;
  verdicts `regressed` / `improved` / `stable` / `unstable` / `new` / `removed`;
  gates `--fail-on regression|flaky|any-fail`.
- Deterministic assertions: `equals`, `contains`, `not_contains`, `regex`,
  `is_json`, `json_schema`, `latency_under`, `completion_tokens_under`.
- Providers: `openai_compat` (OpenAI/GLM/DeepSeek/Qwen/Moonshot via `base_url`,
  retries with backoff) and offline `mock` (rules, variant cycling for flaky
  simulation).
- Response cache (sqlite, read-through) and per-run cost estimation.
- Baseline snapshots as committed, human-reviewable YAML.
- CLI: `init`, `run`, `diff`, `approve`, `show`, `cost`, `demo`, `schema`,
  `version`; JUnit XML and markdown report output; documented exit codes
  (0 pass / 1 gate failure / 2 error).
- Published JSON Schema for suite files (editor completion).
- Fully offline test suite (121 tests, ≥90% coverage), ruff + pyright clean,
  CI matrix Python 3.10–3.13 on Linux/macOS/Windows.

[Unreleased]: https://github.com/promptdrift/promptdrift/compare/v0.1.0...HEAD
