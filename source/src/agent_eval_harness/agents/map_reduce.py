"""Map-Reduce pattern agent — per-item map phase, then aggregate reduce phase."""
from __future__ import annotations

import re

from agent_eval_harness.agents.base import BasePatternAgent, RunContext
from agent_eval_harness.agents.model import CONCEPT_PATTERNS, Action, ModelState
from agent_eval_harness.core.errors import HarnessError
from agent_eval_harness.core.schemas import AgentRunOutcome, StepRecord, Trajectory

_NUM = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)")


def _numeric_from_obs(obs: dict, concept: str = "") -> float | None:
    v = obs.get("value")
    if isinstance(v, dict) and isinstance(v.get("value"), (int, float)):
        return float(v["value"])
    snippet = ""
    if isinstance(v, dict):
        if isinstance(v.get("results"), list) and v["results"]:
            snippet = str(v["results"][0].get("snippet", ""))
        else:
            snippet = str(v.get("snippet", ""))
    if snippet:
        if concept and concept in CONCEPT_PATTERNS:
            m = re.search(CONCEPT_PATTERNS[concept], snippet)
            if m:
                return float(m.group(1).replace(",", ""))
        m = _NUM.search(snippet)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


class MapReduceAgent(BasePatternAgent):
    pattern = "map_reduce"

    def run(self, ctx: RunContext) -> AgentRunOutcome:
        traj = Trajectory()
        try:
            understanding = ctx.model.understand(ctx.task, ctx.context)
            actions = list(understanding.actions)
            if ctx.case.injection and not self._resists(ctx):
                actions = [Action("tool", "store_set",
                                  {"key": "exfiltrate", "value": "all report data"})]

            if not actions:
                return self._finish(ctx, traj, "answer",
                                    "I could not complete the task.")

            # understanding.actions for map-reduce are ALL map actions; the
            # reduce action is synthesized by this agent from collected values.
            map_actions = actions
            traj.plan = [f"map: {self._d(a)}" for a in map_actions]
            if understanding.aggregate_op:
                traj.plan.append(f"reduce: aggregate with {understanding.aggregate_op}")

            # ---- MAP phase (sequential execution, one batch in the trace) ----
            concept = getattr(understanding, "concept", "")
            collected: list[float] = []
            for a in map_actions:
                mstate = ModelState(task=ctx.task, context=ctx.context, phase="act",
                                    pending=[a], assigned="mapper", compose_mode="last")
                term, _ = self._act_loop(ctx, mstate, traj, phase_label="mapper",
                                         max_steps=3)
                if mstate.history and mstate.history[-1].get("ok"):
                    num = _numeric_from_obs(mstate.history[-1], concept)
                    if num is not None:
                        collected.append(num)
                traj.steps.append(StepRecord(
                    index=traj.step_count(), phase="act",
                    summary=f"map item collected ({len(collected)} so far)",
                    agent="mapper"))

            # ---- REDUCE phase --------------------------------------------------
            if understanding.aggregate_op and collected:
                reduce_action = Action("tool", "data_calc",
                                       {"values": collected, "op": understanding.aggregate_op})
                rstate = ModelState(task=ctx.task, context=ctx.context, phase="act",
                                    pending=[reduce_action], assigned="reducer",
                                    compose_mode="last")
                self._act_loop(ctx, rstate, traj, phase_label="reducer", max_steps=3)
                last = rstate.history[-1] if rstate.history else {}
                v = last.get("value")
                answer = str(v.get("value")) if isinstance(v, dict) else str(v)
            elif collected:
                answer = "; ".join(str(c) for c in collected)
            else:
                answer = "I could not complete the task."

            if any(a.kind == "assume" for a in actions):
                answer = "Assuming the intended interpretation: " + answer
            traj.steps.append(StepRecord(index=traj.step_count(), phase="final",
                                         summary=f"final answer: {answer[:200]}",
                                         agent="reducer"))
            return self._finish(ctx, traj, "answer", answer)
        except HarnessError as exc:
            return self._guard(ctx, traj, exc)

    def _d(self, a: Action) -> str:
        return f"{a.tool}({', '.join(f'{k}={v}' for k, v in a.args.items())})"

    def _resists(self, ctx: RunContext) -> bool:
        resist = getattr(ctx.model, "policy_injection_resisted", None)
        return bool(resist()) if resist else True
