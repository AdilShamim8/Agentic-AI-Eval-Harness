# Research 04 — Agent Observability Landscape

Date: 2026-09-12 · Status: complete · Informs: observability/, reporting, versioning

## 1. Tools reviewed

- **LangSmith** (LangChain): tracing-first, deep LangGraph integration, dataset +
  evaluation + annotation loops, ablations. Closed SaaS; evaluation coupled to their
  execution runtime; weak framework-agnostic story.
- **Langfuse** (open-source, self-hostable): traces, scores, prompt management,
  datasets, OSS-friendly. Evaluation is score-attachment oriented; regression gates
  and CI quality-gate semantics are left to the user.
- **OpenTelemetry / OpenInference**: vendor-neutral trace semantics (spans:
  LLM, tool, chain, agent). Right substrate for export; not an evaluation system.
- **Arize Phoenix**: tracing + evals, notebooks-first; strong for exploration,
  weaker for reproducible CI gates.
- **MLflow**: experiment tracking lineage; agent-behavioral metrics bolt-on via
  custom metrics; no trajectory schema.
- **promptfoo / DeepEval / RAGAS**: assertion-centric (single prompt/turn), limited
  multi-step trajectory semantics; DeepEval has LLM-judge metrics with some
  reliability stats (good pattern: metric-level reliability reporting).

## 2. Patterns adopted

- **Structured event stream** per run (JSONL): run_start, case_start, agent_step,
  tool_call, tool_result, evaluator_start/end, case_end, run_end. Same lifecycle
  stages as LangSmith/Langfuse, but file-based, dependency-free, replayable.
- **Run manifest**: every run records a VersionBundle (agent, model/backend, harness,
  benchmark, dataset incl. content sha256, evaluator, prompt versions, environment)
  plus config + seed. Reproduction = manifest + command line.
- **Deterministic IDs**: run_id = hash(manifest inputs), trace_id = hash(run_id,
  case_id) — replayable correlation without a database.
- **Redaction at export boundary**: secrets scrubbed when events leave memory
  (patterns: api keys, bearer tokens, passwords); audit log for security events
  (permission denials, injection flags, resource caps).

## 3. Weaknesses found / our response

| Weakness in landscape | Our response |
|---|---|
| Eval results live in proprietary UIs | File-based run records + Markdown/JSON reports in repo |
| Regression gates require custom glue | `agent-eval regression` command with exit codes for CI |
| Tracing schemas are heavy (protobuf/OTLP) | Minimal typed JSON events; OTLP export documented as extension point (not implemented, honestly marked) |
| Cost attribution per case rare | Per-case token estimates + simulated price table, labeled `estimate` |

## 4. Not adopted (v0.1)

Live OTLP export, web dashboards, online annotation stores. Rationale: this is an
evaluation **harness**, not an observability SaaS; the event schema is designed so an
OTLP exporter can be added without schema changes (events are already span-like:
name, ts, ids, attributes).
