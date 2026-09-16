"""Typed schemas for the entire platform (stdlib dataclasses, sorted-key JSON).

Design notes:
- Serialization is always `sort_keys=True` -> byte-identical run records.
- Every record is JSON-round-trippable via `to_jsonable`.
- Observability events live in observability/events.py; this module defines the
  *domain* records (case, result, trajectory, verdict, run, baseline, regression).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent_eval_harness.core.errors import FailureClass

# ---------------------------------------------------------------------------
# Tools / trajectory
# ---------------------------------------------------------------------------


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    ok: bool
    value: Any = None
    error: str = ""
    latency_ms: float = 0.0
    attempt: int = 1  # 1 = first try, 2+ = retries

    def canonical(self) -> str:
        return json.dumps(
            {"name": self.name, "arguments": self.arguments},
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass
class StepRecord:
    """One observable execution step (no hidden chain-of-thought is stored)."""

    index: int
    phase: str  # think|plan|act|observe|verify|handoff|final|error
    summary: str
    tool_call: int | None = None  # index into Trajectory.tool_calls
    agent: str = ""  # for multi-agent patterns (supervisor/swarm)


@dataclass
class Trajectory:
    steps: list[StepRecord] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    handoffs: list[dict[str, str]] = field(default_factory=list)  # {from,to,reason}
    termination: str = "answer"  # answer|step_limit|tool_limit|timeout|error
    loop_detected: bool = False
    redundant_calls: int = 0
    plan: list[str] = field(default_factory=list)  # for plan-based patterns

    def tool_names(self) -> list[str]:
        return [c.name for c in self.tool_calls]

    def step_count(self) -> int:
        return len(self.steps)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@dataclass
class FaultSchedule:
    """Deterministic fault injection for failure-inducing cases.

    faults: list of {tool, occurrence (1-based), error, kind}
    """

    faults: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TestCase:
    __test__ = False
    id: str
    pattern: str  # react|plan_execute|supervisor|swarm|map_reduce
    category: str  # normal|difficult|ambiguous|edge|adversarial|failure_inducing
    task: str
    context: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)
    difficulty: int = 1
    tags: list[str] = field(default_factory=list)
    seed: int = 0
    injection: bool = False  # task/tool text contains adversarial injection
    faults: list[dict[str, Any]] = field(default_factory=list)

    # convenience accessors -------------------------------------------------
    @property
    def answer_spec(self) -> dict[str, Any]:
        return self.expected.get("answer", {})

    @property
    def required_tools(self) -> list[str]:
        return list(self.expected.get("required_tools", []))

    @property
    def forbidden_tools(self) -> list[str]:
        return list(self.expected.get("forbidden_tools", []))

    @property
    def golden_trajectory(self) -> list[dict[str, Any]]:
        return list(self.expected.get("golden_trajectory", []))

    @property
    def max_steps(self) -> int:
        return int(self.expected.get("max_steps", 12))


# ---------------------------------------------------------------------------
# Results of running one case
# ---------------------------------------------------------------------------


@dataclass
class AgentRunOutcome:
    case_id: str
    ok: bool
    final_answer: str
    trajectory: Trajectory = field(default_factory=Trajectory)
    failure_class: FailureClass = FailureClass.NONE
    error: str = ""
    latency_ms: float = 0.0
    tokens_in_est: int = 0
    tokens_out_est: int = 0
    security_flags: list[str] = field(default_factory=list)
    retried_calls: int = 0
    recovered_from_fault: bool = False
    fault_injected: bool = False


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


@dataclass
class EvaluationResult:
    case_id: str
    evaluator: str
    version: str
    score: float  # normalized [0, 1]
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def errored(cls, case_id: str, evaluator: str, version: str, error: str):
        return cls(
            case_id=case_id,
            evaluator=evaluator,
            version=version,
            score=0.0,
            passed=False,
            error=error,
            meta={"judge_backend": None},
        )


@dataclass
class CaseVerdict:
    case_id: str
    pattern: str
    category: str
    passed: bool
    failure_class: FailureClass = FailureClass.NONE
    scores: dict[str, float] = field(default_factory=dict)
    failed_evaluators: list[str] = field(default_factory=list)
    evaluator_errors: list[str] = field(default_factory=list)
    final_answer: str = ""
    latency_ms: float = 0.0
    tokens_in_est: int = 0
    tokens_out_est: int = 0
    tool_calls: int = 0
    loop_detected: bool = False
    termination: str = "answer"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@dataclass
class MetricPoint:
    name: str
    value: float
    unit: str = "ratio"
    n: int = 0
    ci_low: float | None = None
    ci_high: float | None = None
    note: str = ""


@dataclass
class RunMetrics:
    cases: int = 0
    passed: int = 0
    pass_rate: float = 0.0
    pass_rate_ci: tuple[float, float] = (0.0, 0.0)
    per_evaluator: dict[str, dict[str, float]] = field(default_factory=dict)
    per_pattern: dict[str, dict[str, float]] = field(default_factory=dict)
    per_category: dict[str, dict[str, float]] = field(default_factory=dict)
    failure_histogram: dict[str, int] = field(default_factory=dict)
    tool_metrics: dict[str, Any] = field(default_factory=dict)
    behavior: dict[str, float] = field(default_factory=dict)
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    tokens_in_est: int = 0
    tokens_out_est: int = 0
    cost_estimate_usd: float = 0.0
    runtime_s: float = 0.0

    def points(self) -> list[MetricPoint]:
        ...  # built by metrics module


# ---------------------------------------------------------------------------
# Run records / baselines / regressions
# ---------------------------------------------------------------------------


@dataclass
class RunRecord:
    run_id: str
    benchmark: str
    benchmark_version: str
    agent: str
    agent_pattern: str
    seed: int
    ablation: str
    versions: dict[str, Any]
    config: dict[str, Any]
    verdicts: list[CaseVerdict] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = ""
    events_path: str = ""
    command: str = ""

    @property
    def pass_rate(self) -> float:
        m = self.metrics or {}
        return float(m.get("pass_rate", 0.0))


@dataclass
class BaselineRecord:
    name: str
    run_id: str
    benchmark: str
    created_at: str
    metrics: dict[str, Any] = field(default_factory=dict)
    versions: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass
class RegressionFinding:
    metric: str
    baseline: float
    new: float
    delta: float
    threshold: float
    scope: str = ""  # e.g. "overall" or "per_evaluator:task_completion"
    verdict: str = "ok"  # ok|regression|improvement|insufficient_data


@dataclass
class GateDecision:
    gate: str
    passed: bool
    findings: list[RegressionFinding] = field(default_factory=list)
    summary: str = ""

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses/enums/tuples into JSON-safe structures."""
    if isinstance(obj, Enum):
        return to_jsonable(obj.value)
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_jsonable(getattr(obj, k)) for k in obj.__dataclass_fields__}
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (set, frozenset)):
        try:
            sorted_items = sorted(obj)
        except TypeError:
            sorted_items = sorted(obj, key=str)
        return [to_jsonable(v) for v in sorted_items]
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, float):
        return round(obj, 6)
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    return str(obj)


def dumps(obj: Any) -> str:
    return json.dumps(to_jsonable(obj), sort_keys=True, indent=2)
