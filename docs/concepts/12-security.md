# Security of the Evaluation Infrastructure

## Why
An eval platform executes semi-trusted code and processes adversarial
content; a compromised gate silently approves bad agents. Threat-model the
instrument itself.

## How
Controls (each with a test): tool allow/deny lists + case-level forbidden
tools at the gateway; forbidden-arg keys (cmd/shell/exec); arg/output length
caps; NetworkGuard patches socket.socket during runs; tools are offline
fixtures by construction (static import scan forbids subprocess/eval/exec in
harness modules); injection screening on tasks AND tool outputs (flag +
audit, never silently dropped); redaction at every export; resource caps
(steps/calls/time/bytes); audit JSONL. See docs/security/THREAT-MODEL.md for
the full STRIDE table.

## Trade-offs
- Detect-and-audit vs sanitize-by-default for injections: sanitizing changes
  what the agent sees and would falsify the adversarial measurement;
  detection + gateway denials keep the measurement honest.
- In-process agent execution (v0.1) vs container isolation: documented
  boundary; container is the deployment answer for untrusted agents.

## Failure modes
- Pattern-based redaction misses exotic secret formats (residual, documented).
- Cooperative timeouts bound but do not preempt runaway native code.

## Experimental evidence
Tests: network guard raises SecurityViolation on socket use; repeated denials
escalate to SECURITY_VIOLATION; adversarial deviation attempts are denied and
audited; secret scan is clean; injection events recorded for flagged tool
outputs (fixture://internal/notes page).
