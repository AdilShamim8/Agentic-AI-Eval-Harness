# AGENTS.md — contribution & collaboration conventions

This file governs how engineering agents (human or AI) work in this repo.

## Working agreement

1. **Never fabricate results.** Every score, latency, cost, kappa, or
   reproducibility number must come from an executed run recorded under
   `evals/`. If it wasn't measured: write "Not measured yet."
2. **Determinism is a contract.** Datasets regenerate byte-identically
   (`scripts/generate_datasets.py`, master seed 20260912). Run records are
   semantically identical for the same (agent, benchmark, seed, ablation,
   dataset). Never introduce wall-clock, process-salted hashes, or dict
   ordering into any scoring path. (We shipped a bug exactly like this —
   see journal Day 8.)
3. **Evaluate the harness, not just the agent.** Any change to harness
   capabilities (retry/verification/validation/context-optimization) must be
   validated with `agent-eval ablate` before/after, and the measured deltas
   recorded in `docs/final-report.md`.
4. **Failure taxonomy is sacred.** TEST FAILURE vs EVALUATOR ERROR vs
   INFRASTRUCTURE FAILURE must stay separated at the schema level. Never catch
   an evaluator exception and mark the case as an agent failure.

## Workflow

- Read `/home/z/my-project/worklog.md` (or `docs/engineering-journal.md`)
  before starting; append your work record when done.
- Run `make test-fast` before committing; `make validate` before proposing
  benchmark/dataset changes; `make gate` before merging to main.
- New evaluator: one class + registry entry in `evaluators/__init__.py` +
  unit tests. Deterministic-first — an LLM judge needs a justification that no
  deterministic check suffices.
- New tool: `ToolSpec` in `agents/tools.py` with explicit arg schema + unit
  tests. No network, no subprocess, bounded output.
- New benchmark: YAML in `benchmarks/` + threshold gates + regression threshold
  in `configs/gates.yaml`.

## Style

- stdlib-first (single runtime dependency: PyYAML); dataclasses over pydantic.
- Modules own their failure classification via `core/errors.py`.
- Every public module carries a docstring stating WHY it exists.
- Line length 100; ruff-select E,F,W,I,UP,B.

## Testing obligations

- Every evaluator: table-driven unit tests incl. failure cases.
- Every harness control: a test proving the limit/guard actually fires.
- Datasets: `test_dataset_regenerates_byte_identical` must stay green.
- Security: `tests/unit/test_security_basics.py` +
  `tests/integration/test_harness_and_adapters.py` (permissions/sandbox).
