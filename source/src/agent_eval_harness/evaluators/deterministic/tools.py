"""Deterministic evaluators — tool use, step budget, termination."""
from __future__ import annotations

from typing import Any

from agent_eval_harness.core.schemas import AgentRunOutcome, EvaluationResult, TestCase
from agent_eval_harness.evaluators.base import _result


class ToolSelection:
    """Precision/recall/F1 of called tool names vs required set; forbidden
    tool use is an automatic fail."""

    name, version = "tool_selection", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        required = set(case.required_tools)
        forbidden = set(case.forbidden_tools)
        called = set(outcome.trajectory.tool_names())
        forbidden_hits = sorted(called & forbidden)
        inter = called & required if required else set()
        precision = len(inter) / len(called) if called else (1.0 if not required else 0.0)
        recall = len(inter) / len(required) if required else 1.0
        f1 = (2 * precision * recall / (precision + recall)
              if precision + recall else 0.0)
        passed = recall == 1.0 and not forbidden_hits and bool(called or not required)
        score = 0.0 if forbidden_hits else f1
        return _result(
            case, self.name, self.version, score, passed,
            {"required": sorted(required), "called": sorted(called),
             "precision": round(precision, 3), "recall": round(recall, 3),
             "f1": round(f1, 3), "forbidden_hits": forbidden_hits},
            {"deterministic": True})


class ToolArguments:
    """Spot-check key arguments: expected.tool_args = [{tool, arg, equals|contains|approx}]."""

    name, version = "tool_arguments", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        checks = case.expected.get("tool_args", [])
        if not checks:
            return _result(case, self.name, self.version, 1.0, True,
                           {"note": "no tool_args specified"})
        calls = outcome.trajectory.tool_calls
        results: list[dict[str, Any]] = []
        ok_count = 0
        for chk in checks:
            tool, arg = chk.get("tool", ""), chk.get("arg", "")
            satisfied = False
            for call in calls:
                if call.name != tool or arg not in call.arguments:
                    continue
                val = call.arguments[arg]
                if "equals" in chk:
                    satisfied = val == chk["equals"]
                elif "contains" in chk:
                    satisfied = str(chk["contains"]).lower() in str(val).lower()
                elif "approx" in chk:
                    try:
                        satisfied = abs(float(val) - float(chk["approx"])) <= float(
                            chk.get("tolerance", 1e-6))
                    except (TypeError, ValueError):
                        satisfied = False
                if satisfied:
                    break
            results.append({"tool": tool, "arg": arg, "ok": satisfied})
            ok_count += int(satisfied)
        score = ok_count / len(checks)
        return _result(case, self.name, self.version, score, ok_count == len(checks),
                       {"checks": results}, {"deterministic": True})


class StepLimit:
    name, version = "step_limit", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        limit = case.max_steps
        steps = outcome.trajectory.step_count()
        passed = steps <= limit
        score = min(1.0, limit / steps) if steps else 1.0
        return _result(case, self.name, self.version, score, passed,
                       {"limit": limit, "steps": steps}, {"deterministic": True})


class Termination:
    """The agent must finish with an explicit final answer (not truncation)."""

    name, version = "termination", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        term = outcome.trajectory.termination
        passed = term == "answer"
        return _result(case, self.name, self.version, 1.0 if passed else 0.0, passed,
                       {"termination": term, "error": outcome.error[:200]},
                       {"deterministic": True})
