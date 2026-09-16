# Changelog

## 0.2.1 — 2026-09-16

Production readiness, web dashboard, cross-platform compatibility, and deployment packaging.

### Added
- `agent-eval serve`: Built-in zero-dependency web dashboard server and REST API for visual benchmark run inspection, per-case trajectory replays, and browser-based benchmark execution.
- Production containerization: Multi-stage `Dockerfile`, `docker-compose.yml`, non-root user execution, and `.dockerignore`.
- Cross-platform CI matrix: Added Windows runner (`windows-latest`) alongside Ubuntu in `.github/workflows/ci.yml`.
- Make targets: `make serve`, `make docker-build`, and `make docker-run`.

### Fixed
- Cross-platform encoding: Resolved `UnicodeEncodeError: 'charmap'` and UTF-8 console output issues on Windows.
- Dataset line-ending determinism: Enforced `newline="\n"` on dataset generation for exact SHA-256 byte-matching across all operating systems.
- Pytest collection warnings: Suppressed `PytestCollectionWarning` on `TestCase` schema dataclass.

## 0.2.0 — 2026-09-12

FDE rebuild: the platform re-landed against the FDE field guide's portfolio
contract (six principles, constraint-simulation checklist, presentation
rules). Product behavior unchanged where it was already right; handover,
demo, and engagement-record layers added; two real incidents found and fixed.

### Added
- `make demo` (`scripts/demo.py`): the two-minute one-command demo — healthy
  run → deliberately injected regression (−26.8pp) → GATE FAIL with exit 1 →
  per-case diagnosis (flips, McNemar p = 6.1e-05, 3-bucket taxonomy). Shows
  the failure path on purpose; dated output; works from a clean clone.
- `agent-eval status`: operator weekly health view — latest run per
  benchmark vs baseline (pp drift + verdict), golden-dataset sha256s, judge
  calibration state; exits 1 on regression so cron can watch it. 5 unit
  tests.
- Engagement record (`docs/fde/`): verbatim fictional-composite customer
  brief, discovery notes (questions / assumptions killed / scope cut),
  requirements spec (US-1..7, FR-1..10, NFR-1..8), acceptance criteria +
  outcome metrics frozen in writing before the build with measured results.
- FDE synthesis (`docs/fde/FDE-SYNTHESIS.md`): what the field guide teaches,
  applied — six principles, brief #12 mapping, constraint checklist (6/6),
  presentation contract, repo hygiene (9/9), and the three conscious
  departures from the guide.
- Handover artifacts: RUNBOOK.md (alarm-by-alarm ops procedures, sharp
  edges, escalation — executed by the clean-room validator), INCIDENTS.md
  (8 real incidents incl. 2 found during this rebuild), DECISIONS.md (10
  decision records: alternative / reason / accepted cost).
- Portfolio presentation: docs/fde/WRITE-UP.md (the guide's 8-section
  structure), docs/fde/90-SECOND-STORY.md (+ follow-up depth Q&A).
- README rewritten for the "what is this" first-screen test (one paragraph,
  one sketch, one demo command) with handover links.

### Fixed
- INC-7: pytest `eval_case` fixture missing on clean-clone runs — the
  plugin was only registered via the `pytest11` entry point (requires
  install). `tests/conftest.py` now declares `pytest_plugins` explicitly;
  the raw tree tests green without `pip install`.
- INC-8: demo run discovery assumed a new file per run; deterministic run
  ids overwrite instead. mtime-snapshot discovery; documented as runbook
  sharp edge #4.

### Changed
- Version 0.1.0 → 0.2.0; test count 121 → 126; Makefile gains `demo` and
  `status` targets.

## 0.1.0 — 2026-09-12

Initial release: "pytest for Agentic AI".

### Added
- Agent adapter protocol + 5 built-in pattern agents (ReAct, Plan-and-Execute,
  Supervisor, Swarm, Map-Reduce) on a deterministic scripted backend with
  skill/fault knobs; LangGraph / OpenAI Agents SDK / CrewAI adapters
  (import-guarded, stub-tested; real-framework runs: not measured yet).
- Harness: tool gateway with permissions, arg guards, ablatable
  retry/verification/tool-validation/context-optimization; step/tool/time/
  output caps; network sandbox; fault injection.
- 280 machine-verified golden cases (5 patterns × 56; 6 categories incl.
  adversarial and failure-inducing), byte-identical regeneration.
- 20 evaluators: deterministic outcome/tool checks, trajectory + behavioral
  metrics (alignment, efficiency, loop, termination, recovery, planning), and
  LLM-as-judge (deterministic rubric backend measured at Cohen's κ = 1.0 on a
  56-case hand-labeled sample after v1.1 fix; live OpenAI-compatible backend
  implemented, unmeasured).
- Metrics with Wilson 95% intervals; run records + redacted JSONL event logs
  with full version bundles.
- Baselines, comparison (exact McNemar), regression engine with
  benchmark-specific gates and CI exit codes.
- CLI (`agent-eval`): run / list / validate / compare / report / regression /
  baseline / ablate / calibrate / repro / info. pytest plugin + markers.
- CI: ci.yml (lint/type/tests/validation), eval-gate.yml (blocking quality
  gates), security.yml (secret scan, gitleaks, pip-audit, injection eval).
- Experiments executed and recorded: full-suite scores, harness ablation
  attribution, judge calibration (κ 0.082 → 1.0 documented), reproducibility
  (0.0pp same-seed spread), regression demo (gate FAIL on −14.3pp).

### Fixed during the build (see engineering journal)
- Benchmark-config override silently disabling CLI ablation experiments.
- Process-salted `hash()` seeding breaking dataset determinism.
- Double-wrapped answer specs masking gold references from answer evaluators.
- Rubric judge token-F1 verbosity penalty (24/56 false negatives vs humans).
- Agent retry loop re-queueing failed wrong-tool decisions instead of
  re-planning the original action.
