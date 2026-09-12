# Evidence map — claim → artifact → command

| Claim | Artifact | Verify with |
|---|---|---|
| 280 verified golden cases, 5 patterns | datasets/ + manifest | `python scripts/generate_datasets.py` (prints verification) |
| Full-suite scores + CIs | evals/results/experiments.json | `make experiments` |
| Ablation attribution | same + docs/final-report.md §3 | `make ablate` |
| Judge κ 0.082 → 1.0 | evals/calibration/hand_labels.csv | `make calibrate` |
| Same-seed repro 0.0pp | evals/results/experiments.json | `make repro` |
| Regression gate fails bad agents | evals/baselines/main.json | e2e test `test_cli_regression_gate_flow` |
| 121 tests green | tests/ | `make test` |
| Secret-clean repo | — | `make security` |
| CI gates wired | .github/workflows/eval-gate.yml | yaml valid; commands = Makefile targets |
| Byte-identical dataset regeneration | tests/integration | `pytest -k regenerates` |
