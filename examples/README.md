# Examples

Each folder is a self-contained promptdrift project layout. Copy one into your
repo and point `provider:` at your real endpoint.

- **`support-agent/`** — an OpenAI-compatible suite against a GLM endpoint
  (works the same for DeepSeek/Qwen/OpenAI by changing `base_url` and the key
  env var): Chinese customer-service prompts with contains/regex assertions
  and latency budgets.
- **`extractor/`** — structured extraction: `is_json` + `json_schema`
  assertions pinning the output contract.

Try any of them offline first by swapping the `openai_compat` block for:

```yaml
provider:
  mock:
    rules:
      - contains: "退款"
        text: "您好，请打开订单页点击申请退款，3-5 个工作日到账。"
    default: "您好"
```

Then: `promptdrift run` → `promptdrift approve` → `promptdrift diff`.
