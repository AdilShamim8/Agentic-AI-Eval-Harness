"""Evaluator protocol + registry.

An evaluator reads the case (with its gold expectations) and the agent's
observable outcome, and emits an EvaluationResult with a normalized [0,1]
score. Deterministic evaluators are the default; LLM judges are opt-in per
benchmark (policy: never an LLM judge where a deterministic check suffices).
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agent_eval_harness.core.schemas import AgentRunOutcome, EvaluationResult, TestCase


@runtime_checkable
class Evaluator(Protocol):
    name: str
    version: str

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult: ...


def _result(case: TestCase, name: str, version: str, score: float, passed: bool,
            details: dict[str, Any] | None = None,
            meta: dict[str, Any] | None = None) -> EvaluationResult:
    return EvaluationResult(
        case_id=case.id, evaluator=name, version=version,
        score=max(0.0, min(1.0, float(score))), passed=bool(passed),
        details=details or {}, meta=meta or {},
    )
