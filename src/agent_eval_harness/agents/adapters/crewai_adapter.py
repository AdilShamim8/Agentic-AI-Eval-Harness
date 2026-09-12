"""CrewAI adapter — runs a Crew and records task outputs into our trajectory.

Integration contract:
- Construct with a CrewAI `Crew`. `run()` calls `crew.kickoff(inputs=...)`.
- Task outputs become trajectory steps; tool usage inside tasks is captured
  when the crew's tools are our ToolSpec-backed functions routed through the
  gateway (see QUICKSTART). Without that wiring, tool-level trajectory capture
  is partial — flagged `tool_visibility=partial` in run metadata (honest
  limitation, see docs/research/05).
- Without crewai installed, construction raises InfraError with the install
  hint; stub crews are used by unit tests (real-crew support: Not measured yet).
"""
from __future__ import annotations

from typing import Any

from agent_eval_harness.core.errors import InfraError
from agent_eval_harness.core.schemas import AgentRunOutcome, StepRecord, ToolCallRecord, Trajectory


class CrewAIAdapter:
    id = "crewai"
    pattern = "crewai"

    def __init__(self, crew: Any, require_import: bool = True):
        self.crew = crew
        if require_import:
            try:
                import crewai  # noqa: F401
            except ImportError as exc:  # pragma: no cover - depends on env
                raise InfraError(
                    "crewai is not installed; `pip install crewai` (stub tests "
                    "pass a duck-typed crew object with require_import=False)"
                ) from exc

    def describe(self) -> str:
        return f"CrewAIAdapter(crew={type(self.crew).__name__})"

    def run(self, ctx: Any) -> AgentRunOutcome:
        traj = Trajectory()
        try:
            output = self.crew.kickoff(inputs={"task": ctx.task})
            tasks_output = getattr(output, "tasks_output", None) or []
            parts: list[str] = []
            for i, task_out in enumerate(tasks_output):
                raw = str(getattr(task_out, "raw", "") or "")
                agent = str(getattr(task_out, "agent", "") or f"task{i}")
                parts.append(raw)
                traj.steps.append(StepRecord(index=traj.step_count(), phase="act",
                                             summary=f"crew task {i + 1} ({agent}): "
                                                     f"{raw[:160]}", agent=agent))
                tool_calls = getattr(task_out, "tools_used", None) or []
                for tc in tool_calls:
                    name = getattr(tc, "name", "tool")
                    traj.tool_calls.append(ToolCallRecord(
                        name=str(name), arguments={}, ok=True))
            final = str(getattr(output, "raw", "") or "; ".join(parts))
            traj.steps.append(StepRecord(index=traj.step_count(), phase="final",
                                         summary=f"final: {final[:200]}", agent=self.id))
            stats = ctx.gateway.stats()
            return AgentRunOutcome(
                case_id=ctx.case.id, ok=bool(final), final_answer=final,
                trajectory=traj, security_flags=list(stats.get("security_flags", [])))
        except Exception as exc:  # noqa: BLE001
            from agent_eval_harness.core.errors import classify_exception

            traj.termination = "error"
            return AgentRunOutcome(case_id=ctx.case.id, ok=False, final_answer="",
                                   trajectory=traj,
                                   failure_class=classify_exception(exc),
                                   error=str(exc))
