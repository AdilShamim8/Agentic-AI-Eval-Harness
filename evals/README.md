# Evaluation evidence

- `baselines/main.json` — the CI regression baseline (react_basic, skill .85)
- `calibration/hand_labels.csv` — 56 hand-labeled judge calibration sample
- `results/experiments.json` — every measured claim in docs/final-report.md
- `runs/` — canonical full-suite run records (+ .events.jsonl event logs);
  all other runs are reproducible via scripts/run_experiments.py
