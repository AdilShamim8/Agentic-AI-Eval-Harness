# SECURITY.md

## Reporting

Report vulnerabilities privately to the maintainers (open a private security
advisory on GitHub, or contact the owner listed in pyproject.toml). Do not
open public issues for suspected vulnerabilities.

## Security model (summary)

The evaluation infrastructure is itself a threat surface: it executes agent
code, dispatches tools, and processes benchmark data that may contain
adversarial content. Controls (all testable via `make security`):

| Control | Implementation | Test |
|---|---|---|
| Tool allow/deny | `PermissionPolicy` at the `ToolGateway`; case-level forbidden tools also enforced | `test_permissions.py` integration tests |
| Argument guards | forbidden arg keys (cmd/shell/exec/...), length caps | gateway tests |
| Network isolation | `NetworkGuard` patches `socket.socket` during runs; tools are offline fixtures by construction | `test_network_guard` |
| No dynamic execution | calculator uses AST whitelists; static import scan forbids subprocess/eval/exec in harness modules | `test_no_subprocess_or_network_imports_in_harness` |
| Resource bounds | step/tool-call/wall-clock/output/state caps per case | harness limits tests |
| Prompt-injection screening | pattern screening on tasks and tool outputs; flagged + audit-logged (never silently dropped) | injection tests |
| Secret hygiene | redaction at every export boundary; repo-wide secret scan in CI | `test_redaction`, `scan_secrets.py --strict` |
| Audit trail | security events (denials, injection flags, timeouts) in the run's JSONL event log | permission tests |

Full threat model: [docs/security/THREAT-MODEL.md](docs/security/THREAT-MODEL.md).

## Trust boundary caveat (v0.1)

Built-in tools and the harness run in-process; **arbitrary user-supplied agent
code executes with test-process privileges** and is outside the sandbox
boundary in v0.1 (documented in the threat model). For untrusted agent code,
run the CLI in a container/VM. Live LLM-judge HTTP calls are the only network
path and are opt-in via environment variables.
