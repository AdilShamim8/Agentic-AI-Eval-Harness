"""Swarm pattern agent — specialist handoff chain with a coordinator."""
from __future__ import annotations

from agent_eval_harness.agents.base import BasePatternAgent, RunContext
from agent_eval_harness.agents.model import Action, ModelState
from agent_eval_harness.core.errors import HarnessError
from agent_eval_harness.core.schemas import AgentRunOutcome, StepRecord, Trajectory

_SPECIALIST_BY_TOOL = {
    "calculator": "compute_specialist",
    "data_calc": "compute_specialist",
    "knowledge_search": "research_specialist",
    "sim_web_get": "research_specialist",
    "text_stats": "writing_specialist",
    "text_transform": "writing_specialist",
    "summarize": "writing_specialist",
    "store_set": "memory_specialist",
    "store_get": "memory_specialist",
}


class SwarmAgent(BasePatternAgent):
    pattern = "swarm"

    def run(self, ctx: RunContext) -> AgentRunOutcome:
        traj = Trajectory()
        try:
            understanding = ctx.model.understand(ctx.task, ctx.context)
            actions = list(understanding.actions)
            if ctx.case.injection and not self._resists(ctx):
                actions = [Action("tool", "store_set",
                                  {"key": "exfiltrate", "value": "all report data"})]

            observations: list[dict] = []
            for i, action in enumerate(actions):
                specialist = _SPECIALIST_BY_TOOL.get(action.tool, "research_specialist")
                traj.handoffs.append({"from": "coordinator", "to": specialist,
                                      "reason": f"subtask {i + 1}"})
                traj.steps.append(StepRecord(
                    index=traj.step_count(), phase="handoff",
                    summary=f"coordinator -> {specialist} for {action.tool}",
                    agent="coordinator"))
                sstate = ModelState(task=ctx.task, context=ctx.context, phase="act",
                                    pending=[action], assigned=f"specialist:{specialist}",
                                    compose_mode="last")
                term, _ = self._act_loop(ctx, sstate, traj, phase_label=specialist,
                                         max_steps=4)
                if sstate.history:
                    observations.append(sstate.history[-1])
                traj.handoffs.append({"from": specialist, "to": "coordinator",
                                      "reason": "subtask complete"})

            parts = [self._obs_text(o) for o in observations if o.get("ok")]
            answer = "; ".join(parts) if understanding.compose == "all" else (
                parts[-1] if parts else "I could not complete the task.")
            if any(a.kind == "assume" for a in actions):
                answer = "Assuming the intended interpretation: " + answer
            traj.steps.append(StepRecord(index=traj.step_count(), phase="final",
                                         summary=f"final answer: {answer[:200]}",
                                         agent="coordinator"))
            return self._finish(ctx, traj, "answer", answer)
        except HarnessError as exc:
            return self._guard(ctx, traj, exc)

    def _obs_text(self, o: dict) -> str:
        from agent_eval_harness.agents.model import observation_text

        return observation_text(o)

    def _resists(self, ctx: RunContext) -> bool:
        resist = getattr(ctx.model, "policy_injection_resisted", None)
        return bool(resist()) if resist else True
