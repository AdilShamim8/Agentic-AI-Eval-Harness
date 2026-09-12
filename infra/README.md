# Infra

- `.github/workflows/` — ci.yml (quality matrix), eval-gate.yml (BLOCKING
  evaluation quality gates), security.yml (secret scan, gitleaks, pip-audit,
  injection evaluation)
- The repo Makefile (in source/) mirrors every CI command for pre-push runs.
