# Agent Evaluation — the platform's operating theory

## Why
Agents fail for non-model reasons more often than for model reasons: broken
tool schemas, stale context, missing retries, bad routing. An evaluation
system that only scores final outcomes is a scoreboard; one that localizes
failure to a layer is an engineering instrument. That distinction drives
every design decision here.

## How
Four strata, all first-class: **outcome** (task_checks, answer specs),
**trajectory** (golden alignment, tool selection), **behavioral** (loop rate,
termination, recovery, efficiency), **system** (latency, tokens, cost,
failure taxonomy). Every case verdict carries a granular FailureClass that
maps to exactly one report bucket: TEST FAILURE / EVALUATOR ERROR /
INFRASTRUCTURE FAILURE. Results are surfaced across three primary interfaces:
terminal CLI (`agent-eval status`, `agent-eval gate`), committed JSON/events logs,
and an embedded Web Dashboard (`agent-eval serve`) with step-by-step trajectory replay.

## Trade-offs
- Outcome-only evaluation is cheapest and most stable; we pay compute and
  dataset-authoring cost for trajectory/behavioral signal.
- Hidden chain-of-thought is deliberately NOT evaluated (not an observable
  API surface; behavior is the contract).

## Failure modes
- Score myopia: optimizing pass rate while loops/redundancy regress — caught
  by behavioral metrics in the same gate.
- Category blind spots: suites without adversarial/failure-inducing buckets
  overstate readiness (our datasets mandate both).

## Experimental evidence
react 89.3% vs supervisor 80.4% on identical corpora shows coordination
overhead is measurable; failure-inducing cases drop recovery to 50% without
harness retry (ablation study). See docs/final-report.md.
