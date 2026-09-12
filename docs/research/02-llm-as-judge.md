# Research 02 — LLM-as-Judge

Date: 2026-09-12 · Status: complete · Informs: evaluators/llm_judge, calibration experiment

## 1. Why and when

LLM-as-judge is for criteria that are semantic and open-ended: answer correctness vs a
reference phrased differently, instruction following, plan quality, synthesis quality.
For closed answer spaces, deterministic evaluators dominate: free, reproducible,
CI-safe. **Policy adopted: never invoke an LLM judge where a deterministic evaluator
is sufficient.** The platform encodes this in benchmark configs (LLM judges are opt-in
per benchmark) and in docs.

## 2. Known failure modes (from literature + postmortem culture)

- **Position bias** — prefer first/last option in pairwise; mitigations: order swap.
- **Verbosity bias** — longer answers scored higher; mitigation: rubric anchoring.
- **Self-preference bias** — judge prefers its own model family; mitigation: record
  judge model identity, allow different judge backend.
- **Rubric drift** — prompt wording changes scores silently; mitigation: **versioned
  prompts** (prompts/ directory, `judge_*_v1.md`), prompt hash recorded per judgment.
- **Schema violations** — judge returns prose not JSON; mitigation: strict structured
  output request + parser with error retry + deterministic fallback judge.
- **Uncalibrated confidence** — judge self-reported confidence uncorrelated with
  accuracy; mitigation: treat confidence as metadata only, calibrate externally.

## 3. Implementation requirements extracted

1. Structured outputs: judgment = {score ∈ [0,1], pass bool, rationale, confidence,
   per-item checklist}. Versioned prompt files with explicit rubric levels.
2. Judge metadata recorded with every judgment: backend id, model id, prompt id+hash,
   latency, tokens (when available), retry count.
3. Deterministic fallback judge (rubric-scoring against gold answer: token-F1 overlap +
   checklist satisfaction) so the platform functions with zero external API and CI
   never silently skips judging.
4. Calibration protocol: hand-labeled sample (>= 50), report Cohen's kappa vs human
   labels, agreement %, false-positive/false-negative counts; re-calibrate on rubric
   changes; publish numbers with sample size.
5. Consistency probe: judge the same case twice (deterministic judge must be exactly
   stable; live judge measured empirically).

## 4. Trade-offs accepted in v0.1

- Live judge backends are implemented (OpenAI-compatible HTTP via stdlib urllib) but
  **not exercised in this build environment** (no API key, no SDK). Their reliability
  numbers are explicitly "Not measured yet" everywhere results are reported. The
  deterministic rubric judge IS measured (kappa vs hand labels).
- Single annotator (the author) for calibration labels — documented as a limitation;
  protocol supports adding annotators (labels CSV has annotator column).

## 5. Score semantics

Judges emit normalized [0,1] scores with explicit thresholds per criterion
(e.g., answer_correctness pass >= 0.7). Keeping judge scores on the same [0,1] scale
as deterministic evaluators lets the metrics/regression layers stay judge-agnostic.
