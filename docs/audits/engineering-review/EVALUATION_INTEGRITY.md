# Evaluation Integrity

## 1. Benchmark validity (verified by execution)

- 7 benchmarks over 5 hash-pinned golden datasets (280 cases, 5×56; category
  distribution identical across patterns; unique ids; regeneration
  byte-identical — validated in the clean room, 5/5 hashes equal).
- All 7 measured in this audit session; pass rates reproduce the committed
  table exactly: react 89.3%, plan_execute 73.2%, supervisor 80.4%,
  swarm 82.1%, map_reduce 76.8% (each 95% Wilson CI in the README);
  failure_recovery 87.5% (16 cases), adversarial 100% (6 cases).
- Ablation at skill 0.60 reproduces the README attribution: removing retry
  costs −12.5pp with recovery 83%→50%; removing verification −6.2pp.
- Same-seed repro ×5: spread 0.0pp, records byte-identical (excluding
  wall-clock fields by design; the semantic projection is what is compared).

## 2. Deterministic vs live evaluation — clearly separated

- Every run record carries `versions.model = scripted-policy-v1 (deterministic
  simulation)`; reports label latency/cost as deterministic-backend estimates
  (`cost_note`), never as live measurements.
- The rubric judge is the measured backend (κ vs hand labels). The live
  backend is contract-tested via local doubles only; its reliability/latency/
  cost remain *Not measured yet* — stated, not implied.
- Judge results now carry backend + model + prompt version + prompt sha +
  fallback status per result (auditability contract).

## 3. Judge calibration — honest reading

- κ = 1.0 vs 56 hand labels, single annotator, labeled as such
  (`limitation: single annotator`); the calibration pipeline reports it.
  This is agreement on ONE deterministic rubric against ONE annotator on ONE
  dataset — it does NOT certify live-judge reliability (stated in reports).
  κ target 0.6; v1.0 rubric was rejected at κ 0.082 (INC-4) — the calibration
  loop demonstrably rejects bad rubrics.

## 4. Gate correctness (after this audit)

- Gates verify comparability BEFORE numbers: benchmark identity, dataset
  revision, case selection (exact digest; count fallback for legacy
  baselines), evaluator set — incompatible ⇒ fail closed, visibly
  (`incompatible_*` findings; no misleading deltas).
- Sufficiency: `min_cases_for_gate` honored from the shipped config level;
  n == minimum is sufficient, below is `insufficient_data`;
  `pass_on_insufficient: false` (shipped) ⇒ FAILS CLOSED in CI; the policy
  flag is honored in both directions and tested.
- Thresholds are MAXIMUM ALLOWED DROPS (negative); delta exactly at threshold
  is within (boundary tested).
- Healthy runs pass applicable gates (verified: GATE PASS on comparable
  evidence); injected regressions fail (verified: `make demo` — −26.8pp-class
  regression → GATE FAIL in the clean room).

## 5. Failure taxonomy separation (verified)

TEST FAILURE / EVALUATOR ERROR / INFRASTRUCTURE FAILURE remain separated at
the schema level; evaluator exceptions can never mark a case as an agent
failure (precedence enforced in the runner); live-judge fallback is
explicitly NOT an evaluator error — it is a recorded deterministic
degradation (`metrics.judge_fallbacks` + per-case events + report section).
Adversarial injection cases measure agent resistance; they cannot alter
harness scoring (gateway denials audit-logged).

## 6. Statistical checks (independently exercised)

- Wilson intervals: zero-denominator and known-value tests; per-group CIs
  reported with n (never bare percentages without n).
- Exact McNemar (two-sided): no-discordant-pairs case returns p=1.0;
  significance flag at α=0.05; comparisons require the same benchmark
  (ValueError otherwise) and warn on version drift.
- Cohen's κ: degenerate-case handling (pe≥1) tested; single-annotator
  limitation reported.
- Token/cost figures labeled `est` with the pricing note; never presented as
  live measurements.

## 7. Reproducibility

- Run identity v2: same experiment ⇒ same id (verified); different experiment
  (selection/model config) ⇒ different id (verified) — the artifact-overwrite
  failure mode is closed.
- Datasets regenerate byte-identically (clean-room step 9); CRLF normalized
  before hashing.
- Tracked run records no longer churn on re-runs (verified after 15+ runs).

## 8. Self-review (independent judge pass over this audit's own changes)

Rubric (weights): functional correctness 20%, test reliability/completeness
15%, evaluation & statistical integrity 20%, security 15%, architecture &
maintainability 10%, CI/CD & deployment 10%, documentation & operability 5%,
performance & resource efficiency 5%.

| Dimension | Score | Evidence |
|---|---|---|
| Functional correctness | 4.5 | 215 tests; every fix reproduced-before/fixed-after; determinism preserved (byte-identical repro) |
| Test reliability & completeness | 4.0 | 63 new regression tests incl. negative/failure-injection; isolation hardened; coverage of every fixed defect |
| Evaluation & statistical integrity | 4.0 | gates verify comparability + sufficiency; fallback policy explicit; κ honestly labeled; live measurements still not possible (env) |
| Security | 4.0 | F-05/F-09 fixed with tests; THREAT-MODEL updated; residual risks documented; Docker runtime not verifiable here |
| Architecture & maintainability | 3.5 | v2 identity + paths module + duplicate-tree removal reduce drift; no rewrites; single-boundary change documented (D11–D13) |
| CI/CD & deployment reliability | 3.5 | checks blocking and green; clean-room release validated; Actions runs not directly observable from this environment |
| Documentation & operability | 4.0 | README/CHANGELOG/DECISIONS/RUNBOOK consistency restored; dated addendum; audit trail committed |
| Performance & resource efficiency | 3.5 | atomic writes; serialized executions; O(n) unchanged; no regressions introduced |

**Weighted total: 4.0/5 → 80/100.**

Verdict: **CONDITIONAL PASS.** No known unresolved P0/P1 defects; the
conditions are (a) live-backend judge measurements remain *Not measured yet*
(environment), (b) Docker runtime NOT VERIFIED here, (c) GitHub Actions
outcomes not directly observed (commands replayed locally green). None of
these is silently claimed as verified.
