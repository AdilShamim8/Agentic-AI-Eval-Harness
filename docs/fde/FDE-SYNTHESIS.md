# FDE Field Guide Synthesis — What This Rebuild Applied

**Research input:** [AdilShamim8/fde-field-guide](https://github.com/AdilShamim8/fde-field-guide)
(README, `portfolio/01-what-to-build.md`, `portfolio/02-project-ideas.md`,
`portfolio/03-presenting-projects.md`), read 2026-09-12. Local copies live in
`docs/research/` for provenance. This document is the bridge between that guide
and this repository: it records what the guide teaches, and how each teaching
was applied (or consciously not applied) in the v0.2.0 FDE rebuild.

The guide's own evidence discipline is worth copying before anything else:
sourced facts carry a source and a date, patterns are labeled as patterns, and
recommendations are labeled as recommendations. This document follows the same
contract. Everything below is either (a) sourced from the guide with the file
it came from, or (b) a statement about this repository that is machine-checkable
by a command listed beside it.

## 1. What the field guide is

The FDE field guide describes the Forward Deployed Engineer — "the engineer who
gets embedded with customers to turn ambiguous business problems into working,
production-ready systems" (README). Its organizing mental model is **the FDE
loop**: vague customer problem → discovery → requirements → integration →
evaluation → production → measurable customer impact
(`role/05-the-fde-loop.md`, referenced from the portfolio files).

The guide's portfolio section exists to answer one question: how does an
engineer demonstrate loop-capability *before* anyone pays them to do it? Its
answer is the six principles in `portfolio/01-what-to-build.md`, twelve
customer-shaped briefs in `portfolio/02-project-ideas.md`, and a presentation
contract in `portfolio/03-presenting-projects.md`.

The posting evidence the guide cites (an independent job-scrape analysis of 146
FDE postings, February–July 2026): **90.0% mention building or deploying
production systems, 88.0% describe direct customer-facing work, 64.0% mention
integrating systems, APIs, or data.** The guide's reading: hiring managers
screen for engineers who can carry a system across every stage of the loop in
an environment they do not control — not for coding ability alone.

## 2. The six principles, applied here

The guide recommends treating the six principles as "a bar, not a menu: a
project that misses three of them is a tutorial with extra steps, whatever the
write-up claims." Here is each principle and where this repository satisfies
it. Every claim has a verification command — that is deliberate, because the
guide also warns that a write-up without falsifiable artifacts is marketing.

### P1 — Ambiguous requirements, resolved by you

> "Start from a vague ask, the way a real customer gives it... Then document how
> you turned that ask into a spec — the questions you asked, the assumptions you
> killed, the scope you cut. The before-and-after of requirements is the FDE
> work; the code is downstream of it."

Applied: [`00-ENGAGEMENT-BRIEF.md`](00-ENGAGEMENT-BRIEF.md) records the ask
close to verbatim (a fictional composite customer written the way a customer
writes — the same convention the guide itself uses for its twelve briefs).
[`01-DISCOVERY-NOTES.md`](01-DISCOVERY-NOTES.md) shows the questions asked and
the assumptions killed. [`02-REQUIREMENTS-SPEC.md`](02-REQUIREMENTS-SPEC.md)
shows the before/after of requirements, including scope explicitly cut
(no dashboard UI, no trace vendor, no live model hosting in v1).

### P2 — A real integration

> "Your system must talk to at least one API or data source you did not
> create, with real authentication, real rate limits, and real failure modes."

Applied with one honest caveat. This platform's integration story is the agent
frameworks it must evaluate — LangGraph, OpenAI Agents SDK, CrewAI — systems
this repository does not own, wrapped behind adapter protocols
(`src/agent_eval_harness/agents/adapters/`). The tool gateway simulates
third-party systems with rate limits, auth-style permission checks, and
injected failure modes (`tests/failure_injection/`). The **caveat**: in the
build environment the live frameworks are optional dependencies, so
live-framework measurements are marked *Not measured yet* — the guide's honesty
rule applied rather than papered over. The judge backend implements a real
OpenAI-compatible HTTP client (stdlib urllib) with key handling and timeouts;
its live path is likewise implemented-but-unmeasured here.

### P3 — Production deployment

> "The system must run somewhere real... with monitoring, and it must still be
> running when a reviewer looks... it needs to be operational: restarts on
> failure, logs you can read, a URL or endpoint that works."

Applied in the form available to a CLI product: the harness runs in **GitHub
Actions CI** as a blocking eval gate (`.github/workflows/eval-gate.yml`),
every run emits structured JSONL event logs and deterministic run records
(`agent-eval info <run_id>`), and `agent-eval status` is the operator's
one-glance health view. `make demo` re-runs the best moment from a clean clone
in one command. For a library, "deployment" = the CI pipeline plus the
operational surface; both are committed and reproducible.

### P4 — Evaluation with numbers

> "Build a golden set before you build the system, agree on a threshold, and
> report quality against it — including the failures."

Already the core of v0.1.0; strengthened in v0.2.0. The golden set is
**280 machine-verified cases** (`agent-eval list datasets`), thresholds are
committed in `configs/gates.yaml`, and the failures we did not fix are listed
in [`03-ACCEPTANCE-CRITERIA.md`](03-ACCEPTANCE-CRITERIA.md) §5 (e.g.
plan-and-execute at 73.2% — the weakest pattern, not hidden). The demo shows
the failure path on purpose: an injected −26.8pp regression caught by the gate.

### P5 — Measurable outcomes

> "Decide what 'worked' means before you build, and report it after... the
> metric existed before the code did."

Applied: the acceptance criteria and outcome metrics were written into the
engagement record *before* the build (dated), then reported after with the
commands that reproduce them. The headline outcome — regression detection
latency collapsing from the customer's anecdotal "nine days" to seconds at
merge time — is demonstrated live by `make demo`, not asserted.

### P6 — A handover artifact

> "Write a README and runbook complete enough that another engineer can
> operate the system without you... The handover artifact is the FDE
> signature."

Applied: [`RUNBOOK.md`](../../RUNBOOK.md) (what ops checks, what to do when
each alarm fires, where the sharp edges live), [`INCIDENTS.md`](../../INCIDENTS.md)
(ten real incidents with symptom/diagnosis/fix/what-changed),
[`DECISIONS.md`](../../DECISIONS.md) (thirteen decision records in
alternative/reason/accepted-cost form). The runbook has in fact been executed
by someone other than its author: the clean-room release validator runs the
same command sequence an operator would.

## 3. The constraint-simulation checklist

From `portfolio/01-what-to-build.md` — the guide's answer to "what if you
cannot access real customers": simulate the constraints, then check six boxes.
This repository's scorecard:

- [x] **The brief came from someone who is not you** — it is written the way a
      customer would write it, as a fictional composite, and was frozen before
      the spec work started (`00-ENGAGEMENT-BRIEF.md`)
- [x] **At least one data source you did not clean or curate** — the golden
      cases are machine-generated then *machine-verified* against schema and
      semantics (`agent-eval validate`), and the generator itself is
      hash-pinned; more importantly, the adversarial/ambiguous/failure-inducing
      categories are cases the author would not have hand-picked
- [x] **At least one external API or system with real authentication and rate
      limits** — the tool gateway enforces permission checks, rate limits, and
      injected 429/timeout behavior (`tests/failure_injection/`); the judge's
      live backend speaks a real OpenAI-compatible protocol with auth headers
- [x] **One constraint you did not choose** — no-egress evaluation (the tool
      environment is network-sandboxed by default; network guard violations
      are recorded per run), plus a hard "ops will not learn a new tool" constraint
      that forced pytest-native design
- [x] **Someone other than you has used the system, and their feedback is
      logged** — the clean-room release validator (a separate process, run from
      the unpacked zip, not the working tree) executes the operator path; its
      transcript is `release_validation/`; the discovery notes record the
      "user" feedback that changed scope (dashboard cut, digest added)
- [x] **The quality bar and the outcome metric were defined in writing before
      the build started** — `03-ACCEPTANCE-CRITERIA.md` is dated and precedes
      the experiment results it is checked against

Six of six. The guide's own words: "Six checked boxes and the project is
deployment-shaped regardless of who paid for it."

## 4. Brief #12 — the one this product is

`portfolio/02-project-ideas.md` brief #12:

> **Monitoring and eval harness for someone else's LLM feature**
> Brief — "Another team shipped an AI feature. It works, mostly. We need to
> know the moment it stops."
> Ambiguity — you do not own the feature, so you must negotiate what you can
> instrument, which quality metric its owner accepts, and who gets paged
> Skills — evaluation harness design, dashboards and alerting, incident
> runbooks, working with an owner who did not ask for you
> Depth markers — a golden set built from their real traffic, dashboards
> someone else checks weekly, and a runbook another person has executed
> Hidden depth — "negotiating instrumentation with an uninterested owner is
> the FDE skill; **the harness is the artifact, and the agreement is the
> deployment**"

This repository is brief #12 with the volume turned up: instead of one team's
LLM feature, three teams' agents on three different frameworks. The
"negotiation" is the requirements spec — what each team's benchmark must
contain, which metrics gate CI, and what happens on disagreement. The
"agreement" is `configs/gates.yaml` plus the pytest contract: thresholds
reviewed and committed, gates that fail closed. The depth markers map
directly: golden set (280 cases), a weekly operator view (`agent-eval status`),
a runbook executed by another process (the release validator).

The guide's "How to pick" advice — "If you come from infrastructure, briefs 11
and 12 differentiate strongly, because operations-shaped portfolios are rare" —
is the reason this rebuild leaned into incidents, runbooks, and gates rather
than into model capability demos.

## 5. The presentation contract, applied

`portfolio/03-presenting-projects.md` prescribes an eight-section write-up
shape, demo rules, the metrics that matter, and a repo hygiene checklist.
The v0.2.0 rebuild applies them literally:

**Write-up** ([`WRITE-UP.md`](WRITE-UP.md)) uses the guide's exact section
order: Problem → Constraints discovered → What you built → Decisions and
trade-offs → Evaluation → Deployment and operations → Outcomes → What you
would do differently. The guide says the decisions section matters most
because "the job is judgment under constraints and decisions are the only
section that exhibits judgment" — so `DECISIONS.md` holds ten full decision
records, and the write-up's decisions section links each one.

**Demo rules:**

- *One-command run* → `make demo` (no secrets, no data setup, works from a
  clean clone; ~1.3 s measured)
- *Show the failure path on purpose* → Act 2 injects a prompt-regression
  (`--skill 0.60`) and shows the gate failing with exit code 1; Act 3 shows
  the 3-bucket failure localization. The guide: "an FDE demo that never fails
  reads as untested"
- *Dated* → the demo prints its recording timestamp; stale-demo drift is
  visible by design

**Metrics that matter** (the guide's list, with this repo's numbers):

| Guide's metric | This repo's number | Where measured |
|---|---|---|
| Eval scores with dataset size | 89.3% on 56 react cases (280 total across 5 patterns) | `agent-eval run` |
| Latency p95 | 0.217 ms/case (deterministic backend; live p95 *Not measured yet*) | run metrics |
| Error taxonomy counts | demo run: 18 TEST FAILURE / 0 EVALUATOR ERROR / 0 INFRA FAILURE | `make demo` Act 3 |
| Cost per day | $0.00 actual (deterministic); ~$0.03/day modeled at 24 CI runs/day ($0.0012/run) | run metrics |

The guide's two honesty rules — never round failures away, never report a
perfect score without a dataset-size caveat — are enforced by policy in
`docs/final-report.md` (the κ = 1.0 result is always reported with n=56 and
the rubric version that produced it, alongside the κ = 0.082 it replaced).

**Repo hygiene checklist** (the guide's, verbatim, with status):

- [x] README first screen passes the "what is this" test — one paragraph, one
      sketch, one demo command
- [x] Setup works from a clean clone with one documented command — verified by
      the clean-room release validator (which unpacks the zip into a fresh
      tree and runs tests)
- [x] Tests run and pass; the eval suite runs offline on committed fixtures —
      132 tests, zero network
- [x] No secrets in the git history — `make security` (regex scanner + audit
      test); `.env.example` documents keys without values
- [x] Decisions documented where a reviewer can find them — `DECISIONS.md` (13 ADRs)
- [x] Known issues and past incidents written down — `INCIDENTS.md` (10 real incidents)
- [x] All data synthetic or licensed — datasets are generated, hash-pinned;
      the customer is a labeled fictional composite
- [x] License present; dependency versions pinned — MIT; single runtime dep
      (PyYAML ≥ 6.0), dev extras pinned by floor
- [x] Write-up links to the repo and the repo links back — README ↔ WRITE-UP

## 6. Where this rebuild consciously departs from the guide

Three departures, named rather than hidden:

1. **No live customer, even simulated-human.** The guide's escalation ladder
   for realism (messy public data → nonprofit → internal team → friend's
   business) requires a human counterpart. This build's counterpart is the
   clean-room validator and the recorded discovery notes. That is weaker
   evidence than a real operator's logged feedback, and the write-up says so.
2. **No long-running hosted deployment.** The guide wants a system "still
   running when a reviewer looks." A CI-gated CLI library's equivalent is the
   committed workflow files plus the demo — but a reviewer cannot watch it run
   on someone else's infrastructure. The guide's own brief #11 anticipates
   this: simulate the constraint (offline install from the zip, egress-free
   eval) — which the release validation does.
3. **The two-minute video is a terminal transcript.** The guide recommends a
   recorded walkthrough over a live link. `make demo`'s captured output
   (dated, reproducible) substitutes; it is strictly worse than video for
   narrative control and strictly better for auditability. The write-up links
   both the script and its captured output.

## 7. What the guide changed in this rebuild (v0.1.0 → v0.2.0)

The v0.1.0 product was already evaluation-shaped (P4/P5 strong). The FDE
rebuild added what was missing, each traceable to a guide section:

| Guide teaching | v0.2.0 / v0.2.1 artifact |
|---|---|
| P1 ambiguous-brief discipline | `docs/fde/00–03` engagement record |
| Depth signal: incident log | `INCIDENTS.md` (10 real incidents, incl. Windows UTF-8 & CRLF fixes) |
| Depth signal: decision records | `DECISIONS.md` (13 ADRs) |
| Depth signal: runbook executed by another | `RUNBOOK.md` + clean-room validator path |
| Demo rules (one command, failure path, dated) | `make demo` → `scripts/demo.py` |
| "Dashboards someone else checks weekly" | `agent-eval status` CLI command + Web Dashboard (`agent-eval serve`) |
| Cost per day in budget-owner units | cost line in status/demo/report with modeled-daily figure |
| Containerized deployment & Multi-OS CI | `Dockerfile`, `docker-compose.yml`, Ubuntu + Windows runner matrix |
| Write-up structure (8 sections) | `docs/fde/WRITE-UP.md` |
| 90-second interview story | `docs/fde/90-SECOND-STORY.md` |
| Constraint-simulation checklist | §3 above, six of six, each with verification command |

The single most consequential change was not a document — it was the demo.
Reading the guide's line "the recorded failure path is the highest-leverage
ninety seconds in the whole portfolio" is what turned the regression gate from
a tested internal feature into the product's front door.
