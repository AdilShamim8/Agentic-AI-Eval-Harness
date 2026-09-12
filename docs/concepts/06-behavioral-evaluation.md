# Behavioral Evaluation

## Why
Behavior is the deployable contract: termination quality, loop avoidance,
recovery from faults, planning coverage, and tool efficiency determine
production reliability more than point-in-time accuracy.

## How
Evaluators: `loop_detection` (≥3 identical canonicalized calls → loop;
limit-truncation also fails), `termination_quality` (explicit final answer,
last step is final, within budget), `recovery` (on fault-scheduled cases:
fault_injected AND eventually succeeded), `tool_efficiency`
(necessary/total where necessary = golden steps + fault-driven retries),
`planning_quality` (deterministic plan-coverage of required tools; n/a for
patterns without plans).

## Trade-offs
- Deterministic proxies (plan coverage) vs LLM-judged plan critique: proxies
  are reproducible and CI-safe; judged critique is richer but unmeasured here.
- Recovery is only measurable with scheduled faults — random flakiness is
  noise; deterministic injection is signal.

## Failure modes
- Efficiency penalizing fault-recovery retries as waste — fixed by counting
  fault-driven retries as necessary.
- Loop detection blind to near-loops (slightly-varying args) — bounded by
  step limits + efficiency as a second net.

## Experimental evidence
Recovery: 100% (full harness) vs 50% (no_retry, skill .60) on
failure-recovery cases; loop rate 0% (full) vs 12.5% (no_tool_validation,
skill .60). See final report §Ablations.
