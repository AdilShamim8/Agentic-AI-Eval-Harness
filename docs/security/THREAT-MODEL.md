# Threat Model — agent-eval-harness evaluation infrastructure

Scope: the evaluation platform itself. Assets: benchmark datasets, run records
(event logs), judge prompts, baselines/gates, the CI quality-gate decision, and
the host running the evaluation.

## 1. Trust boundaries

```
[benchmark author] --(YAML/JSONL)--> [harness] --(in-process)--> [tools/fixtures]
[agent author] ----(python module)-> [harness in-process execution]
[live judge] <----(HTTPS, opt-in)---- [harness]
```

Boundaries: (B1) benchmark/agent inputs are UNTRUSTED content; (B2) the live
judge endpoint is an external service; (B3) arbitrary agent code executes
in-process with test privileges — outside the v0.1 sandbox (documented).

## 2. STRIDE analysis

| Threat | Vector | Control | Residual |
|---|---|---|---|
| Spoofing | fake run records passed to `regression` gate | run_id = hash(manifest inputs); version bundle in every record | records are files — protect the repo branch |
| Tampering | malicious benchmark YAML (limits=∞, no gates) | schema validation at load; unknown keys/evaluators rejected | thresholds are author-chosen — review in PR |
| Tampering | evaluator manipulated by adversarial answer | deterministic evaluators are pure functions; judge uses gold only; judge metadata recorded | live judge prompt-injection possible — rubric fallback auditable |
| Repudiation | "the gate passed yesterday" | run records + events + versions persisted per run; CI logs | none for committed artifacts |
| Info disclosure | secrets leaked via traces/events | redaction at export boundary (sk-/ghp_/AKIA/bearer/assignments); audit count; `scan_secrets.py --strict` in CI | redaction is pattern-based — exotic formats can evade |
| DoS | infinite agent loops, huge outputs | step/tool/time/output/state caps; loop detection; per-case budgets; post-hoc per-call timeout check | timeouts are cooperative (no preemption) — bounded, not instant |
| Elevation | agent calls dangerous tools | tool registry is offline-only; allow/deny lists; forbidden-arg keys; network guard blocks sockets; no subprocess imports (statically tested); multi-stage Docker container runs as non-root `aeh` (UID 10001) | in-process agent code (B3): isolation enforced in container runtime |
| Exposure | unauthorized access to Web UI / REST API | `agent-eval serve` binds exclusively to `127.0.0.1` (localhost loopback) by default; endpoint parameters strictly parsed; read-only default views | remote exposure requires explicit operator port binding (`0.0.0.0`) |

## 3. Prompt-injection handling

Benchmark tasks and tool outputs may contain injection directives (adversarial
category + the fixture page `fixture://internal/notes`). Policy: **detect and
audit, never silently drop** — the agent still observes the text; whether it
*follows* the injection is exactly what the adversarial cases measure. Deviating
agents hit case-level forbidden-tool denials at the gateway (audit-logged) and
fail task checks. Agent resistance is a measured property, not an assumption.

## 4. Reproducibility as a security property

Deterministic seeds + content-hashed datasets make runs replayable; any drift
between recorded and re-executed results indicates tampering or environment
change — surfaced by version-bundle fingerprints and dataset sha256 checks.
Cryptographic integrity is preserved cross-platform via LF newline normalization.

## 5. Security Evolution (v0.2.1 Additions)

- **Rootless Container Isolation (addressed from v0.1 scope):** Enterprise Dockerfile
  implements multi-stage build dropping all root privileges to non-root user `aeh`
  (UID 10001, GID 10001) with explicit read/write volume isolation.
- **Localhost Loopback Server Default:** `agent-eval serve` listens on `127.0.0.1`
  to prevent accidental intranet exposure on developer machines or CI nodes.
- **Out of scope:** Multi-tenant SaaS hosting, live-LLM jailbreak red-teaming,
  DDoS of external judge endpoints.

## 6. Verification

Every control row above maps to a test: `tests/unit/test_security_basics.py`
(redaction, injection, sandbox, static imports), harness permission tests in
`tests/integration/test_harness_and_adapters.py`, failure-injection suite,
web server security tests in `tests/unit/test_web_server.py`,
and CI `security.yml` (secret scan + gitleaks + injection evaluation).
