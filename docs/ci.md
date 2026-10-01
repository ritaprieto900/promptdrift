# CI setup

The gate is `promptdrift diff`: exit 0 passes, exit 1 means a regression, exit 2 means
something is misconfigured (stale baseline, missing suite file, unreadable output). The
baseline snapshot under `.promptest/baselines/` must be committed.

## GitHub Actions

```yaml
name: prompt-drift
on:
  pull_request:

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5

      - name: Install promptdrift
        run: uv tool install git+https://github.com/ritaprieto900/promptdrift

      - name: Gate the prompt change
        run: promptdrift diff --require-baseline --md pr-report.md
        env:
          ZHIPUAI_API_KEY: ${{ secrets.ZHIPUAI_API_KEY }}

      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: promptdrift-report
          path: pr-report.md
```

Notes:

- `--require-baseline` turns a missing baseline into exit 2. Without it, a repo that never
  approved a baseline would silently pass.
- `--md pr-report.md` writes the markdown report; upload it as an artifact, or post it as a
  PR comment with your comment bot of choice.
- Set the provider's `api_key_env` name to whatever secret name you use; the tool reads the
  key from that environment variable only.

## Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | gate passed | merge |
| 1 | regression (or assertion failure on `run`) | review the diff, fix or re-approve |
| 2 | config or runtime error | stale baseline, missing suite, provider auth; fix the setup |

## Caching

Responses are cached in sqlite at `.promptest/cache.db`, keyed by provider, model,
messages, and sampling params. Re-running unchanged cases replays stored completions, so
`diff` on a PR that only touched README costs nothing. The cache is local; CI starts cold,
which is fine because the gate needs fresh behavior anyway.

## Re-approving after an accepted change

When a PR changes prompt behavior on purpose, the author runs `promptdrift approve` locally,
commits the new snapshot in the same PR, and reviewers see the behavior change as the
snapshot diff. A change of model, sampling params, or judge config also requires
re-approval: the old baseline is stale by definition.
