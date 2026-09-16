# Observability

## Why
When a case fails at 2am, the question is "which layer broke". Event logs
that replay the full lifecycle turn debugging from archaeology into reading.

## How
Every run emits a JSONL event stream: run_start → case_start → tool_call →
tool_result → evaluator_start/end → case_end → run_end, plus security events
(denials, injection flags) and fault injections. Exports are redacted
(pattern-based secret scrubbing with a redaction count). Run records embed
the VersionBundle (8 components) + config + seed + command line for exact
reproduction. IDs are deterministic (run_id = hash of semantic inputs), so
correlation needs no database.

For interactive visualization, `agent-eval serve` launches a zero-dependency
embedded web server on port 8000. It reads committed and local run records,
rendering pass-rate comparison cards, failure localization taxonomy, and
observable step-by-step trajectory replay (thought, plan, action, observation,
and final answer) directly in any modern browser. A REST API (`/api/status`,
`/api/runs`, `/api/benchmarks`, `/api/run`) enables programmatic query and execution.

## Trade-offs
- File-based JSONL vs OTLP/tracing backend: files are git-reviewable and
  replayable; the event schema is deliberately span-like so an OTLP exporter
  can be added without schema surgery.
- Embedded zero-dependency HTTP server vs third-party SPA framework: avoids
  adding Node.js/npm or heavy Python dependencies (FastAPI, uvicorn), preserving
  instant clean-clone usability while providing rich visual trajectory replay.
- Event volume vs completeness: per-case events are bounded by step caps.

## Failure modes
- Secrets riding inside payload strings — redaction at the export boundary,
  verified by test (fake sk- key injected into context, absent in export).
- Wall-clock timestamps breaking determinism — excluded from run identity.

## Experimental evidence
Every run writes its events file (asserted in e2e tests); the 89.3%→75.0%
regression demo is fully reconstructable from
evals/runs/<id>.events.jsonl.
