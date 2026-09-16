# CI Evaluation

## Why
"Evaluations in CI" only counts if the gate can actually fail the merge.
Notebooks and dashboards inform; gates enforce.

## How
Three workflows: ci.yml (lint/format/type + full dual-OS test matrix covering Ubuntu
and Windows runners on Python 3.11/3.12 + benchmark validation + dataset regeneration
hash check), eval-gate.yml (blocking: smoke benchmarks per pattern, full react +
failure_recovery runs with threshold gates, regression gate vs the committed `main`
baseline with exit-code semantics, adversarial evaluation, same-seed reproducibility),
security.yml (secret scan --strict, gitleaks, pip-audit, security test suite,
adversarial benchmark). Makefile targets mirror every CI command so gates
are verifiable pre-push (`make gate`, `make security`, `make validate`, `make docker-build`).

## Trade-offs
- Blocking evals slow CI: deterministic backend keeps the full gate suite
  under ~30s; live-LLM gates belong in nightly/label-triggered jobs (wired,
  not enabled by default).
- Committed baseline vs remote tracking: committed = reviewable = intentional
  re-baselining via PR.
- Multi-OS matrix vs runner minutes: testing on both Linux (`ubuntu-latest`) and
  Windows (`windows-latest`) catches OS-specific codepage/charmap traps and CRLF git
  line-ending variations before code merges.

## Failure modes
- Gate theater (evals that always pass): countered by the regression demo
  (challenger fails the gate in tests) and min-case fail-closed semantics.
- Environment drift between local and CI: same commands via Makefile and Docker;
  python version matrix covers 3.11/3.12 across Windows and Linux.
- Line ending / encoding drift: avoided via repository-level `.gitattributes` (`eol=lf`)
  and byte-level CRLF normalization in dataset integrity checks.

## Experimental evidence
The gate failure path is itself tested (e2e: degraded run → exit 1;
identical run → exit 0). CI YAML validity is asserted locally; every command
the workflows invoke runs green via make targets.
