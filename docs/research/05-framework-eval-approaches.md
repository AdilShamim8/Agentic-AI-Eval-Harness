# Research 05 — Framework Evaluation Approaches (LangGraph / OpenAI Agents SDK / CrewAI)

Date: 2026-09-12 · Status: complete · Informs: agents/adapters/*

## 1. LangGraph

- Evaluation story: LangSmith datasets + evaluators run against graph invocations;
  trajectories are the LangSmith trace of nodes/edges.
- Integration surface for a neutral harness: a `CompiledGraph.invoke(state)` with a
  state dict (typically `messages` + custom keys). Node names map to trace steps;
  `ToolNode` executions map to tool calls.
- Adapter design: wrap graph invocation, translate returned message list +
  state deltas into our Trajectory (steps + tool calls). Loop control stays the
  graph's own (`recursion_limit`) — our harness wraps it with wall-clock timeout and
  records the mapping in trace metadata.
- Risk: state schema variance across user graphs. Mitigation: adapter accepts a
  `state_schema` mapper (function hooks) with a default `messages` mapping.

## 2. OpenAI Agents SDK

- `Agent` + `Runner.run(agent, input, tools)`; tool calls surface as run items;
  handoffs are first-class (maps to our Swarm handoff steps).
- Adapter design: implement our AgentAdapter over `Runner`; convert run items to
  steps/tool calls; guard import (`openai_agents`).
- Notes: guardrail/handoff events are directly mappable to our behavioral taxonomy
  (termination, handoff). The SDK's own session state maps to our per-case state
  store.

## 3. CrewAI

- `Crew.kickoff()` with tasks and agents; output = CrewOutput with per-task results.
- Adapter design: crew tasks -> sequential/supervisor pattern steps; tool usage inside
  tasks maps to tool calls (when tools are our ToolSpec instances, capture is
  automatic; otherwise adapter records per-task outputs as steps only, flagged
  `tool_visibility=partial`).
- Honest limitation: without using our tools inside the crew, tool-level trajectory
  capture is partial. Documented in adapter docstring.

## 4. Adapter protocol (framework-agnostic core)

```
AgentAdapter:
    id, pattern, describe()
    run(ctx: RunContext) -> AgentRunOutcome
RunContext provides:
    task, context, tool gateway (permissioned), event sink, limits, model backend?
```

Built-in pattern agents consume our ModelBackend (scripted or any LLM-backed
implementation). Framework adapters translate foreign runtimes INTO this protocol.
Both paths produce identical Trace/Trajectory schemas, so evaluators are
runtime-agnostic. This is the central architectural decision enabling "pytest for
agents" across frameworks.

## 5. Support status (honest)

- Built-in pattern agents (5): implemented, fully exercised in this release on the
  deterministic backend; live-LLM backend usage: Not measured yet.
- LangGraph adapter: implemented + tested against a stub compiled-graph object
  implementing the invoke/messages interface (langgraph not installed in build env).
  Real-graph integration: Not measured yet.
- OpenAI Agents SDK adapter: implemented + stub-tested (SDK not installed).
- CrewAI adapter: implemented + stub-tested (crewai not installed).
All adapters import-guard their framework and raise a clear error when missing.
