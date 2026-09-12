# Golden Datasets

## Why
Evaluators are only as trustworthy as the gold they compare against. Hand-built
gold drifts; tool-grounded gold (computed through the same tools the agent
uses) cannot contradict reality.

## How
`scripts/generate_datasets.py` (master seed 20260912, stable per-pattern seeds
via sha256) emits 5 patterns × 56 cases. Gold answers are computed by invoking
the REAL tools (calculator, knowledge_search, data_calc) — the generator also
asserts every QA-bank value appears in the actual top snippet. Categories:
normal(20) difficult(10) ambiguous(6) edge(8) adversarial(6)
failure_inducing(6) per pattern. Every case is then **machine-verified**: a
perfect agent (skill=1.0, zero faults) must pass every benchmark evaluator, or
generation aborts.

## Trade-offs
- Template-generated tasks vs fully free-form: templates buy determinism and
  verifiability at the cost of linguistic variety — mitigated by 12 task
  families and seeded parameter randomization.
- Hand-labeled trajectories are the expensive asset; generator-emitted golden
  paths + author review of the calibration sample is the accepted compromise.

## Failure modes
- Unit-mixing in aggregation tasks (summing Wh with mAh) — avoided by
  concept-consistent map families (validated at generation).
- Ambiguous questions whose noise terms flip snippet selection — QA and
  ambiguous banks are verified against the real corpus at generation time
  (two entries were rewritten during the build for exactly this reason).

## Experimental evidence
Generation output: "All cases verified: perfect agent passes every evaluator."
Byte-identical regeneration asserted in CI.
