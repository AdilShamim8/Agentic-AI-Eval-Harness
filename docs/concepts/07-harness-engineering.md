# Harness Engineering

## Why
The model is not the agent. Retry, verification, tool validation, and context
optimization are harness capabilities that can dominate outcomes — and each
adds complexity. Engineering discipline demands measured attribution, not
folklore.

## How
Each capability is a flag on `AblationProfile`; the gateway/agent-loop honor
them. `agent-eval ablate` runs the same (benchmark, agent, seed) across
profiles {full, no_verification, no_retry, no_tool_validation,
no_context_optimization} and reports pass-rate deltas plus behavioral shifts.
Harness versions are tracked independently from agent/model/benchmark/
dataset/evaluator/prompt/environment in every run manifest.

## Trade-offs
- Ablating at the harness level vs per-capability microbenchmarks: the
  profile matrix is coarser but directly answers "is this feature worth its
  complexity on OUR workloads".
- Strong agents self-heal and mask harness value — hence the two-skill design
  (0.85 strong / 0.60 weak) in the experiment protocol.

## Failure modes
- Silent override: our first ablation run showed zero deltas because the
  benchmark YAML's `ablation: full` override silenced the CLI flag — caught
  by the experiment itself, fixed (explicit CLI/config wins), regression-
  tested.
- Attribution confusion when capabilities interact — keep one flag per run.

## Experimental evidence
Weak agent: no_retry −12.5pp (recovery 100%→50%), no_verification −6.2pp,
no_tool_validation doubles loop rate. Strong agent: no_verification −5.4pp,
retry value masked by agent self-healing. Full table in final report.
