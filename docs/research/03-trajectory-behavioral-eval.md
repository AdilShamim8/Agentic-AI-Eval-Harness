# Research 03 — Trajectory & Behavioral Evaluation

Date: 2026-09-12 · Status: complete · Informs: evaluators/trajectory, harness ablations

## 1. Observable execution model

The platform evaluates only the observable execution record:

```
Input -> Plan -> Tool selection -> Tool calls -> Tool results ->
State changes -> Verification -> Termination -> Final output
```

Hidden chain-of-thought is neither exposed nor required. This is both an API reality
(most deployments hide CoT) and an ethics/robustness stance: behavior is the contract.

## 2. Trajectory metrics — definitions adopted

- **Tool-selection accuracy**: precision/recall/F1 of called tool names vs
  case-required tool set; forbidden-tool use is an automatic fail condition.
- **Trajectory alignment**: normalized LCS distance between observed tool-name
  sequence and golden sequence. Ordered matching catches ordering bugs (e.g., compute
  before retrieve); argument spot-checks catch wrong-argument regressions.
- **Tool-call efficiency**: `necessary_calls / total_calls`. Necessary = appears in
  golden path or is a deduplicated useful call. Redundant calls waste latency/cost.
- **Loop rate**: fraction of cases with >= K identical (tool, args) calls
  (K=3 default). Distinct from step-limit exhaustion.
- **Termination quality**: fraction of cases ending with an explicit final answer
  (not limit-truncation), with no post-answer junk steps.
- **Recovery rate** (failure-inducing cases): fraction where a scheduled tool fault
  occurred and the case still passed. Directly measures retry/fallback value.

## 3. Behavioral evaluation findings

- Loop detection must compare **canonicalized arguments** (JSON key order), else
  false negatives.
- Near-loops (slightly varying args) are best caught by step-limit + efficiency
  metrics rather than exact-match loop detection.
- Recovery is only measurable if the benchmark includes failure-inducing cases with
  **scheduled faults** (deterministic fault injection in the tool gateway). Random
  flakiness makes recovery metrics noisy; scheduled faults make them reproducible.
- Planning quality (plan-and-execute / supervisor patterns): deterministic proxy =
  plan-step coverage of required subtasks (each required tool/phase covered by >= 1
  plan step). LLM-judge plan scoring is optional and off by default (deterministic
  suffices for CI).

## 4. Harness ablation as behavioral experiment

The harness contributes capabilities: retry, verification, tool-arg validation,
context optimization. Each can be toggled (ablation profiles). The experiment matrix
(full vs -retry vs -verification vs -tool-validation vs -context-optimization) run on
the same agent+benchmark yields **measured attribution** of pass-rate deltas to
harness features — the core of Harness Engineering. Findings recorded in
docs/final-report.md with exact deltas; no claim without a run.

## 5. Trade-offs

- Golden trajectories are expensive; we generate them from templates and author-review
  a sample (documented in dataset docs).
- Sequence alignment on argument-level is deliberately coarse (key-arg equality on
  whitelisted keys) to keep signal-to-noise high.
- Parallel patterns (map-reduce) are traced as batched map steps; alignment treats a
  map batch as an unordered set (order within batch is not judged).
