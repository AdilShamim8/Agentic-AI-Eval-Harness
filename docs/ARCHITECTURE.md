# Architecture — agent-eval-harness v0.2.1

Diagrams: `diagrams/*.mmd` (Mermaid, render on GitHub). This document is the textual
source of truth.

## 1. Layered view

```
CLI (cli/) ── pytest bridge (pytest_plugin.py) ── Web Dashboard (web/server.py)
  │
Operations & Commands: run / ablate / calibrate / repro / regression / compare / status / serve
  │
Runner (runner/)  ── Benchmark Registry (registry/)  ── Datasets (datasets/*.jsonl)
  │ per case: fresh Environment
Harness (harness/)  = Execution Environment
  ├─ ToolGateway (permissions, validation, limits, retries, fault injection)
  ├─ VerificationLayer (output/arg checks, retry orchestration)   [ablatable]
  ├─ ContextOptimizer (observation trimming/dedup)                 [ablatable]
  └─ ResourceGuards (steps, tool calls, wall clock, output/state bytes, network)
Agents (agents/)  = unit under test
  ├─ ModelBackend protocol  ── ScriptedModel (deterministic) | LiveBackends
  ├─ 5 pattern agents (ReAct, Plan-Execute, Supervisor, Swarm, Map-Reduce)
  └─ Adapters (LangGraph / OpenAI Agents SDK / CrewAI)
Evaluators (evaluators/)  = deterministic + llm_judge + trajectory
Metrics (metrics/)  →  Comparison (comparison/)  →  Regression engine (regression/)
Reporting (reporting/)  = Markdown + JSON + Web UI  ← Observability event stream (observability/)
Security (security/)  = policy, injection screen, redaction, network guard, audit
Deployment (infra/)  = Dockerfile (multi-stage, non-root) + docker-compose (runner/dashboard/status)
```

## 2. Execution flow per case (the core loop)

1. Runner loads benchmark (registry) + dataset slice; validates.
2. Environment constructed per case: limits + policy + ablation profile + fault
   schedule + fresh KV store + event recorder; network guard armed.
3. Agent adapter runs inside the environment via `RunContext` (gateway + events +
   model backend + limits). Every decision/tool call/state change emits an event.
4. Agent outcome -> AgentResult (trajectory, final answer, failure class).
5. Evaluators run in isolation (exceptions -> EVALUATOR_ERROR, run continues).
6. Verdict per case; metrics aggregate; run record + event log persisted (redacted).

## 3. Key contracts

- `AgentAdapter.run(ctx) -> AgentRunOutcome` — framework-agnostic entry.
- `ModelBackend.decide(state) -> ModelDecision` — Think|Plan|ToolCallDecision|
  Handoff|FinalAnswer|Malformed.
- `Evaluator.evaluate(case, result) -> EvaluationResult` — name, version, score [0,1],
  passed, details, error.
- `AblationProfile` — flags {verification, retry, tool_validation, context_optimization}.
- `FailureClass` — NONE|TEST_FAILURE|AGENT_ERROR|EVALUATOR_ERROR|INFRASTRUCTURE_FAILURE|
  SECURITY_VIOLATION|TIMEOUT|STEP_LIMIT|TOOL_LIMIT|LOOP_DETECTED.
- `VersionBundle` — agent/model/harness/benchmark/dataset(+sha256)/evaluator/prompt/
  environment versions recorded in every run manifest.

## 4. Determinism & reproducibility design

- Single seeded RNG stream per case (seed derived from run seed + case id hash).
- No wall-clock in scores; latency measured but never influencing decisions.
- Ordered dict serialization (sort_keys=True) for byte-identical run records.
- run_id = sha256(benchmark|agent|seed|ablation|dataset_sha) — replayable identity.
- Event timestamps are recorded metadata (excluded from run_id preimage).
- Cross-platform determinism: .gitattributes enforces LF line endings; dataset hashing normalizes CRLF to LF; stdout reconfigures to UTF-8 on Windows.

## 5. Security architecture

Belt-and-suspenders: (a) tools are offline fixtures by construction; (b) tool
allowlist + forbidden-arg guards at the gateway; (c) socket guard raises
SecurityViolation if anything opens a network socket during a run; (d) injection
screening flags adversarial text in tasks and tool outputs (audit-logged, never
silently dropped); (e) secret redaction at export; (f) resource caps bound worst
case; (g) audit JSONL; (h) production container runs as non-root user (UID 10001). Arbitrary user agent code is explicitly OUT of the sandbox
threat boundary in v0.1 (documented in THREAT-MODEL.md §trust boundaries).

## 6. Extension points

- New evaluator: subclass Evaluator, register in EVALUATORS registry.
- New tool: ToolSpec + register; gateway picks up permissions from policy.
- New agent runtime: implement AgentAdapter (see adapters/ for three worked examples).
- Live model backend: implement ModelBackend; runner accepts `--model spec`.
- Web Dashboard & API: custom endpoints in `web/server.py` or consume REST JSON via `/api/runs`.
- OTLP exporter: subscribe to the event recorder (documented, not implemented).
