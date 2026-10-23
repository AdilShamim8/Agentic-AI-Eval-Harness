# Security Review

## 1. Trust boundaries (verified from source + THREAT-MODEL.md)

1. **B1 untrusted content** — benchmark YAML (validated at load: unknown
   evaluators/keys/threshold ranges rejected), dataset JSONL (structural +
   semantic validation), agent answers (deterministic evaluators are pure
   functions of gold expectations).
2. **B2 operator-configured egress** — live judge endpoint
   (OPENAI_BASE_URL/JUDGE_MODEL/API key). Network guard blocks NEW socket
   creation for the whole run; the block is lifted ONLY inside
   `guard.allowed()` windows (the runner's evaluator phase) so authorized
   judge HTTP works while agent code stays blocked; `socket.socket(fileno=…)`
   wraps of existing fds are allowed (accept paths) — creating a connection
   is always blocked for agent code.
3. **B3 in-process agent code** — arbitrary user-supplied `*.py:attr` agents
   run with test privileges. Documented honestly: the guard is best-effort
   (cannot constrain ctypes/os tricks); the container (non-root `aeh:10001`)
   is the real isolation boundary.

## 2. Verified controls (each with a test)

| Control | Test |
|---|---|
| network guard blocks new sockets during runs | test_network_guard_blocks_socket; guard.allowed window semantics; attempts recorded, authorized traffic not |
| live judge can evaluate only in the evaluator window (trusted code) | local HTTP double serves live verdicts during a sandboxed run; agent-phase stays blocked |
| servers accept during guarded runs (fileno wrap) | pre-established connection served while guard active |
| tool permissions: allow/deny lists, forbidden args, repeated-denial violation | permissions-block benchmark runs + gateway enforcement test (F-12) |
| offline-by-construction tools; no subprocess imports in harness modules (static) | test_no_subprocess_or_network_imports_in_harness |
| secret redaction at export boundary + repo-wide strict scan | test_redaction_*; scan_secrets clean (CI-enforced) |
| injection screening (detect-and-audit, never silently drop) | test_injection_screening / sanitize |
| run-record integrity: deterministic v2 ids + atomic persist | overwrite regression (F-01); sentinel-crash test (F-10) |
| regression gates fail closed on insufficient data and on incompatible evidence | F-02/F-03 test matrices |
| dashboard: read-only viewer refuses execution (503); strict input validation (4xx); 1 MiB body cap (413); same-origin (no ACAO:*); nosniff; stored-XSS escaped via esc() + data-run-id delegation (no inline onclick) | F-09 test set |
| CLI minimal install works without rich | F-11 (unit + subprocess) |
| clean-room release validation (hashes, tests, demo, secrets, regeneration) | validate_release ALL 9 PASS |

## 3. Prompt injection

Tasks/tool outputs may carry directives (adversarial category,
`fixture://internal/notes`). Policy unchanged and verified: detect and audit,
never silently drop — the agent still observes the text; whether it *follows*
is what the adversarial cases measure. Deviating agents hit gateway denials
(audit-logged) and fail task checks. The live judge prompt embeds task text
(end noted residual): a hijacked judge can only produce verdicts that pass the
response contract — internally-consistent valid verdicts are indistinguishable
at this layer; the rubric fallback is deterministic and auditable, and judge
traffic is operator-configured (B2), not agent-reachable.

## 4. Residual risks (accepted, documented)

- In-process guard bypass (ctypes/os) for B3 agents — container is the boundary.
- Live-judge prompt-level hijack — contract + fallback + provenance recorded
  (backend/model/prompt sha per result).
- Pattern-based redaction can miss exotic secret formats (documented; strict
  scan in CI).
- pip-audit advisory (explicit decision; transitive advisories reported).
- Dashboard is a single-operator ops tool (serialized executions); must not be
  exposed to untrusted networks; default bind 127.0.0.1; docker exposure is the
  read-only viewer mode only.
- Docker image/compose runtime NOT VERIFIED in this environment (no docker CLI);
  compose YAML validated; non-root user config unchanged.

## 5. Security recommendations (roadmap)

1. OS-level agent isolation (gVisor/namespace per run) for multi-tenant use.
2. Sign run records + baselines (commit signing exists; add record signatures).
3. Judge egress allowlist (explicit host pinning beyond base_url).
4. Dashboard authn/authz if ever exposed beyond loopback.
5. Make pip-audit blocking once advisories are triaged to zero.
