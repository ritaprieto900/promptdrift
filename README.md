# promptdrift

**Know what your prompt change actually did.**

Prompt regression testing with CI gating. Snapshot-diff first, flake-aware by design, Python native.

[![CI](https://github.com/promptdrift/promptdrift/actions/workflows/ci.yml/badge.svg)](https://github.com/promptdrift/promptdrift/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)](https://pypi.org/project/promptdrift/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230)](https://github.com/astral-sh/ruff)

[中文文档](README.zh-CN.md)

Teams that ship LLM features edit prompts constantly, and every edit can quietly break
behavior that used to work. promptdrift catches that: it re-runs the same cases against your
prompt, compares pass rates against a baseline snapshot you commit to git, and fails CI when
behavior got statistically worse. Noise never trips the gate.

## Quick tour, no API key needed

```bash
pipx install promptdrift
promptdrift demo
```

The demo runs a complete loop offline on a scripted mock provider:

1. `run` executes a suite (3 samples per case)
2. `approve` records the behavior as the baseline
3. the mock answer gets "improved" and loses its structured steps
4. `diff` catches the drift and exits 1, the way CI would

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

## Why plain assertions aren't enough

LLM output is non-deterministic. A CI check like "output must contain X" fails randomly,
gets retried, and eventually gets disabled. The verdict engine handles the noise instead:

| Verdict | Meaning | Gate behavior |
|---|---|---|
| 🔴 `regressed` | pass rate fell beyond sampling noise (Wilson score intervals separate) | fails `regression` (default) |
| ⚠️ `unstable` | samples disagree where the baseline was deterministic | fails only `flaky` |
| 🟢 `improved` | pass rate rose beyond noise | never fails |
| ✅ `stable` | within noise | passes |
| 🆕 `new` / ➖ `removed` | case or assertion added or removed since the baseline | fails `any-fail` when imperfect |

Concretely: at `samples: 3`, a 3/3 → 2/3 drop is ⚠️ unstable, a warning. At `samples: 10`,
10/10 → 3/10 is 🔴 regressed. Raise the sample count to sharpen the statistics; run
`promptdrift cost` first to see what that costs.

## How it fits together

```
promptest.yaml ──► Runner ──► Run ──► Differ ◄── Snapshot (.promptest/baselines/*.snap.yaml)
                       │                          ▲
                       └── provider ──► sqlite cache
```

Baselines are YAML files you commit. When a PR touches one, that diff *is* the behavior
change under review, the same way jest snapshots work. A config fingerprint (model, sampling
params, sample count, judge model) protects comparability: swap the model and the old
baseline goes stale instead of being silently mis-compared. Editing prompt text, vars, or
mock answers is never staleness; that is exactly the change the diff should measure.

One provider adapter covers every OpenAI-compatible endpoint (OpenAI, GLM, DeepSeek, Qwen,
Moonshot, vLLM, Ollama), configured with `base_url`.

## Suite file

```yaml
$schema: https://raw.githubusercontent.com/promptdrift/promptdrift/main/schema/promptest.schema.json
suite: support-agent
provider:
  openai_compat:
    model: glm-4.7
    base_url: https://open.bigmodel.cn/api/paas/v4
    api_key_env: ZHIPUAI_API_KEY
    pricing: {prompt_per_1m: 1.0, completion_per_1m: 8.0}
judge:                          # optional: grades `judge` assertions
  openai_compat:
    model: glm-4.7-flash
    base_url: https://open.bigmodel.cn/api/paas/v4
    api_key_env: ZHIPUAI_API_KEY
    temperature: 0.1
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
      - judge:
          rubric: |
            回复是否包含明确的退款步骤（入口、操作、时限）？
            5 = 步骤完整且语气友好；1 = 没有回答问题。
          min_score: 4
```

Deterministic assertions: `equals`, `contains`, `not_contains`, `regex`, `is_json`,
`json_schema`, `latency_under`, `completion_tokens_under`. The `judge` assertion sends each
sample to the judge model with your rubric and expects a 1-5 score; `min_score` sets the
pass bar. Judges are only human (well, only models), so their scores feed the same
multi-sample statistics as everything else: a wavering judge shows up as ⚠️ unstable, not as
a blocked merge.

## Commands

| Command | Purpose |
|---|---|
| `promptdrift init` | scaffold a starter suite (mock provider, runs offline) |
| `promptdrift run` | execute once; exit 1 if any assertion failed |
| `promptdrift approve` | record current behavior as the baseline |
| `promptdrift diff` | run and compare against the baseline; this is the CI gate |
| `promptdrift show` | inspect the latest run or the baseline |
| `promptdrift cost` | estimate calls and cost (when pricing is configured) |
| `promptdrift demo` | the offline end-to-end walkthrough |
| `promptdrift schema` | JSON Schema for suite files (editor completion) |

`diff` options that matter in CI: `--fail-on regression|flaky|any-fail`,
`--require-baseline`, and `--md report.md` to write a PR-ready markdown report.

Exit codes: 0 pass, 1 gate or assertion failure, 2 config or runtime error.

```yaml
# GitHub Actions, minimal version (see docs/ci.md for the full one)
- run: uv tool install git+https://github.com/promptdrift/promptdrift
- run: promptdrift diff --require-baseline --md pr-report.md
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## How it compares

| | promptdrift | promptfoo | DeepEval |
|---|---|---|---|
| Language | Python | Node/TypeScript | Python |
| Core primitive | baseline snapshot diff | eval runs + web viewer | pytest metrics |
| Non-determinism | multi-sample + interval statistics | per-run assertions | metric thresholds |
| Review flow | snapshot diff in the PR | open the web UI | read pytest output |

promptfoo is the broader eval platform and DeepEval is strong on metric research. This
project stays narrow: gate prompt changes in CI, with a verdict you can trust.

## Roadmap

- selective re-runs of changed cases only; embedding-similarity assertion
- composite GitHub Action + sticky PR comments once the PyPI release lands
- multi-suite projects, cross-model comparison mode

## Development

```bash
git clone https://github.com/promptdrift/promptdrift
cd promptdrift
uv sync
uv run pytest              # 150+ tests, fully offline
uv run ruff check .
uv run pyright
```

The whole test suite runs on the mock provider, so CI never touches a real endpoint.
CONTRIBUTING.md has the architecture map and the design invariants.

## License

[Apache-2.0](LICENSE)
