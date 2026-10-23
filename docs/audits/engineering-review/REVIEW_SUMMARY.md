# Review Change Summary — 18 commits, one per fix

Every commit was verified (tests + relevant CLI replay) before its individual
push. Range: `f20f36e..d09b3a0` on main.

| # | Commit | Change | Reason | Behavioral impact | Tests added |
|---|---|---|---|---|---|
| 1 | f20f36e | Makefile recipes 8-space → TAB (32 lines) | every `make` invocation aborted (missing separator); all documented make workflows broken | make targets now run | — (make -n matrix) |
| 2 | 2abbca0 | Makefile `gate` explicit run id | `ls -t` mtime guess could gate the wrong artifact | deterministic gating | — (replayed) |
| 3 | 03385b6 | eval-gate.yml explicit run id + benchmark assert | gated failure_recovery vs react_basic baseline (invalid) | gates the react run it means to gate | — (replayed) |
| 4 | a0debf4 | ids v2 preimage (+case selection, +model identity); `_command_str` --limit | distinct experiments overwrote each other's records (P0) | new ids; old records safe; identical experiments still collide by design (reproducibility) | 9 |
| 5 | ace6483 | regression compatibility checks; save_baseline carries selection digest | gate accepted incomparable evidence | incompatible ⇒ fail closed with incompatible_* findings | 8 |
| 6 | f86ae4b | min_cases_for_gate 4-level resolution + gates.yaml docs | operator value ignored (level mismatch) | honors shipped config; zero-case insufficient; boundary exact | 6 |
| 7 | 7a76150 | LiveJudge response contract + recorded fallback policy; run-level judge_fallbacks; report section | `passed:'false'` false-passed cases; silent clamping; contradictions | invalid responses degrade to rubric, visible; never evaluator errors | 18 |
| 8 | ad4abdb | sandbox v0.2 boundary: guard.allowed() evaluator window; fileno-wrap allowance; SecurityViolation caught by LiveJudge; THREAT-MODEL Egress row | live judge impossible under sandbox; accept loops crashed | authorized judge traffic during runs; agents still blocked | 4 |
| 9 | 680133b | atomic persist (record+events) via tmp+os.replace; dashboard execute lock; web fixture isolation | partial reads/clobber; unserialized executions | crash-safe artifacts; serialized POST /api/run | 3 |
| 10 | d46d65e | dashboard: read-only viewer 503; 4xx validation; 413 body cap; esc()+data-run-id (XSS); no ACAO:*; nosniff; compose/README modes | opaque 500 on ro mount; stored XSS; CORS *; unbounded bodies; limit=0 silent full-run | explicit deployment modes | 7 |
| 11 | 9c6f850 | CLI `_err`/`_out` rich-less helpers on all diagnostic paths | AssertionError crashes on minimal install | controlled exits everywhere | 3 |
| 12 | 0648095 | PermissionPolicy.from_dict fix; secure defaults preserved; max_denials honored | permissions feature crashed (AttributeError) | benchmark permissions usable end-to-end | 2 |
| 13 | 6ed71f3 | core/paths.py; AEH_RUNS_DIR/AEH_BASELINES_DIR wired (CLI/runner/experiments/regression/web) | Dockerfile-declared env read nowhere | container-configurable storage; defaults unchanged | 4 |
| 14 | 33e0d21 | ruff format applied (68 files) | 83 files failed format check (hidden by CI) | mechanical only | — |
| 15 | d8bd5df | all 15 mypy errors fixed with real corrections | mypy failed (hidden by CI) | stronger typing; ToolSpec.handler now required | — (existing suite) |
| 16 | 2a2c368 | ci.yml checks blocking (ruff/format/mypy); Makefile type blocking | quality failures invisible behind `\|\| true` | CI enforces quality | — (commands green) |
| 17 | 7a23606 | removed stale duplicates (source/ 67 files, infra/.github, root MANIFEST); evaluators/ reviewer copies refreshed | drifting twins misled audits (old buggy judge readable) | canonical paths only | — (references checked) |
| 18 | d09b3a0 | docs consistency: README 215 tests; RELEASE_NOTES command; final-report addendum; CHANGELOG; DECISIONS D11–D13 | docs disagreed with verified behavior | claims = verified state | — |

Compatibility impact summary:
- **Run ids change** (v2) — historical records/baselines keep their ids and are
  never overwritten by re-runs; `agent-eval <cmd> <old-id>` still resolves.
- **Gate behavior**: incompatible comparisons now fail (previously
  wrongly passed); insufficient-data policy unchanged (fail-closed).
- **Live judge**: stricter (invalid ⇒ deterministic fallback, recorded);
  valid responses unaffected.
- **Dashboard**: read-only deployments gain a 503 (previously an opaque 500);
  invalid inputs gain 4xx (previously 500s or silent full-runs).
- **Public APIs**: run_id signature extended (backward compatible defaults);
  ToolSpec.handler now required (fail-fast at construction); RunConfig.out_dir
  default via env; PermissionPolicy.from_dict accepts the documented keys.
