# Product Requirements — agent-eval-harness v0.1

Date: 2026-09-12 · Owner: Principal AI Engineer · Status: approved for build

## 1. Problem

Teams shipping LLM agents lack a `pytest`-grade instrument for them. Existing tooling
either traces without gating (Langfuse), gates single prompts (promptfoo), or couples
evaluation to one vendor runtime (LangSmith/LangGraph). Consequences: regressions ship
undetected (agent behavior degrades while outcome scores look flat), failures are
blamed on "the model" without evidence, and evaluation results are not reproducible.

## 2. Target users

1. **Agent engineers** (primary): plug in an agent (LangGraph / OpenAI Agents SDK /
   CrewAI / custom), run standardized benchmarks locally and in CI, compare versions.
2. **ML platform teams**: own quality gates for agent releases; need failure taxonomy,
   reproducibility, and audit trails.
3. **QA/release engineers**: consume pass/fail gates and Markdown evidence in PRs.

## 3. User stories (v0.1)

- US1: As an agent engineer, I run `agent-eval run --benchmark react_basic --agent builtin:react`
  and get a run record + Markdown report with per-evaluator scores, trajectory metrics,
  and failure taxonomy.
- US2: As a platform engineer, I store a baseline, then `agent-eval regression RUN --baseline main`
  fails CI when pass rate drops beyond a configured threshold.
- US3: As an engineer debugging a failure, I open the run's JSONL event log and see
  every step, tool call, evaluator execution, and failure class for the failing case.
- US4: As a harness author, I run `agent-eval ablate --benchmark failure_recovery
  --profiles full,no_retry,no_verification,...` and get a measured attribution table.
- US5: As a QA engineer, I run the suite as pytest (`pytest -m agent_eval`) for smoke.
- US6: As an evaluator author, I implement one `evaluate(case, result)` method and the
  runner, metrics, reports, and gates pick it up by name.
- US7: As a security reviewer, I read SECURITY.md + THREAT-MODEL.md and verify
  controls with `pytest tests/security`.

## 4. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | Agent adapter protocol + 5 built-in pattern agents (ReAct, Plan-Execute, Supervisor, Swarm, Map-Reduce) + LangGraph/OpenAI Agents SDK/CrewAI adapters (import-guarded, stub-tested) |
| FR-2 | Versioned YAML benchmark registry with dataset, evaluators, thresholds, execution settings, gates |
| FR-3 | 280 golden cases across 5 patterns with 6 categories incl. adversarial + failure-inducing; manifest + sha256; deterministic regeneration |
| FR-4 | Deterministic evaluator suite: exact match, contains, forbidden, numeric tolerance, schema, tool selection, tool arguments, step limit, termination, task checks |
| FR-5 | LLM-as-judge: rubric fallback judge (measured), OpenAI-compatible live client (implemented, unmeasured in build env), versioned prompts, judge metadata |
| FR-6 | Trajectory/behavioral evaluators: alignment, tool-selection F1, efficiency, loop, termination, recovery, planning coverage |
| FR-7 | Harness controls: step/tool/time/output/state limits, permissions, retries, verification, tool-arg validation, context optimization — all ablatable via profiles |
| FR-8 | Run records (JSON) + event logs (JSONL, redacted) + run manifest with full VersionBundle |
| FR-9 | Metrics: pass rate + Wilson 95% CI, per-evaluator/pattern/category, latency p50/p95 (measured wall), token & cost estimates (labeled), failure histogram |
| FR-10 | Comparison + baselines + regression engine with per-benchmark gates and CI exit codes |
| FR-11 | Reports: Markdown + JSON, distinguishing TEST FAILURE / EVALUATOR ERROR / INFRASTRUCTURE FAILURE |
| FR-12 | CLI: run / list / validate / compare / report / regression / baseline / ablate / calibrate / repro / info |
| FR-13 | Pytest bridge: `agent_eval` marker, case fixture, smoke suite |
| FR-14 | CI workflows: ci, eval-gate (blocking), security; Makefile mirrors |
| FR-15 | Experiments executed and recorded: full suite, ablation matrix, judge calibration (kappa), reproducibility (repeats), regression demo |

## 5. Non-functional requirements

- Correctness: evaluators unit-tested; runner never conflates failure classes.
- Reproducibility: same inputs + seed => byte-identical run records (verified by test).
- Zero network at runtime by default (tools are offline fixtures; socket guard on).
- Runtime: full 280-case suite < 60 s on the deterministic backend; smoke < 10 s.
- Extensibility: new evaluator/adapter/tool = one module + registry entry.
- Observability: every case fully traced; exports redacted.
- Security: allowlist enforcement, arg guards, injection screening, audit log.
- DX: `pip install -e .` in seconds (single runtime dep: PyYAML).

## 6. Non-goals (v0.1)

Web UI/dashboard, SaaS, distributed execution, live production monitoring, OTLP
export, pairwise A/B judging, human-annotation UIs, model leaderboards, live-LLM
benchmark scores (interfaces provided; measurements marked Not measured yet).

## 7. Success criteria

Final quality gate list from the master build contract (5 patterns, 250+ cases,
deterministic + judge + trajectory + behavioral evaluation, harness ablations,
calibration, reproducibility, baselines, regression detection, CLI, pytest
integration, CI gates, observability, security controls, failure injection,
documentation) — each verifiable by command or test, no fabricated numbers.
