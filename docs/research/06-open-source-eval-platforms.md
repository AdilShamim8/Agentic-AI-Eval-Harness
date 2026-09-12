# Research 06 — Open-Source Evaluation Platforms Compared

Date: 2026-09-12 · Status: complete · Informs: positioning, non-goals

| Platform | Focus | Trajectory eval | CI gates | Determinism | Multi-framework | Verdict for us |
|---|---|---|---|---|---|---|
| DeepEval | LLM test metrics (pytest-style) | Partial (tool-correctness metric) | Yes (pytest exit codes) | Judge-dependent | Prompt-centric | Borrow: pytest ergonomics, metric reliability stats |
| promptfoo | Prompt A/B assertions | No (single-turn) | Yes | Good for deterministic asserts | Prompt-centric | Borrow: config-driven asserts, matrixRedacts |
| RAGAS | RAG quality | No | Weak | Judge-centric | RAG-only | Out of scope |
| Langfuse | Tracing + scores | Trace-view yes, eval no | DIY | DIY | Good via SDKs | Borrow: event lifecycle, prompt mgmt |
| Inspect AI (UK AISI) | Task/eval harness for models+agents | Solver traces, scorers | Yes (CLI) | Strong (seeding) | Own agent runtime | Borrow: Task/Solver/Separator separation, sandbox stance |
| LangSmith | Full loop (SaaS) | Yes | Enterprise tiers | Seeded datasets | LangChain-centric | Borrow: dataset+annotation loop UX |
| OpenAI Evals | Model benchmarks | Logprob/custom | Yes | Partial | OpenAI-centric | Borrow: regression reporting rigor |

## Synthesis — what none of them give us

1. **Harness ablation** as a first-class experiment (attribute performance to retry /
   verification / tool-validation / context-optimization features). Inspect comes
   closest with solver composition; still not ablation-focused.
2. **Schema-level failure taxonomy** separating TEST FAILURE vs EVALUATOR ERROR vs
   INFRASTRUCTURE FAILURE across the whole pipeline (DeepEval conflates in pytest
   reports; Langfuse separates traces but not gate semantics).
3. **Framework-agnostic agent adapter protocol** spanning LangGraph / OpenAI Agents /
   CrewAI / custom with one trajectory schema (each vendor optimizes their own).
4. **Offline-first reproducibility**: byte-identical reruns from committed datasets,
   seeds, and versioned prompts without SaaS (Inspect strong here; not multi-framework).

## Positioning

`agent-eval-harness` = the missing CI-grade layer: deterministic-first evaluators,
trajectory/behavioral metrics, harness ablations, regression gates, and packaging as
engineering evidence — runnable offline, wireable into any CI, extensible to any agent
runtime via the adapter protocol. We do not compete on tracing UIs or annotation
workflows (Langfuse/LangSmith remain complementary exporters of our event stream).

## Explicit non-goals (from this survey)

Web dashboards, SaaS hosting, annotation marketplaces, model-leaderboard hosting,
live production monitoring.
