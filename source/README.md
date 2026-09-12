# agent-eval-harness

**A CI gate for AI agents.** Three teams ship agents on LangGraph, OpenAI
Agents SDK, CrewAI, or plain Python; this platform runs each one against
280 hash-pinned golden cases, scores outcomes **and** observable behavior,
and **fails the merge** when quality drops past the team's own committed
thresholds — with failure localization good enough to act on (TEST FAILURE
vs EVALUATOR ERROR vs INFRASTRUCTURE FAILURE). It is "pytest, but the unit
under test is an entire agent."

Built and rebuilt the FDE way — the full engagement record (vague customer
brief → discovery → spec → acceptance bar → measured outcomes) is in
[`docs/fde/`](docs/fde/); the presentation write-up is
[`docs/fde/WRITE-UP.md`](docs/fde/WRITE-UP.md).

```
Agent → Adapter → Harness → Benchmark Runner → Trajectory Capture → Evaluators
  (deterministic + κ-calibrated LLM-judge + trajectory/behavioral) → Metrics
  → Baselines → Regression Gates (fail closed) → Reports → CLI / pytest / CI
```

**See it work in 90 seconds — including a deliberately injected regression
that the gate catches live:**

```bash
make demo
```

## Why

Agent failures are rarely just "the model." This platform treats the complete
system — model + harness + tools + context + state + verification — as the
unit under test, localizes failures to a layer, and measures which harness
capabilities actually earn their complexity (ablation with real numbers).
The founding rule: **no fabricated results** — every number is measured by a
committed script or explicitly labeled *Not measured yet*.

## Quickstart (works from a clean clone, one command)

```bash
make validate                   # validate all benchmarks + datasets
agent-eval run --benchmark react_basic        # full run + report artifacts
make status                     # operator weekly health view (exit 1 on regression)
pytest -m agent_eval tests/e2e               # run benchmarks as pytest
```

Or with the pytest bridge in your own suite:

```python
# conftest.py
pytest_plugins = ["agent_eval_harness.pytest_plugin"]

def test_react(eval_case):
    assert eval_case("react_basic", limit=8, gate=True) >= 0.7
```

Single runtime dependency: PyYAML. Python ≥ 3.11. The raw tree tests green
even without `pip install`.

## CLI surface

```bash
agent-eval run --benchmark react_basic --agent builtin:react --skill 0.85
agent-eval status               # weekly one-glance: runs vs baseline, datasets, κ
agent-eval list benchmarks | evaluators | datasets
agent-eval validate [dataset|benchmark]
agent-eval compare RUN_A RUN_B            # per-case flips + exact McNemar p
agent-eval report RUN_ID [--format md|json]
agent-eval regression RUN_ID --baseline main     # CI gate: exit 1 on regression
agent-eval ablate --benchmark failure_recovery   # harness ablation study
agent-eval calibrate --labels evals/calibration/hand_labels.csv   # judge κ
agent-eval repro --benchmark react_basic --repeats 5
```

## What's measured (deterministic backend, seed 20260912)

| Benchmark | Pattern | Pass rate | 95% CI |
|---|---|---|---|
| react_basic | ReAct | 50/56 = 89.3% | [78.5%, 95.0%] |
| plan_execute_basic | Plan-and-Execute | 41/56 = 73.2% | [60.4%, 83.0%] |
| supervisor_basic | Supervisor | 45/56 = 80.4% | [68.2%, 88.7%] |
| swarm_basic | Swarm | 46/56 = 82.1% | [70.2%, 90.0%] |
| map_reduce_basic | Map-Reduce | 43/56 = 76.8% | [64.2%, 85.9%] |

Ablation attribution (failure_recovery, skill 0.60): removing harness retry
costs −12.5pp (recovery 100%→50%); removing verification −6.2pp; removing
tool validation doubles the loop rate. Judge calibration vs hand labels:
Cohen's κ = 1.0 (after rubric v1.1; v1.0 measured 0.082 and was rejected —
see `INCIDENTS.md` INC-4). Same-seed reproducibility: 0.0pp spread,
byte-identical run records. Regression demo: injected −26.8pp drop → gate
FAIL in 0.3s (`make demo`).

**Honesty note**: all benchmark scores above are measured on the deterministic
scripted backend (`scripted-policy-v1`) — a reproducible simulation with real
tool executions. Live-LLM measurements (latency, cost, judge reliability):
*Not measured yet* (interfaces implemented; see `docs/final-report.md`).

## Handover artifacts (operate this without its author)

- **[RUNBOOK.md](RUNBOOK.md)** — daily/weekly cadence, what to do when each
  alarm fires, sharp edges; its command sequence is executed by the
  clean-room release validator, so it cannot rot.
- **[INCIDENTS.md](INCIDENTS.md)** — 8 real incidents: symptom → diagnosis →
  fix → what changed.
- **[DECISIONS.md](DECISIONS.md)** — 10 decision records: the alternative,
  the reason, the accepted cost.

## Repository map

```
src/agent_eval_harness/   core/ agents/ harness/ runner/ evaluators/ metrics/
                          comparison/ regression/ reporting/ observability/
                          security/ registry/ cli/
benchmarks/               versioned YAML benchmark registry (7 benchmarks)
datasets/                 280 machine-verified golden cases (5 patterns × 56)
evals/                    runs/ baselines/ calibration/ results/
prompts/                  versioned judge prompts
configs/                  gates.yaml (regression thresholds), settings.yaml
tests/                    126 tests: unit/integration/e2e/security/failure-injection
docs/                     fde/ research/ concepts/ security/ career/ journal
docs/fde/                 the engagement record: brief → discovery → spec → bar
scripts/                  dataset generator, experiments, demo, release
.github/workflows/        ci.yml · eval-gate.yml (blocking) · security.yml
```

## Key guarantees

- **Deterministic**: same (agent, benchmark, seed, ablation, dataset) →
  byte-identical verdicts; datasets regenerate byte-identically (hash-verified).
- **No fabrication**: every number in docs is produced by
  `scripts/run_experiments.py`; anything unmeasured is labeled
  *Not measured yet*.
- **Failure localization**: TEST FAILURE / EVALUATOR ERROR / INFRASTRUCTURE
  FAILURE separated at the schema level in every report.
- **CI-grade gates**: `agent-eval regression` exits non-zero when quality drops
  beyond `configs/gates.yaml` thresholds — wired as a blocking GitHub Actions
  job; fails closed on insufficient data.

## Docs

- [QUICKSTART.md](QUICKSTART.md) — 10-minute path incl. custom agents
- [docs/fde/WRITE-UP.md](docs/fde/WRITE-UP.md) — portfolio write-up (the
  engagement in 8 sections) · [docs/fde/](docs/fde/) — full engagement record
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) + [diagrams/](diagrams/)
- [docs/final-report.md](docs/final-report.md) — all measured results
- [docs/engineering-journal.md](docs/engineering-journal.md) — build log
- [SECURITY.md](SECURITY.md) + [docs/security/THREAT-MODEL.md](docs/security/THREAT-MODEL.md)
- [docs/concepts/](docs/concepts/) — 13 concept docs (why/how/trade-offs/failure modes)

License: MIT. Python ≥ 3.11. Runtime deps: PyYAML.
