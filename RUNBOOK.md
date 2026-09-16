# RUNBOOK — Operating agent-eval-harness After Handover

**Audience:** the engineer who inherits this system when its author is gone.
**Promise:** everything you need to run it daily is on this page; everything
you need to debug it is one link away. **Test:** this exact command sequence
is executed by the clean-room release validator (`python
scripts/validate_release.py`) on every release — so the runbook cannot silently
rot. That is the field guide's bar: *"a runbook that someone other than you
has actually executed."*

If you are reading this fresh: start with `make demo` (90 seconds, shows the
gate catching an injected regression), then `make status`, then come back.

---

## 1. What this system is (operator's vocabulary)

A **CI gate for AI agents**. Three teams ship agents; this platform runs each
agent against a frozen set of golden cases (280 of them, hash-pinned), scores
the outcome *and* the behavior, compares against committed baselines, and
fails the merge when quality drops more than the team's own threshold says.
It is "pytest, but the unit under test is an entire agent."

- **Run** = one benchmark × one agent × one seed → a run record (JSON) + event
  log (JSONL) in `evals/runs/`.
- **Baseline** = a named, blessed run record in `evals/baselines/` (currently
  `main`, react_basic).
- **Gate** = the comparison of a new run vs a baseline against
  `configs/gates.yaml` thresholds; exit 1 = regression.
- **Status** = your Monday command: latest run per benchmark, drift vs
  baseline, dataset hashes, judge calibration.

## 2. The daily/weekly rhythm

| When | Who | Command | Expected |
|---|---|---|---|
| Every merge (CI) | GitHub Actions | `make test-smoke && make gate` | exit 0 |
| Nightly (CI) | GitHub Actions | `make eval-full && make gate` + full suite | exit 0 |
| Monday | ops | `make status` | exit 0; anything else → §4 |
| Visual audit / PR triage | team lead | `make serve` (or `agent-eval serve`) | browser UI at `http://127.0.0.1:8000` |
| Containerized run | devops / CI | `docker compose up dashboard` (or `make docker-run`) | containerized runner & UI |
| On incident | on-call | `make demo` (re-fires the path you're about to debug) | 1.3 s |
| After dataset change | agent lead | `make validate` | `VALID: all benchmarks` |
| Quarterly | platform | `make experiments` → review `docs/final-report.md` deltas | all metrics within gates |

## 3. Healthy numbers (what "good" looks like)

Benchmarks on the deterministic backend, seed 20260912, skill 0.85
(reproduce: `agent-eval run --benchmark <name>`):

| Benchmark | Pass rate | 95% CI |
|---|---|---|
| react_basic | 89.3% (50/56) | [78.5%, 95.0%] |
| supervisor_basic | 80.4% (45/56) | [68.2%, 88.7%] |
| swarm_basic | 82.1% (46/56) | [70.2%, 90.0%] |
| map_reduce_basic | 76.8% (43/56) | [64.2%, 85.9%] |
| plan_execute_basic | 73.2% (41/56) | [60.4%, 83.0%] — *the weak one; known, not hidden* |

Judge calibration: κ = 1.000 (rubric v1.1, n=56). Same-seed repro: 0.0pp.
Drift beyond ±2pp on the *same* seed+skill is not noise — investigate.

## 4. What to do when each alarm fires

### CI gate fails on a PR (`make gate` exit 1)

1. Read the failure table: which metric, which delta, which threshold.
   Six-metric failures on a small PR usually mean a real regression, not a
   flaky judge (judges are calibrated; see §3).
2. `agent-eval compare <baseline_run> <new_run>` — the flipped-case list is
   your bisect starting point. `McNemar p < 0.05` means the drop is real,
   not noise.
3. If cases flipped in `adversarial`/`ambiguous` categories first: suspect
   prompt changes that traded robustness for happy-path quality.
4. Do **not** "fix" this by loosening `configs/gates.yaml` in the same PR —
   that file is the agreement; threshold changes go through the owning team's
   review, alone, with a justification comment.

### Nightly regression but PRs were green

1. `make status` → find the benchmark with `REGRESSION` verdict.
2. Same-seed rerun: `agent-eval run --benchmark <bm>` and compare. Same
   result → real. Different result → you have a determinism bug; file it as
   INFRASTRUCTURE (see `INCIDENTS.md` #2 for how process-salted seeds did
   exactly this once).
3. Check dataset hashes in status output vs git — a regenerated dataset with
   a different hash invalidates baselines (by design).

### `agent-eval status` exits 1

The `REGRESSION` row names the benchmark; run
`agent-eval regression <run_id> --baseline main` for the full gate table.
If the delta is −1pp to −3pp (`watch`), do nothing dramatic: note it, watch
the next run. −3pp and beyond is the alarm.

### Dataset validation fails (`make validate`)

The generator or the golden files drifted. Never hand-edit
`datasets/*/golden.jsonl` — regenerate with
`python scripts/generate_datasets.py` and review the diff; the files are
supposed to be reproducible byte-for-byte. If they are not, that is a bug
(see `INCIDENTS.md` #2).

### Judge kappa degrades (quarterly `make calibrate`)

κ < 0.6 means judge verdicts must stop gating. The rubric version and prompt
version are recorded per run; a κ drop after a prompt-version bump is a
prompt regression — revert the bump (prompt files are versioned in
`prompts/`). A κ drop with no version change means the cases drifted out of
distribution — that is the signal to refresh hand labels.

### CI eval stage exceeds its 10-minute budget

The deterministic backend runs in seconds; if the stage is slow, something
is calling the network (it shouldn't — the tool env is sandboxed) or the
case count grew. Check `network_guard_attempts` in the run record first;
then `agent-eval list datasets` for case-count growth.

## 5. Sharp edges (known, documented, not hidden)

1. **Live-LLM measurements are Not measured yet.** Latency p95 (0.217 ms),
   cost ($0.0012/run), and judge κ are deterministic-backend numbers with
   simulated pricing. The live client exists; nobody has run it with real
   keys. Do not quote these numbers as production LLM figures.
2. **One baseline at a time.** `evals/baselines/main.json` covers
   `react_basic` only; other benchmarks gate on their own threshold tables
   (`configs/gates.yaml`) but have no named baseline run yet. Creating one:
   `agent-eval run --benchmark <bm> --baseline main2`.
3. **plan_execute_basic is the weakest pattern (73.2%)** — multi-step plans
   amplify the scripted backend's errors. Improving it is roadmap work, not
   an incident.
4. **Run ids are deterministic** — the same benchmark+seed+skill rewrites the
   same run record. If you need to keep a run, copy it out of
   `evals/runs/` or vary the seed. (This bit the demo script once:
   `INCIDENTS.md` #8.)
5. **Gates fail closed.** Under 10 gated cases, a "can't tell" becomes a
   FAIL. That is a design decision (`DECISIONS.md` D-05), not a bug; it has
   costs on tiny sample runs.
6. **No CoT anywhere** — by privacy policy. If you "just add" reasoning
   capture to traces, you are violating the engagement's written constraint,
   not improving observability.
7. **Windows console encoding** — terminals default to `cp1252`; `agent-eval`
   automatically reconfigures stdout to UTF-8 (`INCIDENTS.md` #9). If calling via custom
   scripts or subprocesses, ensure `PYTHONIOENCODING="utf-8"` is set.
8. **CRLF vs dataset hashes** — golden dataset integrity check asserts strict
   SHA-256 signatures (`INCIDENTS.md` #10). The repo enforces LF via `.gitattributes`
   and performs byte-level newline normalization during verification.

## 6. Where things live

| Thing | Path |
|---|---|
| Golden datasets (hash-pinned) | `datasets/<pattern>/golden.jsonl` |
| Benchmark registry (YAML) | `benchmarks/*.yaml` |
| Gate thresholds (the agreement) | `configs/gates.yaml` |
| Run records + event logs | `evals/runs/<run_id>.{json,events.jsonl}` |
| Baselines | `evals/baselines/` |
| Web Dashboard (zero-dep HTTP server) | `src/agent_eval_harness/web/` (`agent-eval serve`) |
| Container configuration | `Dockerfile`, `docker-compose.yml`, `.dockerignore` |
| Experiment results (all measured numbers) | `evals/results/experiments.json` |
| Hand labels (judge calibration) | `evals/calibration/` |
| Judge prompts (versioned) | `prompts/` |
| Decision records | `DECISIONS.md` |
| Incident log | `INCIDENTS.md` |
| All measured results + honesty annex | `docs/final-report.md` |
| Engagement record (brief→discovery→spec→bar) | `docs/fde/` |

## 7. Escalation

1. Anything in §4 you cannot resolve in 30 minutes → open an issue titled
   `[runbook §4.x] ...` so the runbook section gets fixed with the fix.
2. Determinism bugs (same input, different output) are **severity-1** — the
   entire gate's authority rests on determinism. See `INCIDENTS.md` #2 for
   the precedent.
3. Security-relevant findings (secrets in artifacts, sandbox escapes) →
   `SECURITY.md` escalation path, not a public issue.

*This runbook is itself versioned; if operating reality diverges from this
page, the page loses — update it in the same commit as the fix.*
