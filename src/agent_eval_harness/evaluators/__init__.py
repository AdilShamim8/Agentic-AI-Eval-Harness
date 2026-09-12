"""Evaluator registry: name -> factory. Benchmarks reference these names."""
from __future__ import annotations

from agent_eval_harness.core.errors import InfraError
from agent_eval_harness.evaluators.deterministic.outcome import (
    ContainsAll,
    ExactMatch,
    ForbiddenContent,
    NumericTolerance,
    SchemaValidation,
    TaskChecks,
)
from agent_eval_harness.evaluators.deterministic.tools import (
    StepLimit,
    Termination,
    ToolArguments,
    ToolSelection,
)
from agent_eval_harness.evaluators.llm_judge.judge import build_judge
from agent_eval_harness.evaluators.trajectory.behavior import (
    LoopDetection,
    PlanningQuality,
    RecoveryBehavior,
    TerminationQuality,
    ToolEfficiency,
    TrajectoryAlignment,
)

_FACTORIES = {
    "exact_match": lambda: ExactMatch(),
    "contains_all": lambda: ContainsAll(),
    "numeric_tolerance": lambda: NumericTolerance(),
    "forbidden_content": lambda: ForbiddenContent(),
    "schema_validation": lambda: SchemaValidation(),
    "task_checks": lambda: TaskChecks(),
    "tool_selection": lambda: ToolSelection(),
    "tool_arguments": lambda: ToolArguments(),
    "step_limit": lambda: StepLimit(),
    "termination": lambda: Termination(),
    "trajectory": lambda: TrajectoryAlignment(),
    "tool_efficiency": lambda: ToolEfficiency(),
    "loop_detection": lambda: LoopDetection(),
    "termination_quality": lambda: TerminationQuality(),
    "recovery": lambda: RecoveryBehavior(),
    "planning_quality": lambda: PlanningQuality(),
    "llm_answer_correctness": lambda: build_judge("answer_correctness"),
    "llm_instruction_following": lambda: build_judge("instruction_following"),
    "llm_plan_quality": lambda: build_judge("plan_quality"),
    "llm_synthesis_quality": lambda: build_judge("synthesis_quality"),
}


def build_evaluator(name: str):
    if name not in _FACTORIES:
        raise InfraError(
            f"unknown evaluator '{name}' (available: {sorted(_FACTORIES)})")
    return _FACTORIES[name]()


def build_evaluators(names: list[str]) -> list:
    return [build_evaluator(n) for n in names]


def available_evaluators() -> list[str]:
    return sorted(_FACTORIES)


__all__ = ["build_evaluator", "build_evaluators", "available_evaluators"]
