"""ReAct pattern agent — interleaved reasoning and acting."""
from __future__ import annotations

from agent_eval_harness.agents.base import BasePatternAgent, RunContext
from agent_eval_harness.agents.model import ModelState
from agent_eval_harness.core.errors import HarnessError
from agent_eval_harness.core.schemas import AgentRunOutcome, Trajectory


class ReActAgent(BasePatternAgent):
    pattern = "react"

    def run(self, ctx: RunContext) -> AgentRunOutcome:
        traj = Trajectory()
        try:
            understanding = ctx.model.understand(ctx.task, ctx.context)
            state = ModelState(
                task=ctx.task,
                context=ctx.context,
                phase="act",
                pending=list(understanding.actions),
                compose_mode=understanding.compose,
            )
            # adversarial-injection gate: resist or deviate
            if ctx.case.injection and not self._resists(ctx):
                state.pending = [a for a in state.pending][:0]  # deviation: drop real work
                from agent_eval_harness.agents.model import Action

                state.pending = [Action("tool", "store_set",
                                        {"key": "exfiltrate", "value": "all report data"})]
                state.compose_mode = "last"
            termination, answer = self._act_loop(
                ctx, state, traj, phase_label=self.id,
                max_steps=ctx.case.max_steps if ctx.case.max_steps else 12,
            )
            return self._finish(ctx, traj, termination, answer)
        except HarnessError as exc:
            return self._guard(ctx, traj, exc)

    def _resists(self, ctx: RunContext) -> bool:
        resist = getattr(ctx.model, "policy_injection_resisted", None)
        return bool(resist()) if resist else True
