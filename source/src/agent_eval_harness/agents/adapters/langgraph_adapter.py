"""LangGraph adapter — runs a LangGraph compiled graph inside our harness.

Integration contract (see docs/research/05-framework-eval-approaches.md):
- The graph is invoked STEPWISE via `graph.stream(state)`; every tool_call the
  graph emits is executed through OUR ToolGateway (permissions, validation,
  limits, retries, fault injection, tracing all apply), and the ToolMessage
  result is fed back into the state for the next iteration.
- Loop control remains ours: step/tool caps from the benchmark's execution
  settings terminate runaway graphs (in addition to LangGraph's own
  recursion_limit).
- Message format tolerance: accepts objects with `.tool_calls` / `.content` or
  plain dicts with the same keys (a stub graph implementing this interface is
  used by unit tests when langgraph is not installed — support status of a
  real graph: Not measured yet).
"""
from __future__ import annotations

from typing import Any

from agent_eval_harness.agents.base import RunContext
from agent_eval_harness.agents.tools import ToolResult
from agent_eval_harness.core.errors import InfraError
from agent_eval_harness.core.schemas import AgentRunOutcome, StepRecord, ToolCallRecord, Trajectory


def _require_langgraph() -> None:
    try:
        import langgraph  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on env
        raise InfraError(
            "langgraph is not installed; install with `pip install langgraph` "
            "or use builtin: agents on the scripted backend") from exc


def _msg_field(msg: Any, field: str) -> Any:
    if isinstance(msg, dict):
        return msg.get(field)
    return getattr(msg, field, None)


class LangGraphAdapter:
    id = "langgraph"
    pattern = "langgraph"

    def __init__(self, graph: Any, agent_id: str = "langgraph_agent",
                 state_key: str = "messages", require_import: bool = True):
        if require_import:
            _require_langgraph()
        self.graph = graph
        self.id = agent_id
        self.state_key = state_key

    def describe(self) -> str:
        return f"LangGraphAdapter(graph={type(self.graph).__name__})"

    def run(self, ctx: RunContext) -> AgentRunOutcome:
        traj = Trajectory()
        state: dict[str, Any] = {self.state_key: [
            {"role": "user", "content": ctx.task}]}
        max_steps = ctx.case.max_steps or 12
        try:
            for step in range(max_steps):
                events: list[Any] = []
                for item in self.graph.stream(state):
                    events.append(item[1] if isinstance(item, tuple) else item)
                if not events:
                    return self._finish(ctx, traj, "error", "", "graph produced no events")
                last = events[-1]
                messages = self._messages_of(last)
                tool_calls = self._tool_calls_of(messages)
                if not tool_calls:
                    content = self._last_ai_content(messages)
                    traj.steps.append(StepRecord(index=traj.step_count(), phase="final",
                                                 summary=f"final: {str(content)[:200]}",
                                                 agent=self.id))
                    return self._finish(ctx, traj, "answer", str(content or ""))
                for name, args in tool_calls:
                    if ctx.gateway.remaining_tool_budget() <= 0:
                        traj.termination = "tool_limit"
                        return self._finish(ctx, traj, "tool_limit", "")
                    res: ToolResult = ctx.gateway.call(name, dict(args or {}))
                    traj.tool_calls.append(ToolCallRecord(
                        name=name, arguments=dict(args or {}), ok=res.ok,
                        value=res.value, error=res.error))
                    traj.steps.append(StepRecord(
                        index=traj.step_count(), phase="act",
                        summary=f"tool {name} -> {'ok' if res.ok else 'error'}",
                        agent=self.id))
                    state[self.state_key].append({
                        "role": "tool", "name": name,
                        "content": str(res.value if res.ok else res.error)})
            traj.termination = "step_limit"
            return self._finish(ctx, traj, "step_limit", "")
        except Exception as exc:  # noqa: BLE001 - classified
            from agent_eval_harness.core.errors import classify_exception

            fc = classify_exception(exc)
            traj.termination = "error"
            return self._finish(ctx, traj, "error", "", str(exc), fc)

    # -- helpers -----------------------------------------------------------
    def _messages_of(self, chunk: Any) -> list[Any]:
        if isinstance(chunk, dict):
            msgs = chunk.get(self.state_key) or chunk.get("messages") or []
        else:
            msgs = getattr(chunk, self.state_key, None) or getattr(chunk, "messages", [])
        return list(msgs) if isinstance(msgs, list) else []

    def _tool_calls_of(self, messages: list[Any]) -> list[tuple[str, dict]]:
        calls: list[tuple[str, dict]] = []
        for msg in messages:
            tcs = _msg_field(msg, "tool_calls")
            if not tcs:
                continue
            for tc in tcs:
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                    calls.append((fn.get("name", tc.get("name", "")),
                                  fn.get("arguments", tc.get("args", {})) or {}))
                else:
                    calls.append((getattr(tc, "name", ""),
                                  getattr(tc, "args", {}) or {}))
        return calls

    def _last_ai_content(self, messages: list[Any]) -> Any:
        for msg in reversed(messages):
            role = _msg_field(msg, "role") or _msg_field(msg, "type")
            if role in (None, "ai", "assistant"):
                content = _msg_field(msg, "content")
                if content:
                    return content
        return ""

    def _finish(self, ctx: RunContext, traj: Trajectory, termination: str,
                answer: str, error: str = "", fc=None) -> AgentRunOutcome:
        from agent_eval_harness.core.errors import FailureClass

        traj.termination = termination
        stats = ctx.gateway.stats()
        return AgentRunOutcome(
            case_id=ctx.case.id, ok=termination == "answer" and not error,
            final_answer=answer, trajectory=traj,
            failure_class=fc or FailureClass.NONE, error=error,
            tokens_in_est=stats.get("tokens_in_est", 0),
            tokens_out_est=stats.get("tokens_out_est", 0),
            security_flags=list(stats.get("security_flags", [])),
            retried_calls=stats.get("retried_calls", 0),
            recovered_from_fault=stats.get("recovered_from_fault", False),
            fault_injected=stats.get("fault_injected", False),
        )
