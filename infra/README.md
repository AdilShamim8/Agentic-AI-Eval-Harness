# Infrastructure & Deployment

- `.github/workflows/` (canonical, at repo root) — ci.yml (dual-OS quality matrix: Ubuntu + Windows across Python 3.11/3.12),
  eval-gate.yml (BLOCKING evaluation quality gates), security.yml (secret scan, gitleaks, pip-audit,
  injection evaluation).
- `Dockerfile` & `docker-compose.yml` (root) — multi-stage rootless containerization (non-root `aeh:10001`)
  with pre-configured profiles for batch CLI runs (`runner`), health checks (`status`), and Web Dashboard (`dashboard`).
- `Makefile` (root) — mirrors every CI command and container workflow for clean pre-push verification (`make gate`, `make serve`, `make docker-build`, `make docker-run`).


Note: the duplicated copy of the workflows that used to live under infra/.github was removed — it had silently drifted from the canonical .github/workflows/. The release pipeline (scripts/package_release.py) copies the canonical workflows into release/infra/.github when building the zip; nothing in the repo reads infra/.github.
