# Acceptance Criteria & Outcome Metrics — The Quality Bar, In Writing, Before The Build

Frozen 2026-09-11 (before implementation). Results column filled 2026-09-12
from committed experiment artifacts — every result carries its reproduction
command. This document is FDE principle #5 made literal: *decide what
"worked" means before you build, and report it after.* A project that reports
outcomes chosen after the fact "has the epistemics of a marketing page"
(field guide, `portfolio/01-what-to-build.md`).

Legend: **AC** = acceptance criterion (the bar) · **OM** = outcome metric
(the point of the whole engagement).

## 1. Acceptance criteria

| # | Criterion (frozen before build) | Result (measured) | Reproduce |
|---|---|---|---|
| AC-1 | Framework-agnostic adapter protocol with 5 reference agents; LangGraph / OpenAI Agents SDK / CrewAI adapters protocol-complete | **Met.** 5 pattern agents + 3 framework adapters; adapters stub-tested (live-framework runs: *Not measured yet* — no frameworks/egress in build env) | `pytest tests/integration/test_harness_and_adapters.py` |
| AC-2 | ≥ 250 machine-verified golden cases, 5 patterns, 6 categories (incl. adversarial + failure-inducing) | **Met.** 280 cases (5 × 56), all validate; sha256-pinned | `agent-eval validate && agent-eval list datasets` |
| AC-3 | Deterministic + judge + trajectory evaluator suite; judge must reach κ ≥ 0.6 vs hand labels **before** judge verdicts gate anything | **Met.** 20 evaluators; κ = 1.000 (rubric v1.1, n=56); v1.0 measured κ = 0.082 and was rejected — documented, not hidden | `agent-eval calibrate --labels evals/calibration/hand_labels.csv` |
| AC-4 | Same-seed reproducibility spread ≤ 2.0pp | **Met — exceeded.** 0.0pp, run records byte-identical | `agent-eval repro --benchmark react_basic --repeats 5` |
| AC-5 | Regression gate exits non-zero on threshold breach; fails closed on insufficient data | **Met.** Demo: injected −26.8pp drop → exit 1, 6 metrics flagged; `pass_on_insufficient: false` | `make demo` (Act 2b) |
| AC-6 | Every report separates TEST FAILURE / EVALUATOR ERROR / INFRASTRUCTURE FAILURE | **Met.** Schema-level taxonomy; demo run: 18 / 0 / 0 | `agent-eval report <run_id>` |
| AC-7 | Full eval stage ≤ 10 min on a 2-core runner, offline | **Met — exceeded.** Full 5-benchmark suite: seconds (deterministic backend); suite runs with egress blocked | `make experiments` |
| AC-8 | Zero fabricated numbers: every published number measured by a committed script or labeled *Not measured yet* | **Met.** All numbers in this doc trace to `evals/results/experiments.json` or the demo transcript; unmeasured items listed in §4 | `git log -- evals/results/` |
| AC-9 | Action-layer traces only (no CoT capture), per privacy counsel | **Met.** Event logs: tool calls, args, results, timings, termination | `agent-eval info <run_id>` + event JSONL |
| AC-10 | Handover: runbook + incidents + decision records, executable without the author | **Met.** RUNBOOK.md, INCIDENTS.md (10 incidents), DECISIONS.md (13 ADRs); runbook path executed by the clean-room release validator | `python scripts/validate_release.py` |
| AC-11 | Zero-dependency Web Dashboard (`agent-eval serve`) & REST API with interactive trajectory replay | **Met.** Built-in standard library HTTP server; 6 unit tests passing | `pytest tests/unit/test_web_server.py` |
| AC-12 | Enterprise containerization: multi-stage rootless Dockerfile (non-root `aeh`) & Docker Compose | **Met.** Multi-stage build, runner/status/dashboard profiles | `docker compose config` |
| AC-13 | Multi-OS CI runner matrix (Ubuntu + Windows) with invariant cryptographic dataset digests | **Met.** Dual-OS matrix green across Python 3.11/3.12; 132 tests green | `pytest tests/` |

## 2. Outcome metrics (the customer's definition of "worked")

Defined in the frozen version of this document, before code existed:

| # | Outcome metric (frozen) | Before (their world) | After (measured) | Reproduce |
|---|---|---|---|---|
| OM-1 | Regression detection latency | 9 days (billing incident, found via support volume) | **< 60 s at merge time** (gate command: 0.3 s; whole demo incl. two full runs + diagnosis: 1.3 s) | `make demo` |
| OM-2 | A silently-regressed agent reaches production | yes — the incident | **No**: gate exits 1 (CI blocks); 6 of 7 gated metrics flagged on the injected regression | `make demo` Act 2b |
| OM-3 | Failure localization effort | "an investigation" | 3-bucket split + flipped-case list + McNemar p = 6.1e-05 in one compare command | `agent-eval compare <healthy> <regressed>` |
| OM-4 | Quality signal trustworthiness | none (no signal) | 280-case golden sets, Wilson 95% CIs on every rate; κ-calibrated judge; 0.0pp repro band | `agent-eval run` |
| OM-5 | Evaluation cost per day | unknown, feared ($4k surprise invoice history) | **$0.00 actual** (deterministic CI); ~$0.03/day modeled at 24 runs/day ($0.0012/run, simulated pricing, labeled) | run metrics + `agent-eval status` |
| OM-6 | Ops adoption burden | "they will not learn a new tool" | **0 new tools**: `make`, pytest, exit codes; weekly health = one command | `make status` |

## 3. The honesty annex — what is *Not measured yet*

Per AC-8, listed rather than buried (full detail in `docs/final-report.md`):

- **Live-LLM judge reliability** (κ on a live model backend): the rubric
  engine and the live client are implemented; the build environment has no
  egress/keys. The measured κ = 1.0 is the deterministic rubric judge on
  hand-labeled cases.
- **Live-backend latency and cost**: p95 0.217 ms and $0.0012/run are
  deterministic-backend numbers (simulated pricing on estimated tokens).
- **Real-framework adapter runs** (LangGraph/OpenAI SDK/CrewAI agents through
  their actual runtimes): adapters are protocol-complete and stub-tested.
- **A real operator's weekly usage**: `agent-eval status` is new; no human has
  run it weekly yet. The clean-room validator executes the runbook path.

## 4. Sign-off line (fictional composite, but the discipline is real)

> Bar frozen 2026-09-11 by the platform team and accepted by the three agent
> leads + ops + privacy counsel (fictional composite engagement; see
> [00-ENGAGEMENT-BRIEF.md](00-ENGAGEMENT-BRIEF.md)). Results recorded
> 2026-09-12 from committed artifacts. Any future claim that weakens a number
> above requires editing this file in a visible commit — which is the point.

The field guide's formulation is why this file exists: "the quality bar and
the outcome metric were defined in writing before the build started" is the
last unchecked box on the constraint-simulation checklist — and the one that
separates measured outcomes from marketing.
