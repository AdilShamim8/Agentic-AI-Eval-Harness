# Discovery Notes — From Vague Ask to Spec

Companion to [00-ENGAGEMENT-BRIEF.md](00-ENGAGEMENT-BRIEF.md). This is the
record of how the ambiguity in the customer's email was resolved: the
questions asked, the assumptions killed, and the scope deliberately cut. The
FDE field guide's principle #1 says this before-and-after *is* the work —
"the code is downstream of it." Dates matter: discovery happened before a
line of platform code was written, and the acceptance criteria
([03-ACCEPTANCE-CRITERIA.md](03-ACCEPTANCE-CRITERIA.md)) were frozen before
the build.

## Interview log (condensed)

Three working sessions with the VP Eng, the three agent-team leads, one ops
representative, and privacy counsel. Condensed to the questions that changed
the spec.

### Session 1 — with VP Eng + ops representative

**Q: What does "stops working" actually mean? Nobody defined it.**
A (after discussion): three different failure shapes, all real to them —

1. *Outcome regression*: the agent completes but completes worse (the
   billing-triage incident — this one hurt them).
2. *Behavioral regression*: loops, wrong-tool usage, failure to terminate.
   Ops sees this as "the agent got weird."
3. *Hard failure*: exceptions, timeouts, step-limit exhaustion.

→ Spec consequence: the platform must evaluate outcomes **and** observable
behavior, and must separate hard failures from quality failures at the schema
level. This became the 3-bucket failure taxonomy (TEST FAILURE / EVALUATOR
ERROR / INFRASTRUCTURE FAILURE) plus six behavioral evaluators.

**Q: "The moment" — what detection latency is acceptable?**
A: "Before a customer tells us" translates, operationally, to **merge time**.
If a regression reaches main, their deploy cadence means it can reach
production within hours. A nightly-only signal would have caught the billing
incident on day 1 instead of day 9 — better, but still a day of damage.
→ Spec consequence: blocking CI gate on every merge + nightly full suite.
Target: eval stage ≤ 10 minutes on their 2-core runners.

**Q: Ops will not learn a new tool — what DO they open?**
A: CI logs, `make` targets, and pytest. Nothing else. The representative was
emphatic: "if it's not in CI or something we already open, it's dead on
arrival."
→ Spec consequence: pytest-native bridge (`pytest -m agent_eval`), a
`make`-first workflow, exit codes as the machine interface, and Markdown
reports that render in the CI viewer. The weekly health view is one CLI
command (`agent-eval status`), not a web page. **Dashboard UI cut.**

### Session 2 — with the three agent-team leads

**Q: Can we instrument inside your frameworks?**
A: No, and not just territorially — LangGraph upgrades, SDK versions, and
their custom loop internals change too fast. They would maintain nothing
inside their agent code beyond a thin boundary.
→ Spec consequence: **adapter protocol** at the boundary (task in → actions +
result out), framework-agnostic core. The harness sees tool calls and final
answers, never framework internals.

**Q: What does each team accept as a quality bar?**
A: This was the negotiation the field guide's brief #12 predicts. Each team
wanted its own threshold; nobody wanted a platform-imposed number.
→ Spec consequence: per-benchmark thresholds in a versioned, reviewable file
(`configs/gates.yaml`). Teams own their numbers; the platform owns the
enforcement. The file is the agreement, in writing, in git.

**Q: Can we trust an LLM judge to gate CI?**
A: Support lead (burned before by "the model says it's fine"): only if it can
be shown to agree with humans, on their cases, with a number attached.
→ Spec consequence: judge calibration against hand labels is a first-class
experiment (`agent-eval calibrate`), with Cohen's κ and a ≥ 0.6 acceptance
bar **before** any judge verdict participates in gating. Judge prompts are
versioned like code.

**Q: The onboarding team's "don't ask" custom agent — how do we test it?**
A: Their agent is a plan-and-execute loop over internal tools, and they run
it "very carefully" (their words, slightly worryingly).
→ Spec consequence: five built-in pattern agents (ReAct, Plan-and-Execute,
Supervisor, Swarm, Map-Reduce) as the deterministic reference
implementations, so the harness's own regression testing never depends on
customer code.

### Session 3 — with ops + privacy counsel

**Q: Legal wants "what the agent did, not what it was thinking" — exactly?**
A: Counsel: observable actions (tool calls, arguments, results, timings) are
discoverable evidence; hidden chain-of-thought is a liability they don't want
stored.
→ Spec consequence: traces capture the action layer only — tool calls,
arguments (sanitized), results, latencies, termination. No CoT capture, and
that is documented as a design commitment, not a gap.

**Q: Can the eval stage make network calls?**
A: Their CI runners are egress-restricted (finance policy, post-audit). The
eval stage must run offline; live LLM calls, if any, happen in a separate,
opt-in job.
→ Spec consequence: deterministic backend as the default CI path; the live
judge path is a separate, explicit mode. Tool environment is network-sandboxed
by default with violations recorded per run. **This constraint we did not
choose — and it shaped the whole architecture.**

**Q: Cost?**
A: VP Eng: "we got a $4k invoice from the observability vendor's 'free' tier
once. Never again. Give me a number."
→ Spec consequence: per-run cost estimate (token-model) in every run record,
and a modeled daily figure in the operator view. Deterministic CI runs cost
$0.00 in real dollars — the estimate is clearly labeled as simulated pricing.

## Assumptions killed

| # | Initial assumption | How it died | Spec consequence |
|---|---|---|---|
| K1 | "A dashboard will make this visible" | Ops: nobody opens dashboards after week two; the vendor dashboard missed the 9-day incident | CLI + Markdown reports + `agent-eval status`; dashboard cut entirely |
| K2 | "Judge scores can gate CI directly" | Support lead's objection + our own calibration measurement (rubric v1.0 scored κ = 0.082 before the fix) | κ ≥ 0.6 vs hand labels required first; measured on a labeled sample before gating |
| K3 | "Per-case latency matters most" | Ops cares about suite wall-time and the tail: p95, not the mean | p50/p95 per case recorded; suite runtime as a tracked metric |
| K4 | "Teams will hand-write golden cases" | Nobody has time; the incident proved cases arrive *after* outages | Machine-generated, machine-verified golden sets (280 cases), adversarial/ambiguous categories included |
| K5 | "We should capture agent reasoning for debugging" | Privacy counsel: storing CoT is a liability, not an asset | Action-layer traces only; documented commitment |
| K6 | "Nightly-only detection is good enough" | Deploy cadence means hours-to-production; "before customers" = merge time | Blocking merge gate, nightly full suite as backstop |
| K7 | "Live LLM measurements can be produced during this build" | Build environment has no egress and no keys; fabricating them would violate the platform's own founding rule | Deterministic backend for all measured numbers; live paths implemented, marked *Not measured yet* |

## Scope cut (and what it cost)

Cut deliberately, each with the cost accepted in writing:

1. **Web dashboard / hosted UI** — the single biggest cut. Cost accepted: no
   visual trending; mitigation is committed JSON records + `agent-eval status`
   + CI-rendered Markdown. Revisit trigger: a second team asks for trending.
2. **Trace-vendor integration (OTel export)** — ops does not run a trace
   backend. Cost: no flame graphs. Mitigation: JSONL event streams per run,
   `agent-eval info` for reconstruction.
3. **Live model hosting / fine-tuning evaluation** — out of scope for v1 by
   the customer's own non-goal. Cost: judge reliability and latency are
   modeled, not measured, in this environment.
4. **Multi-tenant serving layer / API server** — the platform ships as a
   library + CLI + pytest plugin. Cost: no HTTP API; the CI contract *is* the
   interface.
5. **Auto-remediation (auto-rollback of regressed agents)** — tempting after
   the billing incident, but nobody trusts it yet and the detection signal is
   the prerequisite. Cost: humans stay in the rollback loop. Revisit trigger:
   six months of clean gate operation.

## The before-and-after, in one table

| The ask as it arrived | The spec it became |
|---|---|
| "know the moment they stop working" | Blocking CI eval gate on merge + nightly full suite; 3-bucket failure localization; per-metric regression thresholds in a reviewable file |
| "three teams, three stacks, don't ask" | Framework-agnostic adapter protocol; 5 deterministic pattern agents as reference; LangGraph/OpenAI SDK/CrewAI adapters |
| "ops will not learn a new tool" | pytest-native, `make`-first, exit-code machine interface, Markdown reports in the CI viewer, one-command weekly status |
| "logs legal can show what the agent did" | Action-layer JSONL traces (tool calls, args, results, timings); no CoT capture, by documented policy |
| "no idea what this costs" | Per-run cost estimate in every record; $0.00 deterministic CI runs; modeled live-equivalent cost labeled as such |
| "tell us when we're being dumb" | κ-calibrated judge before any LLM verdict gates CI; every number measured or explicitly *Not measured yet* |

The next document, [02-REQUIREMENTS-SPEC.md](02-REQUIREMENTS-SPEC.md), is the
formal version of the right-hand column — and
[03-ACCEPTANCE-CRITERIA.md](03-ACCEPTANCE-CRITERIA.md) is the quality bar both
sides signed, in writing, before the build started.
