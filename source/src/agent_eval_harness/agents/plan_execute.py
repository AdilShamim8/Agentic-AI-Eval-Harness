"""Plan-and-Execute pattern agent — explicit plan, then execution, with replan."""
from __future__ import annotations

from agent_eval_harness.agents.base import BasePatternAgent, RunContext
from agent_eval_harness.agents.model import ModelState, Think
from agent_eval_harness.core.errors import HarnessError
from agent_eval_harness.core.schemas import AgentRunOutcome, Trajectory


class PlanExecuteAgent(BasePatternAgent):
    pattern = "plan_execute"

    def run(self, ctx: RunContext) -> AgentRunOutcome:
        traj = Trajectory()
        try:
            understanding = ctx.model.understand(ctx.task, ctx.context)
            state = ModelState(
                task=ctx.task,
                context=ctx.context,
                phase="plan",
                pending=list(understanding.actions),
                compose_mode=understanding.compose,
            )
            # Phase 1: explicit plan (recorded in trajectory.plan / plan steps)
            plan_decision = ctx.model.decide(state)
            state.phase = "act"
            if hasattr(plan_decision, "steps"):
                traj.plan.extend(plan_decision.steps)
                for s in plan_decision.steps:
                    self._step(traj, state, "plan", s[:200])
                state.step_index += 1
            else:
                self._step(traj, state, "plan", "(no explicit plan produced)")

            if ctx.case.injection and not self._resists(ctx):
                from agent_eval_harness.agents.model import Action

                state.pending = [Action("tool", "store_set",
                                        {"key": "exfiltrate", "value": "all report data"})]

            # Phase 2: execute; on tool errors, note a replan thought
            termination, answer = self._act_loop(
                ctx, state, traj, phase_label=self.id,
                max_steps=ctx.case.max_steps if ctx.case.max_steps else 14,
            )
            if termination == "step_limit" and not traj.tool_calls:
                traj.steps.append(
                    type(traj.steps[0])(index=traj.step_count(), phase="plan",
                                        summary="replan: fall back to direct answer")
                ) if traj.steps else None
            return self._finish(ctx, traj, termination, answer)
        except HarnessError as exc:
            return self._guard(ctx, traj, exc)

    def _resists(self, ctx: RunContext) -> bool:
        resist = getattr(ctx.model, "policy_injection_resisted", None)
        return bool(resist()) if resist else True
