# Findings — per-finding record

Format: ID / Title / Severity / Status / Affected / Root cause / Reproduction /
Expected / Observed / Impact / Evidence / Fix / Tests / Validation / Residual risk.

---

**Finding ID:** F-01
**Title:** Run identity collisions — distinct experiments silently overwrite each other's artifacts
**Severity:** P0 (silent corruption of evaluation records)
**Status:** FIXED (commit `a0debf4`)
**Affected files/functions:** `core/ids.py:run_id`, `runner/runner.py:run/_persist`, `eval-gate.yml` smoke step, any `--limit` invocation
**Root cause:** v1 preimage covered (benchmark, agent, seed, ablation, dataset sha, skill) but NOT which cases ran (limit / category filters) nor the model configuration — two runs differing only in case selection mapped to the same id and filename.
**Reproduction steps:** `agent-eval run --benchmark react_basic` (56 cases, pass 0.8929) then `agent-eval run --benchmark react_basic --limit 8` — both produced id `f8a00acfe9f5dc43`; after the second run the record file held `cases: 8, pass: 1.0`. CI's smoke step (`--limit 8` for 5 benchmarks) triggered the overwrite on every push; tracked committed run records churned on every re-run.
**Expected behavior:** different experiment ⇒ different run id; artifacts never silently replaced.
**Observed behavior:** the 56-case experiment's record and event log were destroyed by an 8-case run.
**Impact:** silent data loss of evaluation evidence; baselines could be invalidated by an unrelated smoke run; `agent-eval status` reported misleading case counts mid-window.
**Evidence:** audit reproduction script output (baseline): "after limit-8 run, file f8a00acfe9f5dc43.json holds cases=8 pass=1.0000"; git churn on tracked `evals/runs/*.json`.
**Fix implemented:** preimage v2 adds `case_selection` (`n=<count>;sha=<digest12>` over selected case ids) and `model_identity` (`default` | `cfg:<hash12>`); recorded in run_start event + RunRecord.config; `_command_str` includes `--limit`. v2 ids never collide with v1 records (different preimage tag).
**Tests added:** `tests/unit/test_run_identity.py` (9): determinism, selection sensitivity, model-config sensitivity, the exact overwrite regression, reproducibility (same experiment ⇒ same id), command string.
**Validation result:** reproduction re-run against fixed code: full id `c732250d…` ≠ limit-8 id `19d9245…`; 56-case record intact. 15+ subsequent runs left tracked records untouched (git status clean).
**Residual risk:** identity is still a hash — deliberate collisions remain theoretically possible (sha256[:16], preimage-tagged; acceptable).

---

**Finding ID:** F-02
**Title:** Regression gate accepts incompatible baselines
**Severity:** P1 (gate trusts incomparable evidence)
**Status:** FIXED (commit `ace6483`)
**Affected:** `regression/engine.py:check_regression` (accepted any run vs any baseline); consumers: `agent-eval regression`, eval-gate workflow (via `ls -t`), Makefile gate.
**Root cause:** no identity checks before comparing numbers; `compare_runs` had a benchmark guard but the gate did not.
**Reproduction steps:** run failure_recovery (16 cases, 0.875), `agent-eval regression <id> --baseline main` (react_basic baseline 0.8929, 56 cases).
**Expected:** rejection — the samples are incomparable.
**Observed:** GATE PASSED with per-metric 'ok'/'improvement' findings. This was the exact comparison CI executed on every push (newest-mtime artifact = failure_recovery run).
**Impact:** a quality gate lent its credibility to invalid evidence; regressions in the actually-gated benchmark could be masked by another benchmark's numbers.
**Fix implemented:** `_compatibility_problems` verifies benchmark identity, dataset revision (sha), case selection (exact digest; count equality as legacy fallback), evaluator set — any problem ⇒ `GateDecision(passed=False)` with `incompatible_*` findings and a GATE INCOMPATIBLE summary; numeric findings are not emitted for incompatible pairs. `save_baseline` now persists the case-selection digest.
**Tests added:** 8 compatibility cases incl. the runner-level cross-benchmark reproduction and the legacy-baseline fallback.
**Validation result:** the reproduction now fails closed listing `incompatible_benchmark/selection/evaluators`; valid comparisons (demo path) still gate on real numbers (GATE PASS on equal evidence).
**Residual risk:** legacy baselines without digests are only count-checked (necessary, not sufficient); new baselines are exact.

---

**Finding ID:** F-03
**Title:** `min_cases_for_gate` read from the wrong configuration level
**Severity:** P1 (fail-closed policy not actually configurable)
**Status:** FIXED (commit `f86ae4b`)
**Affected:** `regression/engine.py:check_regression` (`cfg.get("min_cases_for_gate", 10)`), `configs/gates.yaml` (declares the value under `default:`).
**Root cause:** engine read only the top-level key; the shipped file documents the value under `default:` — the operator-facing level was silently ignored.
**Reproduction steps:** gates config with `default: min_cases_for_gate: 30`; run with 20 cases.
**Expected:** insufficient_data verdict; gate FAILS CLOSED (`pass_on_insufficient: false`).
**Observed:** verdict 'ok', gate PASSED — the hardcoded 10 always won.
**Fix implemented:** `_min_cases_for_gate` resolution: `benchmarks.<name>` > `default` > top-level (legacy) > 10; gates.yaml header documents the order; zero-case runs always insufficient; boundary (n == min) sufficient.
**Tests added:** 6 (default level, per-benchmark override, exact/below boundary, zero cases, legacy top-level, `pass_on_insufficient` both directions).
**Validation result:** reproduction now yields insufficient_data + passed=False.
**Residual risk:** none known.

---

**Finding ID:** F-04
**Title:** Live-judge responses accepted without validation
**Severity:** P1 (false PASS possible; evaluation integrity)
**Status:** FIXED (commit `7a76150`)
**Affected:** `evaluators/llm_judge/judge.py:LiveJudge.evaluate`.
**Root cause:** live path did `score = max(0, min(1, float(parsed.get("score", 0))))` and `passed = bool(parsed.get("passed", score >= 0.7))` — no contract enforcement; transport errors fell back (good) but schema violations were honored as verdicts.
**Reproduction steps (mocked transport, no network/cost):** judge returning `{"score": 0.9, "passed": "false"}` → case marked PASSED (`bool("false")` is truthy). Also: score 5.0 silently clamped to 1.0; score 0.2 + passed=true honored; missing score → passed=True with score 0.0; confidence='high' recorded verbatim.
**Expected:** malformed judge verdicts must never be accepted as evidence; degradation must be explicit and recorded.
**Fix implemented:** `_validated_live_payload` enforces the contract (JSON object; numeric non-bool score in [0,1]; passed boolean or 'true'/'false' string that must agree with score≥threshold; required string rationale; optional numeric confidence in [0,1]; optional list items). Any violation or transport failure (timeout/429/5xx/non-JSON/SecurityViolation) degrades that evaluation to the deterministic rubric with a recorded reason. Run-level visibility: `metrics.judge_fallbacks`, per-case `judge_fallback` events, report section. Fallback is NOT an evaluator error.
**Tests added:** 17 live-contract cases + 1 runner-level integration case (fallbacks counted, visible in record/events; deterministic evaluators unaffected).
**Validation result:** reproduction table re-run: every invalid response now falls back with a specific reason; valid responses still used as live backend.
**Residual risk:** a hijacked judge returning internally-consistent valid verdicts is indistinguishable at this layer (prompt-level risk; rubric fallback auditable; endpoint is operator-configured).

---

**Finding ID:** F-05
**Title:** Live judge incompatible with the network sandbox; global monkeypatch broke server accept
**Severity:** P1
**Status:** FIXED (commit `ad4abdb`)
**Affected:** `security/sandbox.py`, `runner/runner.py` (guard spanned evaluation), any in-process HTTP server during runs (dashboard).
**Root cause:** (a) the guard blocked ALL socket creation for the whole run including the evaluator phase where the trusted live judge needs authorized HTTP — SecurityViolation was not in LiveJudge's except list and escaped; (b) `socket.socket(fileno=...)` wraps (http.server accept) were blocked too, crashing accept loops.
**Reproduction steps:** with `AEH_JUDGE_BACKEND=live`, every judged case became EVALUATOR_ERROR; a server accepting a connection during a run raised SecurityViolation in its accept thread.
**Expected:** agent code blocked at every point; trusted judge able to reach its operator-configured endpoint; servers keep accepting.
**Fix implemented:** `NetworkGuard.allowed()` window — the runner lifts the block ONLY for the evaluator loop; `socket.socket(fileno=...)` wraps of existing fds allowed; SecurityViolation caught by LiveJudge (defense in depth); THREAT-MODEL Egress row documents the boundary.
**Tests added:** allowed-window semantics; attempts recording excludes authorized traffic; fileno-wrap accept with a pre-established connection; **the Issue D regression: a live judge served by a local HTTP double succeeds during a sandboxed run** (live scores in verdicts, zero fallbacks, judge traffic observed by the double).
**Validation result:** all green; dashboard + live-probe integrations stable.
**Residual risk:** during an evaluator window any in-process code could create sockets (documented; runs are single-threaded; dashboard serializes executions; container remains the real boundary).

---

**Finding ID:** F-06
**Title:** CI quality checks non-blocking while the repository had real failures
**Severity:** P1 (CI lied about quality)
**Status:** FIXED (commits `33e0d21`, `d8bd5df`, `2a2c368`)
**Affected:** `.github/workflows/ci.yml` (ruff/format/mypy `|| true`), `Makefile:type`.
**Root cause:** pass-through `|| true` on required checks; failures were invisible behind green status.
**Reproduction steps:** at baseline `ruff format --check src tests scripts` failed (42+ files in src alone; 83 total) and mypy reported 15 errors — while CI showed success.
**Fix implemented:** repo made legitimately clean (format applied; all 15 mypy errors fixed with real type corrections, not blanket ignores), then checks made blocking (ci.yml + Makefile). pip-audit stays advisory as an explicit commented decision (transitive advisories), not a silent pass-through.
**Validation result:** ruff check / format --check / mypy all clean and enforced; full suite green.
**Residual risk:** none for the required checks; advisory scans documented.

---

**Finding ID:** F-07
**Title:** CI/Makefile selected the gated run by newest mtime
**Severity:** P1 (wrong artifact gated)
**Status:** FIXED (commits `2abbca0`, `03385b6`); backstopped by F-02.
**Affected:** `eval-gate.yml` regression step, `Makefile:gate` (`ls -t evals/runs/*.json | head -1`).
**Root cause:** mtime ordering picked the newest artifact — the failure_recovery run — and gated it against the react_basic baseline.
**Fix implemented:** the full react_basic run is captured with `--json` into `$RUNNER_TEMP`; the gate step reads its run_id AND benchmark, asserts `benchmark == react_basic`, gates that exact id. Makefile equivalent via mktemp + `--json`.
**Validation result:** exact command sequence replayed locally: gates react_basic vs main, GATE PASS on real numbers.
**Residual risk:** none identified (selection is now deterministic and self-verifying).

---

**Finding ID:** F-08
**Title:** Entire Makefile non-functional (spaces instead of TABs)
**Severity:** P1 (all documented make workflows broken)
**Status:** FIXED (commit `f20f36e`)
**Affected:** `Makefile` (all 35 recipe lines).
**Root cause:** recipes indented with 8 spaces; GNU make requires TAB — `make <anything>` aborted with `missing separator`. README/QUICKSTART/RUNBOOK instruct `make demo/test/gate/...`.
**Reproduction steps:** `make -n install` → `Makefile:12: *** missing separator`.
**Fix implemented:** mechanical TAB conversion (32 recipe lines); `make -n` verified for all targets.
**Validation result:** `make demo` exit 0; `make gate` GATE PASS; `make validate-release` RELEASE VALIDATED.
**Residual risk:** none.

---

**Finding ID:** F-09
**Title:** Dashboard security/deployment defects (read-only mount, XSS, CORS, DoS, validation)
**Severity:** P1 (stored XSS with shared-volume precondition) / P2 (validation)
**Status:** FIXED (commit `d46d65e`)
**Affected:** `web/server.py` (`_handle_execute_run`, `_send_json`, INDEX_HTML rendering), `docker-compose.yml`, README Docker section.
**Root cause:** POST /api/run attempted writes on a read-only mount (opaque 500); run-record fields interpolated into innerHTML unescaped and inlined into onclick strings; `Access-Control-Allow-Origin: *`; no Content-Length cap; client errors surfaced as 500; `limit=0`/negatives silently meant a full run.
**Reproduction steps:** compose dashboard (ro mount) → Execute button → 500 OSError; crafted run record with markup in run_id/benchmark/category/final_answer → injected into the page; oversized declared body accepted.
**Fix implemented:** explicit deployment modes (read-only viewer refuses execution with 503 + message; authorized executor = runner service); strict input validation (4xx): JSON object body, benchmark via registry, skill ∈ [0,1], limit positive int or null; 1 MiB body cap → 413 refused before reading; same-origin default (no ACAO), nosniff; client `esc()` for every record field, Number() coercion, `encodeURIComponent`, event delegation with `data-run-id` (no inline onclick).
**Tests added:** 7 (invalid benchmark/skill/limit 400s, malformed/non-object JSON, 413, read-only 503 + writable path still executes, stored-XSS payload rendered inert).
**Validation result:** all web tests green; page ships `esc()` and zero `onclick=`.
**Residual risk:** dashboard is a single-operator ops tool (executions serialized); do not expose it to untrusted networks (documented).

---

**Finding ID:** F-10
**Title:** Run artifacts written in place; concurrent executions unserialized
**Severity:** P1
**Status:** FIXED (commit `680133b`)
**Affected:** `runner/runner.py:_persist` (wrote the record twice in place), `observability/events.py:export_jsonl`, `web/server.py` (POST /api/run).
**Root cause:** direct writes (partial-file window for readers; crash mid-write clobbers existing records); no mutual exclusion for POST /api/run (artifact interleaving + process-global guard contention).
**Fix implemented:** tmp + `os.replace` atomicity for record and events (POSIX+Windows); events exported before the single record write; `DashboardHandler._execute_lock` serializes executions.
**Tests added:** sentinel-record survives simulated serialization crash; no `.tmp` residue; concurrent double-POST never overlaps.
**Validation result:** green.
**Residual risk:** none identified for single-process deployments.

---

**Finding ID:** F-11
**Title:** CLI crashes without rich on error/warning paths
**Severity:** P2
**Status:** FIXED (commit `9c6f850`)
**Affected:** `cli/app.py:cmd_validate` (`assert ERR is not None`), `cmd_compare` (version drift), main() handlers.
**Root cause:** rich is optional (PyYAML is the only runtime dep) but paths assumed `ERR` initialized.
**Reproduction steps:** minimal install (no rich); `agent-eval validate --dataset <invalid>` → raw AssertionError traceback.
**Fix implemented:** `_err`/`_out` helpers (rich or plain with markup stripped) used by all diagnostic paths.
**Tests added:** 3 (unit monkeypatch, compare drift warning, subprocess with simulated rich absence).
**Validation result:** clean controlled INVALID output, exit 1; also verified in a clean venv (no rich) end-to-end.
**Residual risk:** none.

---

**Finding ID:** F-12
**Title:** `PermissionPolicy.from_dict` crashed for any permissions block
**Severity:** P2 (security-config feature unusable)
**Status:** FIXED (commit `0648095`)
**Affected:** `harness/controls.py:PermissionPolicy.from_dict`.
**Root cause:** referenced `cls.forbidden_arg_keys` — a class attribute that does not exist for `default_factory` dataclass fields.
**Reproduction steps:** `PermissionPolicy.from_dict({"allowed_tools": ["calculator"]})` → AttributeError; any benchmark YAML with `execution.permissions` crashed at runner construction.
**Fix implemented:** module-level `_DEFAULT_FORBIDDEN_ARG_KEYS`; absent keys keep secure defaults (never silently dropped); `max_denials_before_violation` now honored.
**Tests added:** 2 (defaults preserved with partial block; end-to-end benchmark with permissions + gateway enforcement).
**Validation result:** green.
**Residual risk:** none.

---

**Finding ID:** F-13
**Title:** Environment plumbing gaps (AEH_RUNS_DIR/AEH_BASELINES_DIR) — see F-14..F-16 in ENGINEERING_AUDIT numbering
**Severity:** P3
**Status:** FIXED (commit `6ed71f3`) — `core/paths.py` single source of truth honored by CLI/runner/experiments/regression/web at call time; container behavior now matches the Dockerfile declaration. 4 tests.
**Residual risk:** none.

*F-14 (stale duplicate trees) and F-15/F-16 (docs drift) are recorded in ENGINEERING_AUDIT.md §3; both FIXED (commits `7a23606`, `d09b3a0`).*
