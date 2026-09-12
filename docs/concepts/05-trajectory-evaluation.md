# Trajectory Evaluation

## Why
Two agents with identical final answers can differ catastrophically in cost
and reliability (12 redundant calls vs 2 clean calls; near-loop states).
Outcome-only evaluation cannot see this; regression gates on behavior can.

## How
Golden trajectories are ordered tool sequences with optional arg containment
checks. The `trajectory` evaluator scores 0.7 × normalized-LCS(sequence) +
0.3 × argument spot-checks. Map-reduce batches count every item (a 3-item map
has a 4-step golden including the reduce). `tool_selection` computes
precision/recall/F1 against required tools; forbidden tool use zeroes the
score. Only observable steps are judged — never hidden CoT.

## Trade-offs
- Ordered LCS punishes benign reordering in independent steps — mitigated by
  keeping ordering-sensitive goldens to dependent chains.
- Argument checking is deliberately spot-check-style (key args only) —
  full-argument diffing produces noise without signal.

## Failure modes
- Golden over-specification (every arg pinned) makes legitimate alternative
  paths fail; we pin only `args_contains` keys the task actually constrains.
- Loop detection must canonicalize args (sorted JSON) or it misses
  key-order-shuffled repeats.

## Experimental evidence
Trajectory scores differentiate agent quality: 0.964 (skill .85) vs 0.857
(skill .70) on react_basic; ablation no_tool_validation raises loop rate from
0% to 3.6-12.5% — caught by the loop_detection evaluator, not by outcomes.
