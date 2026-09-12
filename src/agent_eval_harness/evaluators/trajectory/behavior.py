"""Trajectory + behavioral evaluators (observable execution, no hidden CoT)."""
from __future__ import annotations

from typing import Any

from agent_eval_harness.core.schemas import AgentRunOutcome, EvaluationResult, TestCase
from agent_eval_harness.evaluators.base import _result


def _lcs_len(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            cur[j] = prev[j - 1] + 1 if a[i - 1] == b[j - 1] else max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1]


class TrajectoryAlignment:
    """Ordered tool-sequence alignment (normalized LCS) + golden arg spot checks."""

    name, version = "trajectory", "1.1"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        golden = case.golden_trajectory
        if not golden:
            return _result(case, self.name, self.version, 1.0, True,
                           {"note": "no golden trajectory for this case"})
        g_names = [g["tool"] for g in golden]
        o_names = outcome.trajectory.tool_names()
        denom = max(len(g_names), len(o_names), 1)
        seq_score = _lcs_len(g_names, o_names) / denom

        arg_checks = [g for g in golden if g.get("args_contains")]
        arg_ok = 0
        for chk in arg_checks:
            for call in outcome.trajectory.tool_calls:
                if call.name != chk["tool"]:
                    continue
                if all(str(v).lower() in str(call.arguments.get(k, "")).lower()
                       for k, v in chk["args_contains"].items()):
                    arg_ok += 1
                    break
        arg_score = arg_ok / len(arg_checks) if arg_checks else 1.0
        score = 0.7 * seq_score + 0.3 * arg_score
        return _result(
            case, self.name, self.version, score, score >= 0.6,
            {"golden_tools": g_names, "observed_tools": o_names,
             "sequence_score": round(seq_score, 3),
             "argument_score": round(arg_score, 3),
             "lcs": _lcs_len(g_names, o_names)},
            {"deterministic": True, "pass_threshold": 0.6})


class ToolEfficiency:
    """necessary_calls / total_calls (map batches count as unordered sets)."""

    name, version = "tool_efficiency", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        calls = outcome.trajectory.tool_calls
        golden = case.golden_trajectory
        if not calls:
            score = 1.0 if not golden else 0.0
            return _result(case, self.name, self.version, score, score >= 0.6,
                           {"total": 0, "note": "no calls made"})
        # necessary = golden steps + fault-driven retries (recovery is not
        # waste); unique (name, canonical args) is reported for context.
        unique = {(c.name, str(sorted(c.arguments.items(), key=str))) for c in calls}
        if golden:
            necessary_n = len(golden)
        else:
            necessary_n = len(unique)
        if case.faults and outcome.fault_injected:
            necessary_n += len(case.faults)
        necessary_n = min(necessary_n, len(calls))
        score = necessary_n / len(calls) if calls else 1.0
        return _result(
            case, self.name, self.version, score, score >= 0.6,
            {"total_calls": len(calls), "unique_calls": len(unique),
             "necessary_est": necessary_n, "redundant": outcome.trajectory.redundant_calls},
            {"deterministic": True, "pass_threshold": 0.6})


class LoopDetection:
    name, version = "loop_detection", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        looped = outcome.trajectory.loop_detected
        capped = outcome.trajectory.termination in ("tool_limit", "step_limit")
        passed = not looped and not capped
        return _result(case, self.name, self.version, 1.0 if passed else 0.0, passed,
                       {"loop_detected": looped, "termination": outcome.trajectory.termination},
                       {"deterministic": True})


class TerminationQuality:
    """Explicit final answer, no post-final junk, within step budget."""

    name, version = "termination_quality", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        traj = outcome.trajectory
        terminated_by_answer = traj.termination == "answer"
        last_is_final = bool(traj.steps) and traj.steps[-1].phase == "final"
        within_budget = traj.step_count() <= case.max_steps
        score = (0.5 * terminated_by_answer + 0.25 * last_is_final
                 + 0.25 * within_budget)
        return _result(
            case, self.name, self.version, score,
            terminated_by_answer and last_is_final and within_budget,
            {"termination": traj.termination, "last_phase": traj.steps[-1].phase if traj.steps else "",
             "steps": traj.step_count(), "budget": case.max_steps},
            {"deterministic": True})


class RecoveryBehavior:
    """On failure-inducing cases: did the run recover after a scheduled fault?"""

    name, version = "recovery", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        if not case.faults:
            return _result(case, self.name, self.version, 1.0, True,
                           {"note": "no scheduled faults (not applicable)"},
                           {"deterministic": True, "applicable": False})
        passed = outcome.recovered_from_fault and outcome.trajectory.termination == "answer"
        score = (0.7 if outcome.recovered_from_fault else 0.0) + (
            0.3 if outcome.trajectory.termination == "answer" else 0.0)
        return _result(
            case, self.name, self.version, score, passed,
            {"fault_injected": outcome.fault_injected,
             "recovered": outcome.recovered_from_fault,
             "termination": outcome.trajectory.termination},
            {"deterministic": True, "applicable": True})


class PlanningQuality:
    """Deterministic plan-coverage proxy: plan steps must cover required tools."""

    name, version = "planning_quality", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        plan = outcome.trajectory.plan
        required = case.required_tools
        if not required:
            return _result(case, self.name, self.version, 1.0, True,
                           {"note": "no required tools to plan for"},
                           {"deterministic": True})
        if not plan and outcome.trajectory.tool_calls:
            # pattern without explicit plan -> not applicable
            return _result(case, self.name, self.version, 1.0, True,
                           {"note": "no plan recorded (pattern without explicit planning)"},
                           {"deterministic": True, "applicable": False})
        blob = " ".join(plan).lower()
        covered = [t for t in required if t.lower().replace("_", " ") in blob
                   or t.lower() in blob]
        score = len(covered) / len(required)
        return _result(case, self.name, self.version, score, score >= 0.8,
                       {"required": required, "covered": covered, "plan_steps": len(plan)},
                       {"deterministic": True})
