# Engineering Audit — Agentic AI Evaluation Harness

- **Repository:** https://github.com/AdilShamim8/Agentic-AI-Eval-Harness
- **Baseline commit reviewed:** `71bdbe8` (main, clean tree)
- **Audit window:** 2026-10-23; fix series `f20f36e..d09b3a0` (18 commits, pushed
  individually with per-commit verification)
- **Environment:** Ubuntu (sandbox), Python 3.12.15, pytest 8.x, ruff 0.17.2,
  mypy 1.x, package 0.2.1, single-runtime-dep install (PyYAML) plus dev extras.
  Docker CLI unavailable in the audit environment (Docker steps: NOT VERIFIED).
- **Auditor:** coordinated principal-engineer / SDET / eval-research / security /
  SRE roles; independent judge pass in `EVALUATION_INTEGRITY.md` §self-review.

## 1. Architecture summary (verified from source)

`agent-eval` CLI (argparse, rich optional) → benchmark registry (YAML, validated
at load) → `BenchmarkRunner` (per-case: fresh Environment → ToolGateway
[permissions → arg guards → validation/repair → retry/fault-injection →
limits] → ScriptedModel policy backend → trajectory capture) → evaluators
(deterministic tables + LLM-as-Judge rubric/live) → metrics aggregation
(Wilson CI, McNemar, kappa) → run records (deterministic v2 ids, atomic
persist, redacted JSONL events) → baselines → regression gates (compat
checks → sufficiency → thresholds; fail-closed) → reports / dashboard /
pytest bridge / CI.

Trust boundaries: benchmark+agent inputs untrusted; tools offline;
network guard blocks new sockets for the whole run with an explicit
evaluator-phase allowance (live judge) and fileno-wrap allowance (server
accept); arbitrary user-supplied agent code runs in-process (best-effort
control — container is the real isolation); dashboard = read-only viewer or
authorized executor, never both silently.

## 2. Audit scope

All 16 investigation leads (Issues A–L) from the engagement brief, plus a
full-repository pass: src (18 modules), tests, benchmarks/datasets/configs,
workflows, Dockerfile/compose, Makefile, scripts, docs claims. Every finding
below was **reproduced before fixing** (scripts preserved in the audit
trail; regression tests now pin the behavior).

## 3. Findings

See `FINDINGS.md` for the per-finding record (ID, severity, evidence, fix,
tests, validation, residual risk). Summary by severity:

| ID | Severity | Finding | Evidence | Status |
|---|---|---|---|---|
| F-01 | P0 | Run identity collisions: `--limit`/model config excluded from preimage → distinct experiments silently overwrote artifacts (CI smoke step did this every push) | full 56-case record replaced by 8-case record, same id `f8a00acfe9f5dc43` | FIXED (ids v2) + 9 tests |
| F-02 | P1 | Regression gate accepted incompatible baselines (cross-benchmark/dataset/selection/evaluators) — the CI gate compared failure_recovery vs react_basic and passed on meaningless numbers | repro: gate PASSED with 'ok' findings on incomparable evidence | FIXED (fail-closed, visible) + 8 tests |
| F-03 | P1 | `min_cases_for_gate` read from top level; shipped config declares it under `default:` → operator value ignored (hardcoded 10 always won) | 20-case run gated sufficient against configured minimum 30 | FIXED (4-level resolution) + 6 tests |
| F-04 | P1 | Live-judge responses unvalidated: `passed:'false'` (string) → case marked PASSED; score 5.0 silently clamped; contradictions honored; missing score manufactured passed=True/score 0.0 | mocked-transport repro table | FIXED (contract + recorded fallback) + 18 tests |
| F-05 | P1 | Live judge impossible under network sandbox (SecurityViolation escaped → every case EVALUATOR_ERROR); global monkeypatch also crashed server accept loops | exception escaped LiveJudge.evaluate | FIXED (evaluator-phase allowance + fileno wrap; local HTTP double proves live judging during sandboxed run) |
| F-06 | P1 | CI quality checks non-blocking (`|| true`) while repo had REAL failures: ruff format 42+ files, mypy 15 errors — hidden behind green CI | baseline outputs captured | FIXED (repo clean; checks blocking) |
| F-07 | P1 | CI/Makefile run selection by `ls -t` (mtime) — gated the wrong benchmark's artifact | workflow text + local replay | FIXED (explicit id capture, self-verifying benchmark assert) |
| F-08 | P1 | Entire Makefile non-functional (8-space recipes → `make` aborts: 'missing separator'); every documented make workflow broken | `make -n install` failed | FIXED (tabs) + gate target rewrite |
| F-09 | P1 | Dashboard: read-only compose mount vs POST /api/run (opaque 500); stored XSS (unescaped record fields, inline onclick); ACAO:*; unbounded bodies; 500s for client errors; limit=0 silently = full run | payload record rendered with markup; 413/503 paths | FIXED (modes + validation + escaping) + 7 tests |
| F-10 | P1 | Run artifacts written in place twice — crash mid-write clobbers records; concurrent readers see partial JSON; dashboard runs unserialized | sentinel-record crash test | FIXED (tmp+os.replace atomic, execute lock) |
| F-11 | P2 | CLI crashes without rich (assert ERR is not None) on the documented minimal install | AssertionError traceback on invalid dataset | FIXED (_err/_out helpers) + 3 tests incl. subprocess |
| F-12 | P2 | `PermissionPolicy.from_dict` AttributeError for ANY permissions block — the security-policy feature was unusable | repro: AttributeError | FIXED (secure defaults never dropped) + 2 tests |
| F-13 | P2 | Sandbox/concurrency: evaluation-phase redesign documented in THREAT-MODEL (Egress row) | — | FIXED (with F-05) |
| F-14 | P3 | `AEH_RUNS_DIR`/`AEH_BASELINES_DIR` declared by Dockerfile, read nowhere | grep: only Dockerfile | FIXED (core/paths.py single source of truth) + 4 tests |
| F-15 | P3 | Stale release-layout duplicates committed (`source/` 67 files drifted, `infra/.github`, root MANIFEST) — active integrity hazard (old buggy judge readable in two places) | diff vs src; nothing reads them | FIXED (removed; evaluators/ reviewer copies refreshed) |
| F-16 | P3 | Docs drift: README 126 tests (actual 152→215); RELEASE_NOTES referenced removed source/; historical counts ambiguous | rg sweep | FIXED (consistency sweep + dated addendum) |

## 4. Baseline vs final (executed evidence)

| Check | Baseline @ 71bdbe8 | Final @ d09b3a0 |
|---|---|---|
| pytest | 152 passed | **215 passed** (63 regression tests added) |
| ruff check | PASS | PASS |
| ruff format --check | **FAIL (42+ files)** | PASS (83 files) |
| mypy | **FAIL (15 errors)** | PASS (58 files) |
| CI visibility of the above | hidden (`|| true`) | **blocking** |
| make demo / make gate / any make | **broken (missing separator)** | exit 0 / GATE PASS |
| 7 benchmarks | 89.3/73.2/80.4/82.1/76.8, fr 87.5, adv 100 | identical (reproduced; byte-identical repro ×5) |
| Tracked run-record churn on re-runs | every run rewrote committed records | **none** (v2 ids; verified after 15+ runs) |
| validate_release (clean-room zip) | not run at baseline | **ALL 9 PASS — RELEASE VALIDATED** |
| scan_secrets --strict | clean | clean |

## 5. Remaining limitations

- Docker build/compose-up: NOT VERIFIED (no docker in audit env); compose YAML
  validated; image logic unchanged except documented modes.
- Live-backend judge reliability/latency/cost: still *Not measured yet* (no
  endpoint in build env) — interfaces contract-tested via local HTTP doubles.
- pip-audit remains advisory (explicit commented decision, not silent).
- In-process network guard remains best-effort against arbitrary user-supplied
  agent code (documented; container is the real boundary).
- GitHub Actions results were not observable from the audit environment
  (pushes succeeded; workflow YAML validated locally; the exact CI commands
  replayed locally green).
