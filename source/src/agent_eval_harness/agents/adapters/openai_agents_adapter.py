"""OpenAI Agents SDK adapter — records SDK run items into our trajectory.

Integration contract:
- Construct with an SDK `Agent` and a runner callable (defaults to
  `openai_agents.Runner.run_sync` when the SDK is importable).
- To route tools through the harness gateway, build the SDK agent with tools
  whose invocation functions call the gateway (see QUICKSTART). Tool items are
  translated into ToolCallRecords; handoff items into trajectory.handoffs.
- Without the SDK installed, construction raises InfraError with the install
  hint; a stub runner is used by unit tests (real-SDK support: Not measured
  yet).
"""
from __future__ import annotations

from typing import Any, Callable

from agent_eval_harness.core.errors import InfraError
from agent_eval_harness.core.schemas import AgentRunOutcome, StepRecord, ToolCallRecord, Trajectory


class OpenAIAgentsAdapter:
    id = "openai_agents"
    pattern = "openai_agents"

    def __init__(self, agent_obj: Any, runner_fn: Callable[..., Any] | None = None):
        self.agent_obj = agent_obj
        if runner_fn is None:
            try:
                from openai_agents import Runner  # type: ignore

                runner_fn = Runner.run_sync
            except ImportError as exc:  # pragma: no cover - depends on env
                raise InfraError(
                    "openai-agents is not installed; `pip install openai-agents` "
                    "or pass runner_fn explicitly (stub tests do)") from exc
        self.runner_fn = runner_fn

    def describe(self) -> str:
        return f"OpenAIAgentsAdapter(agent={type(self.agent_obj).__name__})"

    def run(self, ctx: Any) -> AgentRunOutcome:
        traj = Trajectory()
        try:
            run = self.runner_fn(self.agent_obj, ctx.task)
            items = list(getattr(run, "new_items", []) or [])
            final = str(getattr(run, "final_output", "") or "")
            for item in items:
                kind = type(item).__name__.lower().replace("_", "")
                if "toolcall" in kind and "output" not in kind:
                    name = getattr(item, "name", "") or getattr(
                        getattr(item, "tool_call", None), "name", kind)
                    args = getattr(item, "arguments", None) or getattr(
                        getattr(item, "tool_call", None), "arguments", {}) or {}
                    if isinstance(args, str):
                        import json

                        try:
                            args = json.loads(args)
                        except ValueError:
                            args = {"_raw": args}
                    traj.tool_calls.append(ToolCallRecord(
                        name=str(name), arguments=dict(args), ok=True))
                    traj.steps.append(StepRecord(
                        index=traj.step_count(), phase="act",
                        summary=f"tool {name}", agent=self.id))
                elif "handoff" in kind:
                    target = getattr(item, "target_agent", None) or getattr(
                        item, "to", "?")
                    traj.handoffs.append({"from": self.id, "to": str(target),
                                          "reason": "sdk handoff"})
                elif "message" in kind:
                    traj.steps.append(StepRecord(
                        index=traj.step_count(), phase="think",
                        summary=str(getattr(item, "content", ""))[:200], agent=self.id))
            traj.steps.append(StepRecord(index=traj.step_count(), phase="final",
                                         summary=f"final: {final[:200]}", agent=self.id))
            stats = ctx.gateway.stats()
            return AgentRunOutcome(
                case_id=ctx.case.id, ok=bool(final), final_answer=final,
                trajectory=traj, security_flags=list(stats.get("security_flags", [])))
        except Exception as exc:  # noqa: BLE001
            from agent_eval_harness.core.errors import FailureClass, classify_exception

            traj.termination = "error"
            return AgentRunOutcome(case_id=ctx.case.id, ok=False, final_answer="",
                                   trajectory=traj,
                                   failure_class=classify_exception(exc),
                                   error=str(exc))
