# Regression Testing (for agents)

## Why
Agent "upgrades" (new model, prompt tweak, harness change) routinely trade
one capability for another. Without gates, regressions ship silently and get
discovered in production.

## How
Baselines: `agent-eval run --baseline main` persists headline metrics +
versions. Gates: `agent-eval regression RUN --baseline main` compares overall
pass rate and per-evaluator pass rates against configs/gates.yaml thresholds
(max allowed drop, default −3pp), with `min_cases_for_gate` (fail-closed when
n is too small for statistics) and per-benchmark overrides. Exit code 1 fails
CI. Comparisons add per-case flip lists and the exact McNemar test so a
"3-point drop" can be judged against noise.

## Trade-offs
- Absolute thresholds (benchmark-level) vs relative deltas (baseline-level):
  we use both — thresholds define "good enough to ship", deltas define "no
  silent degradation".
- Fail-closed on insufficient data blocks small smoke runs from gating —
  intentional: underpowered gates are theater.

## Failure modes
- Baseline staleness: re-baseline deliberately, in a reviewed PR that updates
  the baseline file (version bundle makes drift visible).
- Over-gating on tiny deltas: Wilson CIs and McNemar p-values contextualize
  every comparison.

## Experimental evidence
Demo: baseline 89.3% vs challenger 75.0% (skill .70 + no_retry) → REGRESSION
DETECTED on 4 metrics, exit 1; identical-quality rerun → GATE PASS, exit 0.
