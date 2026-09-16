# The 90-Second Story (Interview Version)

The field guide: *"Prepare the 90-second version and rehearse it until it is
boring to you: the problem in one sentence, the constraint that mattered
most, what you shipped, the number that proves it, and the one thing that
broke."* Then prepare the follow-up depth, "because the 90 seconds buys the
questions, and the depth is what you are being scored on."

## The 90 seconds

> Three teams at a mid-size SaaS shipped AI agents on three different
> frameworks. A prompt tweak degraded one agent silently, and they found out
> from a support-volume spike — nine days later, from their customers.
>
> The constraint that mattered most wasn't technical: ops told me flatly
> they would not learn a new tool — so whatever I built had to live inside
> CI and the tools they already open, or it would be dead on arrival. That
> killed the dashboard idea and forced a pytest-native design.
>
> So I built an evaluation harness — "pytest for agents." Each agent runs
> against 280 hash-pinned golden cases through a framework-agnostic adapter;
> deterministic, trajectory, and calibrated-judge evaluators score outcomes
> and behavior; and a regression gate fails the merge when quality drops
> past the team's own committed thresholds — failing closed on insufficient
> data.
>
> The number that proves it: detection latency went from nine days to under
> sixty seconds at merge time — the demo injects a 26.8-point regression and
> the gate catches it in 0.3 seconds with a per-metric table and a McNemar
> test on the flipped cases. And the judge was only allowed to gate CI after
> it hit Cohen's κ of 1.0 against hand labels — which mattered, because the
> first rubric I wrote measured κ = 0.082, and calibration caught it before
> it could gate anything.
>
> The thing that broke — my favorite one: my demo script stopped working on
> its second run ever, because I'd built it on the assumption that every
> run creates a new file, and the harness guarantees byte-identical
> deterministic runs — so it *overwrote* the same file. The product's core
> guarantee collided with my operational assumption. I fixed the demo, and
> documented the collision as a sharp edge in the runbook, because the next
> operator would have hit it too.

## Follow-up depth (the questions the 90 seconds buys)

**"Why deterministic runs? Isn't that avoiding the real problem?"**
Determinism is the prerequisite, not the evasion: without byte-identical
reruns, a regression gate can't distinguish a quality drop from noise, and
every threshold becomes unfalsifiable. Live-model runs are the opt-in second
tier — the adapters and the live judge client are implemented; their
measurements are labeled *Not measured yet* rather than fabricated. The
harness also grades itself: ablation experiments measured what its own
retry, verification, and tool-validation layers earn (retry removal costs
−12.5pp on weak agents).

**"How do you know the judge isn't just agreeing with itself?"**
It's calibrated against human hand labels with Cohen's κ, sampled and
stratified; κ < 0.6 pulls judge verdicts out of gating entirely. That bar
exists because my own first rubric scored 0.082 — a verbosity bias that
rewarded answers containing the gold answer plus padding. The failure is
documented with its fix (rubric v1.1, κ = 1.0, n=56).

**"What does the customer's operator actually do weekly?"**
One command — `agent-eval status` — latest pass rate per benchmark, drift
against baseline, dataset hashes, judge calibration, and a non-zero exit if
anything regressed, so cron does the watching. The runbook's command
sequence is executed by the clean-room release validator on every release,
so it can't silently rot.

**"What broke in operation, and what changed?"**
Ten incidents, all written down: the ablation experiment silently
measuring one config four times (YAML precedence), process-salted `hash()`
breaking dataset determinism, a judge rubric at κ = 0.082, the pytest
fixture vanishing on clean clones, Windows charmap encoding crashes,
cross-platform CRLF line ending mismatches in dataset hashing... Each entry
ends with what changed — the pattern across them is that six were caught by
the platform's own verification machinery and multi-OS CI matrix, which is
the product's argument applied to itself.

**"What would you do differently?"**
Hand-label ~150 calibration samples before writing any rubric (56 was the
floor); start the clean-room validator on day one instead of at release; and
two-tier run ids (content-hash for canonical runs, salted for display runs)
so determinism and "new file per run" stop colliding.

## One-line versions (pick your audience)

- *To a hiring manager:* "I built the CI gate that catches agent regressions
  at merge time — 9 days to 60 seconds — with a judge calibrated against
  humans before it was allowed to gate anything."
- *To an engineer:* "Deterministic agent-eval harness: 280 golden cases,
  20 evaluators, McNemar-backed regression gates that fail closed, κ = 1.0
  judge calibration, 0.0pp same-seed repro, 132 tests, zero-dep web dashboard, one runtime dep."
- *To the guide itself:* brief #12 — "monitoring and eval harness for
  someone else's LLM feature" — walked end to end: the harness is the
  artifact, and the agreement is the deployment.
