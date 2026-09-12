# Engagement Brief — Cascade SaaS, Inc.

> **Provenance note.** Cascade SaaS, Inc. is a **fictional composite**, written
> the way real customer briefs arrive: deliberately ambiguous on the surface,
> with the hard problems hidden underneath. This is the same convention used by
> the FDE field guide's own twelve briefs (`portfolio/02-project-ideas.md`):
> "All twelve are fictional composites; none describes a real company's
> system." Resolving this brief into a spec is the demonstration — see
> [01-DISCOVERY-NOTES.md](01-DISCOVERY-NOTES.md).
>
> Brief frozen: 2026-09-11, before any requirements or architecture work.

## The ask, as it arrived

Email from the VP of Engineering, forwarded by our account team (verbatim,
typos included):

> Subject: agent stuff — help?
>
> hey — getting your team in because we trust you'll tell us when we're being
> dumb.
>
> short version: three teams shipped AI agents in the last two quarters. the
> demos all looked great. support triage (lang-something), onboarding flows
> (custom python, don't ask), and the ops folks did some multi-agent thing.
>
> last month somebody tweaked a prompt and the billing-triage agent got worse
> — *quietly*. we found out from a support volume spike NINE DAYS later. nine
> days. our customers found out before we did.
>
> we need to know the moment they stop working. before our customers tell us.
> and whatever you build — ops has to actually run it. they will not learn a
> new tool. if it's not in CI or something they already open, it's dead on
> arrival.
>
> also legal got involved after the billing thing, so whatever you do needs
> logs good enough that we can show *what the agent did* — not what it was
> thinking.
>
> no idea what this costs. tell us. you have the intro call thursday.

## Account context (from the intro call)

- **Company:** mid-size B2B SaaS, ~450 employees, ~2,800 customers. Fictional
  composite; the numbers are chosen to be plausible, not real.
- **Three agent teams, three stacks:**
  - *Support team* — LangGraph ReAct-style triage agent, in production 5 months
  - *Onboarding team* — custom Python plan-and-execute agent ("don't ask")
  - *Ops team* — supervisor + worker-swarm scripts for internal tooling
  - A fourth team is evaluating OpenAI Agents SDK and CrewAI for a Q4 project
- **The incident:** a prompt tweak shipped Thursday; billing-triage accuracy
  degraded silently; detected 9 days later via support volume, not via any
  test. No rollback path existed because no signal existed.
- **What "good" looks like to them:** they find out before customers do, at
  merge time; ops touches nothing new; legal gets auditable traces.
- **What they fear:** a science project. They have been burned by an
  observability vendor whose dashboard nobody opened after week two.

## Why this maps to FDE brief #12

The field guide's brief #12 ("Monitoring and eval harness for someone else's
LLM feature") is this engagement with one team instead of three:

> "Another team shipped an AI feature. It works, mostly. We need to know the
> moment it stops."

The brief's hidden depth is the real constraint here too: the platform team
does not own the agents, cannot force instrumentation inside the frameworks,
and must negotiate a quality bar each agent owner accepts. The harness is the
artifact; the agreement (committed thresholds, CI contract) is the deployment.

## Explicit non-goals stated by the customer

- They do **not** want a model-score leaderboard or vendor bake-off.
- They do **not** want a new dashboard product ("nobody opens dashboards after
  week two" — their words, from the incident).
- They do **not** want agent *reasoning* logged — legal explicitly asked for
  observable actions, not hidden chain-of-thought (privacy counsel's
  requirement).
- They will **not** host or tune models in v1; agents are API consumers.

## What the customer agreed to supply

- Ten tickets per team per week from real production traffic, sanitized, to
  seed golden sets (this is the "golden set built from their real traffic"
  depth marker — in this build, simulated by the dataset generator with
  machine verification, honestly labeled).
- One reviewer per team for hand-labeling a judge calibration sample.
- A CI slot: their GitHub Actions runners, 2-core, with a hard 10-minute
  budget for the eval stage.
