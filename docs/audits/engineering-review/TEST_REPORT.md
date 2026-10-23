# Test Report — executed matrix

Environment: Ubuntu sandbox, Python 3.12.15, venv with `pip install -e .[dev]`
(pytest/ruff/mypy) — rich deliberately absent (validates the minimal-install
contract). Docker CLI unavailable (Docker rows: NOT VERIFIED).

| Test / command | Result | Exit | Tests | Failures | Skipped | Notes |
|---|---|---|---|---|---|---|
| `python -m pytest tests/ -q` (baseline @71bdbe8) | PASS | 0 | 152 | 0 | 0 | 3.6s |
| `python -m pytest tests/ -q` (final @d09b3a0) | PASS | 0 | **215** | 0 | 0 | +63 regression tests added by the audit |
| `ruff check src tests scripts` (baseline) | PASS | 0 | — | — | — | hid nothing (format was the failure) |
| `ruff format --check src tests scripts` (baseline) | **FAIL** | 1 | — | 42+ files (src alone) | — | hidden by CI `\|\| true` |
| `ruff format --check src tests scripts` (final) | PASS | 0 | — | 0 | — | 83 files formatted |
| `mypy src/agent_eval_harness` (baseline) | **FAIL** | 1 | — | 15 errors / 10 files | — | hidden by CI `\|\| true` |
| `mypy src/agent_eval_harness` (final) | PASS | 0 | — | 0 | — | 58 files, real fixes (no blanket ignores) |
| `agent-eval validate` | PASS | 0 | — | — | — | VALID: all benchmarks |
| `agent-eval list benchmarks / evaluators` | PASS | 0 | 7 / 20 | — | — | |
| `agent-eval run --benchmark react_basic` | PASS | 0 | 56 cases | — | — | 50/56 = 89.3% (id v2 `c732250d…`) |
| `agent-eval run --benchmark plan_execute_basic` | PASS | 0 | 56 | — | — | 41/56 = 73.2% |
| `agent-eval run --benchmark supervisor_basic` | PASS | 0 | 56 | — | — | 45/56 = 80.4% |
| `agent-eval run --benchmark swarm_basic` | PASS | 0 | 56 | — | — | 46/56 = 82.1% |
| `agent-eval run --benchmark map_reduce_basic` | PASS | 0 | 56 | — | — | 43/56 = 76.8% |
| `agent-eval run --benchmark failure_recovery` | PASS | 0 | 16 | — | — | 14/16 = 87.5% |
| `agent-eval run --benchmark adversarial` | PASS | 0 | 6 | — | — | 6/6 = 100% |
| `agent-eval repro --benchmark react_basic --repeats 3/5` | PASS | 0 | 3/5 | — | — | spread 0.0pp; byte-identical(same seed)=True |
| `agent-eval calibrate --labels evals/calibration/hand_labels.csv` | PASS | 0 | 56 labels | — | — | κ=1.0 (single annotator, labeled as such) |
| `agent-eval ablate --benchmark failure_recovery --skill 0.60` | PASS | 0 | 5 profiles | — | — | reproduces README: no_retry −12.5pp, recovery 50% |
| `agent-eval regression <id> --baseline main` (react run) | PASS | 0 | — | — | — | GATE PASS on comparable evidence |
| `agent-eval regression <failure_recovery id> --baseline main` (baseline code) | **WRONG-PASS** | 0 | — | — | — | the F-02 defect: invalid comparison accepted — now fails closed (incompatible_*) |
| `pytest -m agent_eval tests/e2e` (bridge) | PASS | 0 | 7 | 0 | 0 | |
| `make demo` (baseline code) | **BROKEN** | 2 | — | — | — | `missing separator` — entire Makefile non-functional (F-08) |
| `make demo` (final) | PASS | 0 | — | — | — | injected regression → GATE FAIL, exit 0 by design |
| `make gate` (final) | PASS | 0 | — | — | — | explicit run id, GATE PASS |
| `python -m build --wheel` | PASS | 0 | — | — | — | agent_eval_harness-0.2.1-py3-none-any.whl |
| clean venv install of wheel (outside repo, no rich) | PASS | 0 | — | — | — | imports OK; validate/run/status work (F-11 verified end-to-end) |
| `python scripts/package_release.py` | PASS | 0 | — | — | — | 203 files + manifest; zip 0.44 MB |
| `python scripts/validate_release.py` (clean-room zip) | **PASS — RELEASE VALIDATED** | 0 | 9 steps | 0 | 0 | extract/structure/hashes/tests/smoke/demo/CI-parse/doc-consistency/secrets/regen all PASS |
| `python scripts/scan_secrets.py --strict` | PASS | 0 | — | 0 findings | — | one test-fixture credential shortened to stay under the generic_assignment threshold |
| `docker build` / `docker compose config` | **NOT VERIFIED** | — | — | — | — | docker CLI unavailable in audit env; compose YAML validated; modes documented |
| tracked run records after 15+ runs | UNCHANGED | — | — | — | — | v2 ids: zero churn (baseline: every run rewrote committed records) |

## Failure-injection coverage added by the audit

- judge transport doubles: timeout, 429, 500, non-JSON, fenced JSON, not-an-object,
  string-'false', out-of-range, contradiction, missing score/rationale,
  non-numeric confidence, non-list items, SecurityViolation-under-guard
- persist crash mid-write (sentinel record must survive)
- concurrent POST /api/run (never overlaps)
- stored-XSS payload record (rendered inert)
- oversized declared body (413 before reading)
- read-only runs dir (503, explicit message)
- invalid CLI inputs (benchmark/skill/limit; 400s)
- permissions-block benchmark (previously crashed)
- cross-benchmark/dataset/selection/evaluator gate comparisons (rejected)
- min_cases boundary (exact/at/below/zero; both pass_on_insufficient policies)
- network guard: agent blocked / evaluator window allowed / fileno accept
- no-rich CLI paths (unit + subprocess with simulated rich absence)

## Test isolation

- web tests serve from throwaway tmp dirs (previously wrote into the shared
  `evals/runs`); pytest bridge uses mkdtemp; live-judge tests use mocked
  transports or a local HTTP double (no paid services, no network);
  sandbox tests pre-establish connections outside the guard window.
