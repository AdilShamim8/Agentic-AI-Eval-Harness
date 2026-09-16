# Requirements Specification — Agentic AI Evaluation Platform

Version 1.0 · Frozen 2026-09-11 (before implementation) · Derived from
[01-DISCOVERY-NOTES.md](01-DISCOVERY-NOTES.md) · Customer:
[Cascade SaaS, Inc.](00-ENGAGEMENT-BRIEF.md) (fictional composite)

This is the requirements half of the FDE loop's discovery stage: the
negotiated contract between the platform team and three agent teams who did
not ask for governance. It is written so that engineers and the customer's
leads both accept it — the field guide calls this "documents that engineers
and customers both accept," and the acceptance test is that every threshold
below is visible in a committed file a team lead can review and veto.

## 1. User stories

Each story names its owner — the negotiated part. Format: the operator who
lives with the requirement, not the vendor feature.

- **US-1 (merge-time, every agent developer):** "When I open a PR that changes
  my agent, CI fails with a table telling me which quality metric dropped, by
  how much, against which threshold — and which cases flipped — so I fix it
  before merge, not after an incident."
- **US-2 (nightly, platform on-call):** "When a nightly full suite regresses
  versus the committed baseline, the run record and report are already on disk
  with a 3-bucket failure split, so my first diagnostic is one command, not an
  investigation."
- **US-3 (weekly, ops):** "When I open my terminal on Monday, one command
  shows me every benchmark's latest pass rate, its drift vs baseline, dataset
  integrity, and judge calibration state — and it exits non-zero if anything
  regressed, so my cron does the watching."
- **US-4 (per-team, agent lead):** "When my team's threshold is too tight, I
  change one reviewed YAML file with a PR — the platform enforces, my team
  decides."
- **US-5 (onboarding a new agent, any team):** "When my agent follows the
  adapter protocol (task in → actions + result out), the harness runs it
  against the shared golden cases with zero framework lock-in, and the
  pytest bridge means my existing test suite already knows how to fail."
- **US-6 (quarterly, privacy counsel):** "When legal asks what an agent did in
  a disputed case, the run's event log reconstructs every tool call, argument,
  result, and timing — and contains no stored chain-of-thought."
- **US-7 (budget review, VP Eng):** "When finance asks what evaluation costs,
  every run record carries a cost estimate and the deterministic CI path shows
  $0.00 actual."

## 2. Functional requirements

Numbered for traceability; each carries its verification surface.

- **FR-1 Adapter protocol.** Framework-agnostic boundary: task in →
  (action/tool-call stream, final answer) out. Built-in reference agents for
  five patterns (ReAct, Plan-and-Execute, Supervisor, Swarm, Map-Reduce).
  LangGraph, OpenAI Agents SDK, and CrewAI adapters implement the same
  protocol; frameworks are optional dependencies. *Verify: adapters module +
  stub tests; live-framework runs marked Not measured yet.*
- **FR-2 Golden datasets.** ≥ 250 machine-verified cases across the five
  patterns, spanning six categories: normal, difficult, ambiguous, edge,
  adversarial, failure-inducing. Every case validates against a typed schema;
  datasets regenerate byte-identically from pinned seeds. *Verify:
  `agent-eval validate`; `agent-eval list datasets` (280 cases, sha256 shown).*
- **FR-3 Evaluator suite.** (a) Deterministic evaluators: exact/semantic
  answer checks, JSON schema, tool-selection and tool-argument correctness,
  step-limit, termination. (b) LLM-as-judge with structured output, versioned
  prompts, published rubric, confidence; judge backends: deterministic rubric
  engine and OpenAI-compatible live client. (c) Trajectory/behavioral
  evaluators: tool precision, tool efficiency, loop detection, recovery
  behavior. No chain-of-thought capture anywhere. *Verify: evaluators module +
  20 registered evaluators + tests.*
- **FR-4 Run pipeline.** Agent → adapter → harness (tool gateway with
  permissions, retry, verification, context optimization, resource caps,
  network sandbox) → runner → per-case verdicts + aggregate metrics (Wilson
  95% CI, latency p50/p95, token/cost estimates, behavior rates). Every run
  emits a deterministic run record + JSONL event log. *Verify: `agent-eval
  run` artifacts in `evals/runs/`.*
- **FR-5 Baselines & regression.** Named baselines; per-benchmark metric
  thresholds in a reviewable, versioned file (`configs/gates.yaml`);
  regression engine exits non-zero on breach; **fails closed** when data is
  insufficient. *Verify: `agent-eval regression`; demo Act 2b.*
- **FR-6 Reporting.** Markdown + JSON reports distinguishing TEST FAILURE /
  EVALUATOR ERROR / INFRASTRUCTURE FAILURE, with per-category breakdown,
  flips, and gate sections. *Verify: `agent-eval report`.*
- **FR-7 Comparison.** Run-vs-run comparison with per-case flips and exact
  McNemar test; version drift warnings. *Verify: `agent-eval compare`.*
- **FR-8 Experiments.** Harness ablation (remove retry/verification/tool
  validation/context optimization and measure what breaks), judge calibration
  vs hand labels (Cohen's κ, FP/FN counts), reproducibility repeats
  (same-seed and varied-seed). *Verify: `make experiments`;
  `evals/results/experiments.json`.*
- **FR-9 Operator surface.** Rich CLI (11 commands), `make` targets mirroring
  CI, pytest bridge (`pytest -m agent_eval`), weekly status command with
  regression exit code. *Verify: `agent-eval status`; `make demo`.*
- **FR-10 Security & governance.** Threat model documented; secret scanning;
  permission-gated tool access; network sandbox; step/token/resource caps;
  audit trail per run; prompt-injection-resistant case schema.
  *Verify: `make security`; `tests/security/`.*

## 3. Non-functional requirements

- **NFR-1 Determinism.** Same (agent, benchmark, seed, ablation, dataset) →
  byte-identical verdicts and metrics. Non-negotiable: without it, regression
  detection is noise. *Measured: 0.0pp spread, byte-identical records.*
- **NFR-2 CI budget.** Eval stage ≤ 10 minutes on 2-core runners, offline
  (no egress). *Measured: seconds (deterministic backend).*
- **NFR-3 Judge reliability.** Cohen's κ ≥ 0.6 vs hand labels before any
  judge verdict gates CI. *Measured: 1.0 (rubric v1.1, n=56); v1.0's 0.082
  documented as the reason the bar exists.*
- **NFR-4 Reproducibility band.** Same-seed repeats within 2.0pp; varied-seed
  spread reported so teams can size their own noise floor.
- **NFR-5 Zero fabrication.** Any number published by the platform must be
  measured by a committed script, or explicitly labeled *Not measured yet*.
  Enforced by review and by the release checklist, not by hope.
- **NFR-6 Dependency minimalism.** One runtime dependency (PyYAML). The
  customer's egress-restricted CI must be able to install it from a mirror.
- **NFR-7 Observability of the observer.** The harness versions itself:
  benchmark, dataset, evaluator, judge-prompt, and platform versions recorded
  on every run; version drift between compared runs is a warning.
- **NFR-8 Auditability.** Every run reconstructs: who (agent id), what (tool
  calls + results), when (timestamps), how well (verdicts), at what cost.

## 4. Non-goals (agreed with the customer)

From the brief and discovery; repeated here because non-goals are
requirements turned inside out.

1. No web dashboard or hosted UI in v1 (ops: "dead on arrival" — the CI
   viewer is the viewer).
2. No chain-of-thought capture or storage (privacy counsel).
3. No model hosting, fine-tuning, or leaderboard bake-offs.
4. No auto-remediation / auto-rollback in v1 (detection first; trust later).
5. No trace-vendor integration (no OTel backend exists on their estate).
6. Not a load-testing or latency-benchmarking tool for the agents' APIs.

## 5. Constraints discovered (the ones we did not choose)

| Constraint | Source | Architectural consequence |
|---|---|---|
| No egress in CI | finance policy post-audit | Deterministic default backend; live judge is opt-in and separate |
| 2-core runner, 10-min budget | their CI fleet | Pure-Python runner; sub-second full runs; no model downloads |
| Ops touches nothing new | ops representative | pytest + make + exit codes; `agent-eval status` one command |
| Teams own thresholds | three leads' negotiation | `configs/gates.yaml` per-benchmark, PR-reviewable |
| No CoT storage | privacy counsel | Action-layer traces only |
| Framework churn | three stacks, fast-moving | Adapter protocol at the boundary; framework deps optional |
| Judge trust deficit | support lead + our own κ=0.082 scare | Calibration experiment precedes any judge gating |

## 6. Requirements → acceptance mapping

Every functional requirement above has a numbered acceptance criterion in
[03-ACCEPTANCE-CRITERIA.md](03-ACCEPTANCE-CRITERIA.md), and every acceptance
criterion has a reproduction command. That mapping is the loop closing:
discovery → requirements → **spec → build → measurement** — with nothing
asserted that a reviewer cannot re-run.

---

## 7. v0.2.1 Addendum — Web Dashboard, Containerization, and Multi-OS CI (2026-09-16)

Following initial deployment and multi-platform validation, v0.2.1 added:

- **US-8 (visual audit, team lead / reviewer):** "When evaluating an agent's failure
  modes during a PR review, I can open a web browser to inspect interactive pass-rate
  cards, compare runs side-by-side, and replay step-by-step observable trajectories
  without installing any third-party UI dependencies."
- **FR-11 Zero-dependency Web Dashboard & REST API.** Built-in HTTP server (`agent-eval serve`)
  powered by standard library `http.server` providing interactive web UI on port 8000
  and REST API (`/api/status`, `/api/runs`, `/api/benchmarks`, `/api/run`).
- **FR-12 Containerization & Rootless Packaging.** Multi-stage `Dockerfile` (Python 3.12-slim,
  non-root user `aeh`, UID 10001) and `docker-compose.yml` defining `runner`, `status`, and
  `dashboard` services.
- **FR-13 Cross-platform Determinism & Invariance.** Enforced LF line endings via `.gitattributes`
  and byte-level CRLF normalization in dataset integrity verification (INC-10). Automated UTF-8
  stream reconfiguration on Windows consoles (INC-9). Dual-OS CI runner matrix (Ubuntu + Windows).

