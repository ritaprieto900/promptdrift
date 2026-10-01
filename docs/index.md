# promptdrift

Prompt regression testing with CI gating. You edit a prompt, promptdrift re-runs the same
cases, compares against a baseline snapshot committed to your repo, and fails CI when
behavior got statistically worse. Sampling noise never trips the gate.

## Install and try

```bash
pipx install promptdrift
promptdrift demo
```

`demo` runs a full loop offline on a scripted mock provider: run a suite, approve a
baseline, apply a prompt change that breaks behavior, then watch `diff` catch it and exit 1.

## The workflow

1. **Write a suite** (`promptest.yaml`) describing cases, assertions, and a provider.
   `promptdrift init` scaffolds one that runs offline.
2. **`promptdrift run`** executes it. Every case runs `samples` times; assertions are
   checked per sample.
3. **`promptdrift approve`** records the run as the baseline, a YAML file under
   `.promptest/baselines/`. Commit it.
4. **`promptdrift diff`** re-runs and compares against the baseline. Exit code 1 means the
   gate failed. In CI this blocks the merge.

When you accept a behavior change on purpose, run `approve` again and commit the updated
snapshot. The diff on that file in your PR is the reviewed behavior change.

## Where to go next

- [Verdict semantics](verdicts.md): what regressed / unstable / stable actually mean, and
  how the statistics decide.
- [Suite reference](suite-reference.md): every config key and assertion type.
- [CI setup](ci.md): GitHub Actions workflow, exit codes, and PR reports.

## Links

- [GitHub repository](https://github.com/ritaprieto900/promptdrift)
- [中文 README](https://github.com/ritaprieto900/promptdrift/blob/main/README.zh-CN.md)
