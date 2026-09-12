# Evaluator Calibration

## Why
An evaluator is a measurement device; uncalibrated devices produce confident
nonsense. Cohen's kappa vs human labels quantifies whether the evaluator
agrees with ground truth beyond chance.

## How
`agent-eval calibrate` exports (case, answer, gold, judge decision) to CSV;
a human annotator fills `human_pass`; `compute_calibration` reports
agreement, Cohen's kappa, FP/FN, annotator count. Target: κ > 0.6. Judge
metadata (backend, prompt version) travels with every judgment so
re-calibration is triggered by any rubric/prompt change.

## Trade-offs
- Single annotator (author) is fast but subjective — documented as a
  limitation; the CSV schema supports multiple annotators for future panels.
- Containment-semantic rubric is calibrated to this dataset's answer styles;
  open-ended generation tasks need the live judge + its own calibration.

## Failure modes
- Kappa paradox on skewed marginals (everyone passes) — report agreement
  AND kappa together with n.
- Calibrating on the training distribution only — the sample spans all six
  categories.

## Experimental evidence
Measured: rubric v1.0 κ=0.082 (24 FN, verbosity bias) → v1.1 κ=1.0,
agreement 100% on n=56. The improvement loop is itself the evidence that
calibration catches real evaluator defects.
