# Portfolio Write-Up — agent-eval-harness

The FDE field guide's presentation contract
(`portfolio/03-presenting-projects.md`) prescribes eight sections, in this
order. This write-up follows it literally. The guide also says hiring
managers spend minutes, not hours — so: **the one-paragraph version is in
the README's first screen; the two-minute version is `make demo`; the
ninety-second spoken version is [90-SECOND-STORY.md](90-SECOND-STORY.md).
Everything below is the depth behind those.**

---

## 1. Problem

The brief as it arrived (fictional composite customer, verbatim, frozen
before any spec work — see
[00-ENGAGEMENT-BRIEF.md](00-ENGAGEMENT-BRIEF.md)):

> "three teams shipped AI agents in the last two quarters. the demos all
> looked great... last month somebody tweaked a prompt and the
> billing-triage agent got worse — *quietly*. we found out from a support
> volume spike NINE DAYS later... we need to know the moment they stop
> working. before our customers tell us. and whatever you build — ops has to
> actually run it. they will not learn a new tool."

Rejected problem statements (visible on purpose — the guide wants "a problem
statement that starts vague and ends specific, with the rejected versions
visible"):

- ~~"Build an agent evaluation framework"~~ — a solution wearing a problem's
  clothes; nobody asked for a framework, they asked for a moment.
- ~~"LLM-as-judge platform"~~ — one technique, not the problem; the customer
  explicitly distrusted model-scored quality.
- ~~"Agent observability"~~ — dashboards were rejected by the constraint
  ("nobody opens dashboards after week two").
- **Final: "Detect agent quality regressions at merge time, in CI, with
  failure localization good enough to act on — using tools the customer's
  teams already open."**

## 2. Constraints discovered

The ones we did not choose (the guide's definition):

- **No egress in CI** (finance policy) → evaluation must run fully offline;
  live LLM calls are a separate opt-in path.
- **2-core runners, 10-minute budget** → pure-Python, dependency-minimal
  (one runtime dep), sub-second full runs.
- **"Ops will not learn a new tool"** → pytest-native, `make`-first, exit
  codes as machine interface, Markdown reports in the CI viewer.
- **No chain-of-thought storage** (privacy counsel) → action-layer traces
  only, as a documented commitment.
- **Three agent stacks, none owned by us** → adapter protocol at the
  boundary; frameworks are optional dependencies.
- **Judge trust deficit** (a prior "the model says it's fine" burn) → no
  judge verdict gates anything until κ ≥ 0.6 is measured against hand
  labels.

## 3. What you built

In the operator's vocabulary (the guide: "named in the operator's vocabulary
rather than the vendor's"): **a CI gate for AI agents.** Three teams ship
agents; this platform runs each against 280 frozen, hash-pinned golden
cases; scores outcomes *and* behavior; compares against committed baselines;
fails the merge when quality drops beyond the team's own threshold; and
tells you whether to blame the agent, the evaluator, or the infrastructure.

```
Agent → Adapter → Harness (tool gateway: permissions · retry · verification ·
       sandbox · resource caps) → Benchmark Runner → Trajectory capture
       → Evaluators (10 deterministic · 6 trajectory/behavioral · 4 judge
       criteria, κ-calibrated) → Metrics (Wilson CI · p50/p95 · cost)
       → Baselines → Regression Gates (fail closed) → Reports (3-bucket)
       → CLI (13 commands) · Web Dashboard (`agent-eval serve`) · pytest bridge · CI · `make demo`
```

Components: 16-package Python library (stdlib-first), 5 deterministic
reference agents (ReAct / Plan-and-Execute / Supervisor / Swarm /
Map-Reduce), 3 framework adapters (LangGraph / OpenAI Agents SDK / CrewAI),
20 evaluators, regression engine with exact McNemar comparison, 132 tests,
zero-dependency Web Dashboard, and production Docker containerization.

## 4. Decisions and trade-offs

The guide calls this the section that matters most — "the reason the
second-best option lost is what proves an engineer was present." Five here;
all 13 in [DECISIONS.md](../../DECISIONS.md):

1. **Deterministic backend for all measured numbers** — rejected silent
   live-LLM fallback; cost: no live latency/cost/κ figures in this build,
   everything live is labeled *Not measured yet*.
2. **Gates fail closed on insufficient data** — rejected pass-open; cost:
   occasional false blocks on tiny runs, correctness in exactly the small-
   diff cases where regressions hide.
3. **No dashboard** — rejected a web UI (ops: "dead on arrival"); cost: no
   visual trending; the weekly view is one CLI command.
4. **Adapter protocol, not framework instrumentation** — rejected deep
   per-framework hooks; cost: boundary visibility only, framework internals
   invisible.
5. **κ ≥ 0.6 before any judge verdict gates CI** — rejected
   judge-out-of-the-box; cost: a calibration experiment and hand labels
   before value — which then caught our own rubric v1.0 scoring κ = 0.082
   (INC-4) before it could gate anything.

## 5. Evaluation

The guide's rule: dataset size and provenance, metrics, thresholds, and the
failures you could not fix.

- **Golden set:** 280 machine-verified cases (5 patterns × 56), six
  categories each (normal / difficult / ambiguous / edge / adversarial /
  failure-inducing), generated from pinned seeds, sha256-verified,
  byte-identical regeneration. Provenance: generated + machine-verified, not
  hand-curated — honestly weaker than customer-traffic-sourced cases, and
  labeled as such.
- **Headline numbers** (deterministic backend, seed 20260912, Wilson 95% CI):

| Benchmark | Pass rate | 95% CI |
|---|---|---|
| react_basic | 89.3% (50/56) | [78.5%, 95.0%] |
| swarm_basic | 82.1% (46/56) | [70.2%, 90.0%] |
| supervisor_basic | 80.4% (45/56) | [68.2%, 88.7%] |
| map_reduce_basic | 76.8% (43/56) | [64.2%, 85.9%] |
| plan_execute_basic | 73.2% (41/56) | [60.4%, 83.0%] |

- **Thresholds:** per-benchmark, in a reviewable committed file
  (`configs/gates.yaml`); default max drop −3pp pass-rate; fail-closed under
  10 cases.
- **The failures we did not fix, stated plainly:** plan-and-execute is the
  weakest pattern (73.2%) — multi-step planning amplifies backend errors;
  not fixed, documented and tracked. Live-LLM judge κ, live latency, live
  cost: *Not measured yet* (interfaces implemented, honestly labeled).
  Judge κ = 1.000 is the deterministic rubric backend on n=56 hand-labeled
  cases — always reported with the backend label and the κ = 0.082 it
  replaced.
- **Ablation (what the harness itself earns):** removing retry costs
  −12.5pp pass-rate on weak agents; removing verification −6.2pp; removing
  tool validation doubles loop rate. The harness is measured, not assumed.

## 6. Deployment and operations

- **Where it runs:** GitHub Actions, as a **blocking** eval-gate job
  (`.github/workflows/eval-gate.yml`) and dual-OS matrix (Ubuntu + Windows across Python 3.11/3.12);
  runnable anywhere Python 3.11+ runs, in Docker containers (`docker compose up dashboard`), or from a clean clone.
- **How it's monitored:** every run writes a deterministic run record +
  JSONL event log; `agent-eval status` is the Monday one-glance view
  (latest run per benchmark, drift vs baseline, dataset hashes, judge
  calibration) and exits non-zero on regression so cron does the watching;
  `agent-eval serve` provides an interactive browser UI for visual PR audits.
- **What an incident looks like:** the gate fails a PR with a table (metric,
  baseline, new, delta, threshold, verdict) + flipped-case list + McNemar p.
  `make demo` performs a full incident live: inject a −26.8pp regression,
  gate fails with exit 1, compare localizes it — 1.3 seconds, on purpose.
- **Who gets paged:** merge-blocked developers in CI; nightly regressions →
  agent-owner + platform channel (per the requirements spec).
- **Runbook:** [RUNBOOK.md](../../RUNBOOK.md) — daily/weekly cadence, alarm-
  by-alarm procedures, sharp edges — and its command sequence is executed by
  the clean-room release validator on every release, so it cannot rot.
- **Incident log:** [INCIDENTS.md](../../INCIDENTS.md) — 10 real incidents,
  including Windows UTF-8 console encoding and cross-platform CRLF line ending fixes.

## 7. Outcomes

Defined in writing before the build
([03-ACCEPTANCE-CRITERIA.md](03-ACCEPTANCE-CRITERIA.md)), reported after —
the guide's rule, not our habit:

- **Regression detection latency: 9 days → under 60 seconds at merge time.**
  The injected regression in the demo is caught in 0.3 s by the gate; the
  full incident arc (two full runs + gate + diagnosis) is 1.3 s.
- **A silently-regressed agent now blocks its own merge** (exit 1; 6 of 7
  gated metrics flagged on the injected regression; McNemar p = 6.1e-05).
- **Failure localization is one command:** 3-bucket taxonomy + flipped cases
  (18 TEST FAILURE / 0 EVALUATOR ERROR / 0 INFRASTRUCTURE FAILURE in the
  demo — "blame the agent change, not the harness").
- **Signal trustworthiness:** 280 cases, Wilson CIs, κ-calibrated judge
  (1.000 vs 0.6 bar, n=56), same-seed repro 0.0pp / byte-identical.
- **Cost:** $0.00 actual per CI run (deterministic); ~$0.03/day modeled at
  24 runs/day — labeled simulated pricing, in budget-owner units.
- **Ops adoption burden: zero new tools** (`make`, pytest, exit codes).

## 8. What I would do differently

Specific and technical, per the guide's ban on "I would plan better":

1. **Hand-label more calibration samples before writing any rubric.** The
   κ = 0.082 incident (INC-4) came from a rubric written against my own
   intuitions; 56 labels was the floor, not a comfortable margin. I would
   label ~150 and stratify by category before rubric v1 exists.
2. **Make run ids include a sequence salt for *display* runs while keeping
   content-hash ids for *canonical* runs.** The determinism guarantee and
   the "new file per run" operational expectation collided twice (INC-8,
   runbook sharp edge #4); a two-tier id scheme would have avoided both
   without weakening byte-identical reproducibility.
3. **Start the clean-room validator on day one, not at release.** INC-7
   (plugin missing from clean clones) existed for the entire build and was
   only caught when the zip was validated. The validator that found it
   should have been the second thing written, after the skeleton.
4. **Emit OTLP-shaped events even without a trace backend.** The
   no-trace-vendor decision (D-07 scope cut) was right for the customer, but
   serializing to the OTel-compatible shape from the start would make the
   future integration a config change instead of a refactor.
5. **Buy the latency p95 budget explicitly in the spec.** We record p50/p95
   per case, but the *suite* wall-time budget got all the negotiation
   attention; the per-case tail budget (where cold-starts live, per the
   guide) was implicit. Cheap to have written down; expensive to retrofit.

---

*Depth artifacts, per the guide's five signals: rejected problem statements
(§1) · decision records ([DECISIONS.md](../../DECISIONS.md), 13 ADRs) ·
evaluation table with dataset size, thresholds, and unfixed failures (§5) ·
incident log ([INCIDENTS.md](../../INCIDENTS.md), 10 real incidents) ·
runbook executed by another process ([RUNBOOK.md](../../RUNBOOK.md) +
clean-room validator). The repo links back: README → this file; this file →
every artifact it claims.*
