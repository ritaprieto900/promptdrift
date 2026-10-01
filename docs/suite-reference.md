# Suite reference

Everything lives in one YAML file, validated before anything runs (with editor completion
via the published [JSON Schema](https://github.com/promptdrift/promptdrift/blob/main/schema/promptest.schema.json)).

## Top-level keys

| Key | Type | Default | Notes |
|---|---|---|---|
| `suite` | string | required | kebab-case identifier, used in snapshot filenames |
| `description` | string | — | free text |
| `provider` | mapping | required | `openai_compat` or `mock` |
| `judge` | mapping | — | optional grading provider for `judge` assertions |
| `samples` | int 1-20 | `3` | samples per case (cases can override) |
| `concurrency` | int 1-32 | `4` | max in-flight provider calls |
| `cases` | list | required | at least one |

## Providers

`openai_compat` works with any OpenAI-shaped endpoint:

| Key | Default | Notes |
|---|---|---|
| `model` | required | |
| `base_url` | `https://api.openai.com/v1` | GLM, DeepSeek, Qwen, Moonshot, vLLM, Ollama |
| `api_key_env` | `OPENAI_API_KEY` | name of the env var holding the key |
| `temperature`, `max_tokens`, `top_p`, `seed` | — | forwarded per request |
| `timeout_seconds` | `120` | |
| `max_retries` | `2` | retries 429/5xx/transport errors with backoff |
| `pricing` | — | `{prompt_per_1m, completion_per_1m}`, enables `promptdrift cost` |

`mock` runs fully offline:

| Key | Notes |
|---|---|
| `rules` | list of `{contains, text}` or `{contains, variants}`; first match wins |
| `default` | text when no rule matches |
| `default_variants` | cycles per call; simulates flakiness |

The `judge` block uses the same shape as a provider. Point it at a cheap, fast model with
low temperature.

## Cases

| Key | Type | Notes |
|---|---|---|
| `id` | string | kebab-case, unique, identity in the baseline |
| `description` | string | — |
| `messages` | list | `{role, content}`; roles: system / user / assistant |
| `vars` | mapping | values coerced to strings; `{{name}}` in content is substituted |
| `samples` | int | overrides suite-level for this case |
| `assertions` | list | see below |

## Assertions

One assertion per list item. Deterministic types use the key as the field:

```yaml
- equals: "exact text"
- contains: "substring"
- not_contains: "forbidden"
- regex: "^步骤 1"          # re.search, DOTALL
- is_json: true
- json_schema: {"type": "object", "required": ["id"]}
- latency_under: 3000        # milliseconds, per sample
- completion_tokens_under: 400
```

`judge` takes a mapping:

```yaml
- judge:
    rubric: |
      回复是否包含明确的退款步骤？
      5 = 步骤完整且语气友好；1 = 没有回答问题。
    min_score: 4             # 1-5, default 3
```

Each sample is sent to the judge model with the rubric and the conversation; the reply must
contain a JSON score. Parse failures and out-of-scale scores count as failed samples, which
multi-sample statistics then report as unstable rather than a gate failure.

Assertion identity is derived from type plus target (for `judge`, a hash of the rubric), so
it stays stable across runs and becomes the key in the baseline.

## What changes the baseline vs what the diff measures

The config fingerprint covers: model, base_url, sampling params, sample count, judge
config. Changing any of these makes the baseline stale; approve again. Prompt text, vars,
mock rule text, assertion targets, and pricing are *not* in the fingerprint: changing them
is a measured behavior change, not staleness.
