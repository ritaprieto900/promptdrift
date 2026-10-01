# Verdict semantics

promptdrift compares one run against the baseline per **case × assertion**. Each assertion
is checked on every sample, producing a pass rate like 2/3. The verdict engine then
classifies the change. Everything here is pure math over those rates; the implementation
lives in `domain/verdict.py`.

## Wilson score intervals

For a rate of `passed/total`, the engine computes a Wilson score interval at 95%
confidence (`z ≈ 1.96`). A rate of 3/3 does not mean "always passes"; its interval is
roughly [0.44, 1.0], which encodes how little three samples can tell you.

Two rates are compared by checking whether their intervals separate:

- baseline lower bound above the new upper bound → the new rate is **significantly worse**
- new lower bound above the baseline upper bound → **significantly better**
- overlapping intervals → the difference could be noise

## The six verdicts

| Verdict | Condition | Default gate |
|---|---|---|
| 🔴 `regressed` | Intervals separate in the bad direction, or a pure flip (all-pass → all-fail) | fails |
| ⚠️ `unstable` | The baseline was pure (0% or 100%) and the new samples disagree with each other | passes (`flaky` fails it) |
| 🟢 `improved` | Intervals separate in the good direction, or a pure flip upward | passes |
| ✅ `stable` | Intervals overlap in both directions | passes |
| 🆕 `new` | No baseline entry for this case or assertion | passes (`any-fail` fails imperfect ones) |
| ➖ `removed` | The case disappeared from the suite | passes |

Examples worth internalizing:

- `samples: 3`, baseline 3/3, new 2/3 → **unstable**. The intervals overlap, and a baseline
  that always passed now sometimes fails, which is a flakiness smell rather than proof of a
  regression.
- `samples: 10`, baseline 10/10, new 3/10 → **regressed**. Intervals separate.
- `samples: 1`, baseline 1/1, new 0/1 → **regressed**. With one sample the comparison is
  deterministic; a pure flip is always significant.
- baseline 2/3, new 0/3 → **stable**. The baseline was already noisy, so a further drop
  cannot be attributed with confidence. Approve baselines from stable runs.

## Choosing the gate

`promptdrift diff --fail-on <level>`:

- `regression` (default): fails only on regressed cases. Use this everywhere; it is the
  zero-false-positive setting.
- `flaky`: additionally fails unstable cases. Use when a case must be deterministic, for
  example before a release.
- `any-fail`: fails when any assertion has an imperfect pass rate, including new cases.
  Strictest setting, sensitive to noise by definition.

## Sharpening the statistics

More samples separate smaller true changes from noise. The tradeoff is cost and latency;
`promptdrift cost` estimates the call count (and money, when pricing is configured) before
you commit to a higher sample count. Judge assertions also produce one call per sample per
judge assertion, which the estimate includes.
