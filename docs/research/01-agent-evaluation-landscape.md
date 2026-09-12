# Research 01 — Agent Evaluation Landscape

Date: 2026-09-12 · Status: complete · Informs: PRD, evaluator system, architecture

## 1. The core problem

Evaluating an agent is harder than evaluating a model because the unit under test is a
**system**: model + harness + tools + context + state + verification + governance. A
single scalar score ("the agent got 82%") conflates at least eight failure surfaces.
Production teams consistently report that agents fail for non-model reasons (broken
tool schemas, stale context, bad retrieval, missing retry logic) far more often than
for raw model-capability reasons. Any evaluation platform that cannot localize failure
to a layer is a scoreboard, not an engineering instrument.

## 2. Four evaluation strata

| Stratum | Question answered | Typical method |
|---|---|---|
| Outcome | Is the final result right? | Exact/semantic match, task checks, LLM-judge |
| Trajectory | Was the path reasonable? | Golden-trajectory alignment, tool-choice F1 |
| Behavioral | Did the agent behave well? | Loop rate, termination, recovery, redundancy |
| System | What did it cost? | Latency p50/p95, tokens, cost, failure rate |

Key finding from the literature and from LangSmith/Langfuse field usage: outcome-only
evaluation has the worst regression-signal quality. An agent can pass 90% of outcome
checks while quietly doubling tool calls or entering near-loop states — regressions that
will surface in production under load. This platform therefore makes trajectory and
behavioral metrics first-class, not bolt-ons.

## 3. Evaluation methodologies reviewed

- **Reference-based scoring** (exact match, contains, numeric tolerance, JSON schema).
  Deterministic, cheap, CI-friendly. Weak on open-ended phrasing. Verdict: default
  choice whenever the answer space is closed.
- **Reference-free LLM-as-judge**. Covers semantic equivalence, instruction following,
  synthesis. Costs tokens, drifts with judge model version, needs calibration. Verdict:
  use only where deterministic checks are provably insufficient (rule adopted in our
  evaluator policy).
- **Trajectory alignment**. Compare observed tool sequence to a hand-labeled golden
  path. Normalized edit/LCS distance works well for tool-name sequences. Argument-level
  comparison is noisier; restrict to key-argument spot checks. Verdict: LCS-based
  sequence score + arg spot checks.
- **Pairwise comparison** (A/B judging). Lower variance than absolute scoring for
  subjective axes, but produces no absolute number to gate CI. Verdict: out of scope
  for v0.1 gates; documented as extension.
- **Human calibration panels**. Gold standard for evaluator reliability (Cohen's kappa
  vs human labels). Expensive; sampled. Verdict: required for our judge (target
  kappa > 0.6 on a >= 50-case hand-labeled sample).

## 4. Benchmark design findings

- Golden datasets must mix **normal / difficult / ambiguous / edge / adversarial /
  failure-inducing** cases. Suites without adversarial and failure-inducing buckets
  systematically overstate agent readiness.
- Hand-labeled trajectories are the single most expensive asset. Generate-by-template
  then **human-review a sample** is the accepted compromise (our approach: generator +
  author-reviewed calibration sample, documented).
- Reproducibility requires pinned seeds, pinned versions of every component (agent,
  harness, dataset, evaluator, prompts), and content hashes of datasets. Temperature
  and sampling parameters must be recorded per run.
- Statistical honesty: report Wilson 95% intervals for pass rates; treat sub-CI deltas
  as "no signal". With n<30 per bucket, never gate on that bucket alone.

## 5. Gaps in existing tooling (design opportunities)

1. No mainstream tool treats the **harness itself** as the unit under evaluation
   (ablation of retry/verification/validation). LangSmith ablations exist but are
   model/prompt-centric.
2. Regression gates wired into CI exist only in proprietary setups; open-source
   eval frameworks focus on notebooks/one-off runs.
3. Failure taxonomy in most tools conflates "agent wrong" with "evaluator broke" and
   "infra down". Production teams need the three separated at the schema level.
4. Framework lock-in: DeepEval/promptfoo skew toward specific stacks. A
   framework-agnostic adapter protocol with a small surface is the opening.

## 6. Patterns we adopt / reject

Adopt: strata model; deterministic-first evaluator policy; versioned benchmarks with
thresholds; CI quality gates; Wilson intervals; failure taxonomy at schema level;
harness ablation as first-class experiment.

Reject: pure notebook-driven eval (not reproducible); chain-of-thought inspection
(hidden reasoning is not observable API surface; we evaluate only observable
behavior); single overall score as a headline metric.
