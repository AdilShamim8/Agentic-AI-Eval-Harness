# Benchmark Design

## Why
A benchmark is a measurement instrument; uncontrolled variation makes it a
random number generator. Versioned YAML + content-hashed datasets + pinned
seeds make every score attributable to a specific (agent, harness, dataset)
tuple.

## How
`benchmarks/*.yaml` defines: name/version/pattern, dataset path, evaluator
list, pass thresholds, execution settings (limits, permissions, ablation,
category filters, case limits), and regression gates. Loader validates cross
references (known evaluators, thresholds in [0,1], dataset exists). Cases are
JSONL with id/pattern/category/task/expected{answer, required/forbidden
tools, golden trajectory, max_steps, task_checks, instructions}/faults.

## Trade-offs
- Registry-as-directory (git-friendly, CI-friendly) vs a service (queryable,
  stateful): we chose files; a service can wrap the same loader later.
- Per-case category filters vs separate datasets: filters avoid duplication.

## Failure modes
- Threshold theater: gates tuned so tight that normal variance fails them —
  mitigated by Wilson CI reporting and `min_cases_for_gate`.
- Dataset drift: caught by sha256 in the run manifest + byte-identical
  regeneration test (a real bug — process-salted seeding — was caught this way).

## Experimental evidence
Every benchmark loads and validates (`agent-eval validate` = VALID across all
7); regeneration hash equality is asserted in
tests/integration/test_runner_e2e.py.
