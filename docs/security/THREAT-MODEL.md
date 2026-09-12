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
| Elevation | agent calls dangerous tools | tool registry is offline-only; allow/deny lists; forbidden-arg keys; network guard blocks sockets; no subprocess imports (statically tested) | in-process agent code (B3): run untrusted agents in a container |

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

## 5. Out of scope (v0.1)

Multi-tenant hosting, sandboxed execution of untrusted agent code (container
isolation), live-LLM jailbreak red-teaming, DDoS of the judge endpoint.

## 6. Verification

Every control row above maps to a test: `tests/unit/test_security_basics.py`
(redaction, injection, sandbox, static imports), harness permission tests in
`tests/integration/test_harness_and_adapters.py`, failure-injection suite,
and CI `security.yml` (secret scan + gitleaks + injection evaluation).
