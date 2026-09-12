"""Failure taxonomy — the schema-level distinction between TEST FAILURE,
EVALUATOR ERROR, and INFRASTRUCTURE FAILURE (plus granular classes).

This taxonomy is the platform's backbone: when an evaluation fails we must know
*which layer* failed before blaming the model.
"""
from __future__ import annotations

from enum import Enum


class FailureClass(str, Enum):
    """Granular failure classification for one case/run."""

    NONE = "none"
    # Agent-side failures (the unit under test misbehaved in some way).
    TEST_FAILURE = "test_failure"            # checks evaluated -> not passed
    AGENT_ERROR = "agent_error"              # agent code raised
    TIMEOUT = "timeout"                      # wall-clock budget exhausted
    STEP_LIMIT = "step_limit"                # harness step cap hit
    TOOL_LIMIT = "tool_limit"                # harness tool-call cap hit
    LOOP_DETECTED = "loop_detected"          # identical calls repeated
    SECURITY_VIOLATION = "security_violation"  # policy violation (denied/flagged)
    # Evaluation-machinery failures.
    EVALUATOR_ERROR = "evaluator_error"      # an evaluator crashed
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"  # harness/env broke


# Report-level buckets (the three the master contract requires to distinguish).
REPORT_BUCKETS = {
    FailureClass.TEST_FAILURE: "TEST FAILURE",
    FailureClass.AGENT_ERROR: "TEST FAILURE",
    FailureClass.TIMEOUT: "TEST FAILURE",
    FailureClass.STEP_LIMIT: "TEST FAILURE",
    FailureClass.TOOL_LIMIT: "TEST FAILURE",
    FailureClass.LOOP_DETECTED: "TEST FAILURE",
    FailureClass.SECURITY_VIOLATION: "TEST FAILURE",
    FailureClass.EVALUATOR_ERROR: "EVALUATOR ERROR",
    FailureClass.INFRASTRUCTURE_FAILURE: "INFRASTRUCTURE FAILURE",
    FailureClass.NONE: "PASS",
}


def report_bucket(fc: "FailureClass | str") -> str:
    try:
        return REPORT_BUCKETS[FailureClass(fc)]
    except (KeyError, ValueError):
        return "TEST FAILURE"


class HarnessError(Exception):
    """Base class for all harness-raised errors. Carries a FailureClass."""

    failure_class = FailureClass.INFRASTRUCTURE_FAILURE

    def __init__(self, message: str, *, failure_class: FailureClass | None = None):
        super().__init__(message)
        if failure_class is not None:
            self.failure_class = failure_class


class AgentError(HarnessError):
    """Agent adapter code raised an unexpected exception."""

    failure_class = FailureClass.AGENT_ERROR


class EvaluatorError(HarnessError):
    """An evaluator raised an unexpected exception."""

    failure_class = FailureClass.EVALUATOR_ERROR


class InfraError(HarnessError):
    """Evaluation infrastructure itself failed (I/O, bad state, event sink...)."""

    failure_class = FailureClass.INFRASTRUCTURE_FAILURE


class ToolInfraError(InfraError):
    """Tool infrastructure broke (as opposed to a legitimate tool error result)."""


class SecurityViolation(HarnessError):
    """A security policy was violated (denied tool/arg, network attempt...)."""

    failure_class = FailureClass.SECURITY_VIOLATION


class TimeoutExceeded(HarnessError):
    failure_class = FailureClass.TIMEOUT


class StepLimitExceeded(HarnessError):
    failure_class = FailureClass.STEP_LIMIT


class ToolLimitExceeded(HarnessError):
    failure_class = FailureClass.TOOL_LIMIT


class LoopDetected(HarnessError):
    failure_class = FailureClass.LOOP_DETECTED


def classify_exception(exc: BaseException) -> FailureClass:
    """Map an arbitrary exception to a FailureClass."""
    if isinstance(exc, HarnessError):
        return exc.failure_class
    if isinstance(exc, (RecursionError, MemoryError, OSError)):
        return FailureClass.INFRASTRUCTURE_FAILURE
    return FailureClass.AGENT_ERROR
