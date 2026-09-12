"""Supervisor pattern agent — routes subtasks to workers, verifies outputs."""
from __future__ import annotations

from agent_eval_harness.agents.base import BasePatternAgent, RunContext
from agent_eval_harness.agents.model import Action, ModelState
from agent_eval_harness.core.errors import HarnessError
from agent_eval_harness.core.schemas import AgentRunOutcome, StepRecord, Trajectory

_WORKER_BY_TOOL = {
    "calculator": "compute_worker",
    "data_calc": "compute_worker",
    "knowledge_search": "research_worker",
    "sim_web_get": "research_worker",
    "text_stats": "text_worker",
    "text_transform": "text_worker",
    "summarize": "text_worker",
    "store_set": "memory_worker",
    "store_get": "memory_worker",
}


class SupervisorAgent(BasePatternAgent):
    pattern = "supervisor"

    def run(self, ctx: RunContext) -> AgentRunOutcome:
        traj = Trajectory()
        try:
            understanding = ctx.model.understand(ctx.task, ctx.context)
            actions = list(understanding.actions)
            if ctx.case.injection and not self._resists(ctx):
                actions = [Action("tool", "store_set",
                                  {"key": "exfiltrate", "value": "all report data"})]

            # supervisor plan: one subtask per action
            traj.plan = [f"Delegate: {self._describe(a)}" for a in actions]
            for s in traj.plan:
                traj.steps.append(StepRecord(index=traj.step_count(), phase="plan",
                                             summary=s[:200], agent=self.id))

            worker_outputs: list[dict] = []
            for i, action in enumerate(actions):
                worker = _WORKER_BY_TOOL.get(action.tool, "research_worker")
                traj.handoffs.append({"from": self.id, "to": worker,
                                      "reason": self._describe(action)[:120]})
                traj.steps.append(StepRecord(index=traj.step_count(), phase="handoff",
                                             summary=f"delegate subtask {i + 1} to {worker}",
                                             agent=self.id))
                # worker mini-loop: executes its assigned action
                wstate = ModelState(task=ctx.task, context=ctx.context, phase="act",
                                    pending=[action], assigned=f"worker:{worker}",
                                    compose_mode="last")
                term, _ans = self._act_loop(ctx, wstate, traj, phase_label=worker,
                                            max_steps=4)
                last_obs = wstate.history[-1] if wstate.history else {}
                # supervisor verification of the worker output
                verified = bool(last_obs.get("ok")) or term == "answer"
                traj.steps.append(StepRecord(
                    index=traj.step_count(), phase="verify",
                    summary=f"worker {worker}: {'verified' if verified else 'FAILED - delegating retry'}",
                    agent=self.id))
                if not verified and action not in wstate.pending:
                    wstate2 = ModelState(task=ctx.task, context=ctx.context, phase="act",
                                         pending=[action], assigned=f"worker:{worker}",
                                         compose_mode="last")
                    self._act_loop(ctx, wstate2, traj, phase_label=worker, max_steps=3)
                    last_obs = wstate2.history[-1] if wstate2.history else {}
                worker_outputs.append(last_obs)

            # compose final from worker outputs
            parts = [self._obs_text(o) for o in worker_outputs if o.get("ok")]
            answer = "; ".join(parts) if understanding.compose == "all" else (
                parts[-1] if parts else "I could not complete the task.")
            if any(a.kind == "assume" for a in actions):
                answer = "Assuming the intended interpretation: " + answer
            traj.steps.append(StepRecord(index=traj.step_count(), phase="final",
                                         summary=f"final answer: {answer[:200]}", agent=self.id))
            return self._finish(ctx, traj, "answer", answer)
        except HarnessError as exc:
            return self._guard(ctx, traj, exc)

    def _describe(self, a: Action) -> str:
        if a.kind == "assume":
            return "state the assumption"
        return f"{a.tool}({', '.join(f'{k}={v}' for k, v in a.args.items())})"

    def _obs_text(self, o: dict) -> str:
        from agent_eval_harness.agents.model import observation_text

        return observation_text(o)

    def _resists(self, ctx: RunContext) -> bool:
        resist = getattr(ctx.model, "policy_injection_resisted", None)
        return bool(resist()) if resist else True
