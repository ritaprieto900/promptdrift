# promptdrift

**Know what your prompt change actually did.**

Flake-aware prompt regression testing and CI gating — snapshot-diff first, Python-native.

[![CI](https://github.com/promptdrift/promptdrift/actions/workflows/ci.yml/badge.svg)](https://github.com/promptdrift/promptdrift/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)](https://pypi.org/project/promptdrift/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230)](https://github.com/astral-sh/ruff)
[![Checked with pyright](https://img.shields.io/badge/checked%20with-pyright-blue)](https://microsoft.github.io/pyright/)

[中文文档](README.zh-CN.md)

---

Every team shipping LLM features iterates on prompts. Every prompt edit can silently break
behavior that used to work. `promptdrift` makes that visible and preventable: it re-runs the
same cases against your prompt, compares pass rates against a **committed baseline snapshot**,
and fails CI only when behavior got *statistically significantly* worse.

## 30-second tour (no API key needed)

```bash
pipx install promptdrift
promptdrift demo
```

The demo runs a complete loop offline on a scripted mock provider:

1. `run` — execute a suite (3 samples per case)
2. `approve` — record the behavior as the baseline
3. someone "improves" the prompt (the mock answer loses its substance)
4. `diff` — the drift is caught, gate fails, exit code 1 — the merge would be blocked

```text
step 4/4 — diff: catch the drift
┌──────────────┬─────────────────────┬────────┬───────┬────────────────┐
│ case         │ assertion           │ before │ after │ verdict        │
├──────────────┼─────────────────────┼────────┼───────┼────────────────┤
│ refund-steps │ contains-申请退款    │ 3/3    │ 0/3   │ 🔴 regressed   │
│              │ regex-3-5-个工作日   │ 3/3    │ 0/3   │ 🔴 regressed   │
│ invoice-json │ is_json-yes         │ 3/3    │ 3/3   │ ✅ stable      │
└──────────────┴─────────────────────┴────────┴───────┴────────────────┘
❌ gate FAILED — 1 regressed case(s)
```

## Why not just assert on outputs?

LLM outputs are **non-deterministic**. A naive CI check — "output must contain X" — fails
randomly, gets retried, gets disabled. promptdrift's verdict engine is built for the noise:

| Verdict | Meaning | Gate (`--fail-on`) |
|---|---|---|
| 🔴 `regressed` | pass rate fell **beyond sampling noise** (Wilson score intervals must separate) | fails `regression` (default) |
| ⚠️ `unstable` | samples disagree where the baseline was deterministic | fails only `flaky` |
| 🟢 `improved` | pass rate rose beyond noise | never fails |
| ✅ `stable` | within noise | — |
| 🆕 `new` / ➖ `removed` | case or assertion added/removed since the baseline | fails `any-fail` when imperfect |

In practice: with `samples: 3`, a 3/3 → 2/3 drop is flagged ⚠️ **unstable** (a warning), not
🔴 regressed — noise alone can never block a merge. Raise the sample count to sharpen the
statistics; `promptdrift cost` tells you what that costs before you run.

## How it works

```text
promptest.yaml ──► Runner ──► Run ──► Differ ◄── Snapshot (.promptest/baselines/*.snap.yaml)
   (cases,             │                    │
   assertions,         └── provider ──► cache (sqlite)      ▲
   samples)                   ▲                             │
                    openai_compat / mock          `promptdrift approve` records one
```

- **Baseline snapshots are YAML files you commit.** A PR that changes a snapshot file is a
  reviewed behavior change, exactly like jest snapshots.
- **The config fingerprint** (model + sampling params + sample count) guards comparability:
  change the model and the baseline is *stale* (exit 2) instead of silently mis-compared.
  Editing prompt text, vars, or mock answers is *not* staleness — that's exactly what the
  diff should measure.
- **One adapter covers most providers**: any OpenAI-compatible endpoint (OpenAI, GLM,
  DeepSeek, Qwen, Moonshot, vLLM, Ollama) via `base_url`.

## Suite file

```yaml
$schema: https://raw.githubusercontent.com/promptdrift/promptdrift/main/schema/promptest.schema.json
suite: support-agent
provider:
  openai_compat:
    model: glm-4.7
    base_url: https://open.bigmodel.cn/api/paas/v4
    api_key_env: ZHIPUAI_API_KEY
    pricing: {prompt_per_1m: 1.0, completion_per_1m: 8.0}   # enables `promptdrift cost`
samples: 3
cases:
  - id: refund-steps
    messages:
      - role: user
        content: "订单有点问题，我想申请{{topic}}"
    vars:
      topic: 退款
    assertions:
      - contains: "申请退款"
      - regex: "3-5 个工作日"
      - not_contains: "抱歉"
      - latency_under: 3000
```

Assertion types in M0: `equals` · `contains` · `not_contains` · `regex` · `is_json` ·
`json_schema` · `latency_under` · `completion_tokens_under`.

## Commands

| Command | What it does | Exit codes |
|---|---|---|
| `promptdrift init` | scaffold a runnable starter suite (mock provider) | |
| `promptdrift run` | execute once; exit 1 if any assertion failed | 0/1/2 |
| `promptdrift approve` | record the current behavior as the baseline | |
| `promptdrift diff` | run + compare to baseline; **the CI gate** (`--fail-on regression\|flaky\|any-fail`, `--md report.md` for PR comments) | 0/1/2 |
| `promptdrift show` | inspect the latest run or the baseline | |
| `promptdrift cost` | estimate calls and cost (with configured pricing) | |
| `promptdrift demo` | the offline end-to-end walkthrough | |
| `promptdrift schema` | JSON Schema for suite files (editor completion) | |

Exit codes: `0` pass · `1` gate or assertion failure · `2` config/runtime error.

CI usage (the baseline snapshot must be committed):

```yaml
- run: pipx install promptdrift
- run: promptdrift diff --require-baseline --md pr-report.md
```

## Positioning

| | promptdrift | promptfoo | DeepEval |
|---|---|---|---|
| Language | Python | Node/TypeScript | Python |
| Core primitive | **baseline snapshot diff** | eval runs + web viewer | pytest metrics |
| Non-determinism | multi-sample + interval statistics | per-run assertions | metric thresholds |
| Review flow | snapshot file diff in the PR | open the web UI | read pytest output |

promptfoo is a great broader eval platform; DeepEval shines at metric research. promptdrift
does one narrow thing: **gating prompt changes in CI with a verdict you can trust.**

## Roadmap

- **M1** — `judge` assertion (LLM-as-judge with rubric scoring, judge model decoupled), richer
  markdown reports, selective re-runs
- **M2** — GitHub Action with sticky PR comments, docs site (mkdocs), PyPI release
- **M3** — embedding-similarity assertion, multi-suite projects, cross-model comparison mode

## Development

```bash
git clone https://github.com/promptdrift/promptdrift
cd promptdrift
uv sync
uv run pytest              # 120+ tests, fully offline
uv run ruff check .        # lint
uv run pyright             # types
```

The entire test suite runs on the mock provider — CI never touches a real endpoint.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the architecture map.

## License

[Apache-2.0](LICENSE)
