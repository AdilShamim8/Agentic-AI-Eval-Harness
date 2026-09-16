"""Benchmark runner: executes a benchmark end-to-end and produces a run record.

Per case: fresh environment -> agent run (wall-clocked, network-guarded) ->
isolated evaluator execution (errors classified, never crash the run) ->
verdict. Run record + redacted event log persisted. Deterministic for a fixed
(seed, agent, benchmark, ablation, dataset) tuple.
"""
from __future__ import annotations

import os
import platform
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from agent_eval_harness.agents import create_agent
from agent_eval_harness.agents.model import ScriptedModelConfig
from agent_eval_harness.core.errors import (
    FailureClass,
    InfraError,
    classify_exception,
)
from agent_eval_harness.core.ids import case_seed, run_id as make_run_id
from agent_eval_harness.core.schemas import (
    BaselineRecord,
    CaseVerdict,
    RunRecord,
    dumps,
)
from agent_eval_harness.evaluators import build_evaluators
from agent_eval_harness.evaluators.trajectory.behavior import (
    PlanningQuality,
    ToolEfficiency,
)
from agent_eval_harness.harness.controls import (
    AblationProfile,
    ExecutionLimits,
    PermissionPolicy,
    get_ablation,
)
from agent_eval_harness.harness.environment import Environment
from agent_eval_harness.metrics.aggregation import aggregate
from agent_eval_harness.observability.events import EventRecorder
from agent_eval_harness.registry.datasets import dataset_sha256, load_dataset
from agent_eval_harness.registry.registry import BenchmarkDef
from agent_eval_harness.security.sandbox import network_sandbox


@dataclass
class RunConfig:
    benchmark: str
    agent_spec: str = ""
    seed: int = 20260912
    ablation: str | None = None  # explicit override wins over benchmark default
    skill: float = 0.85
    limit: int | None = None
    out_dir: str = "evals/runs"
    model_config: ScriptedModelConfig | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.skill <= 1.0:
            raise InfraError(f"skill must be in [0,1], got {self.skill}")


class BenchmarkRunner:
    def __init__(self, benchmark: BenchmarkDef, config: RunConfig):
        self.benchmark = benchmark
        self.config = config
        self.agent_spec = config.agent_spec or benchmark.agent or "builtin:react"
        pattern = benchmark.pattern or "react"
        if self.agent_spec.startswith("builtin:") and pattern and \
                self.agent_spec != f"builtin:{pattern}":
            # allow explicit override; default to benchmark's pattern
            if config.agent_spec == "":
                self.agent_spec = f"builtin:{pattern}"
        self.evaluators = build_evaluators(benchmark.evaluators)
        self.limits = ExecutionLimits.from_dict(benchmark.execution.get("limits"))
        self.policy = PermissionPolicy.from_dict(
            benchmark.execution.get("permissions"))
        ablation_name = (config.ablation
                         or benchmark.execution.get("ablation") or "full")
        self.ablation: AblationProfile = get_ablation(ablation_name)
        self.cases = load_dataset(self._resolve(benchmark.dataset_path))
        categories = benchmark.execution.get("categories")
        if categories:
            self.cases = [c for c in self.cases if c.category in set(categories)]
        limit = config.limit or benchmark.execution.get("limit")
        if limit:
            self.cases = self.cases[:int(limit)]
        self.events = EventRecorder("pending")

    # ------------------------------------------------------------------
    def _resolve(self, path: str) -> str:
        if os.path.isabs(path) or os.path.isfile(path):
            return path
        alt = os.path.join("datasets", os.path.basename(path))
        if os.path.isfile(alt):
            return alt
        raise InfraError(f"dataset not found: {path}")

    def run(self) -> RunRecord:
        t_start = time.perf_counter()
        ds_sha = dataset_sha256(self._resolve(self.benchmark.dataset_path))
        rid = make_run_id(self.benchmark.name, self.agent_spec, self.config.seed,
                          self.ablation.name, ds_sha,
                          extra=f"skill={self.config.skill}")
        self.events = EventRecorder(rid)
        self.events.emit("run_start", {
            "run_id": rid, "benchmark": self.benchmark.name,
            "benchmark_version": self.benchmark.version,
            "agent": self.agent_spec, "seed": self.config.seed,
            "ablation": self.ablation.name, "cases": len(self.cases),
            "skill": self.config.skill})

        verdicts: list[CaseVerdict] = []
        outcome_rows: list[dict] = []
        tokens_in = tokens_out = 0

        with network_sandbox() as guard:
            for case in self.cases:
                self.events.emit("case_start", {"case_id": case.id,
                                                "category": case.category},
                                 phase="case", case_id=case.id)
                agent = create_agent(
                    self.agent_spec, skill=self.config.skill,
                    model_config=self.config.model_config, seed=self.config.seed)
                env = Environment(self.limits, self.policy, self.ablation,
                                  self.events)
                gateway = env.prepare(case)
                if hasattr(agent, "model") and hasattr(agent.model, "begin_case"):
                    agent.model.begin_case(case.id, case_seed(self.config.seed, case.id))
                ctx = env.run_context(case, agent.model, gateway)

                t0 = time.perf_counter()
                try:
                    outcome = agent.run(ctx)
                except Exception as exc:  # noqa: BLE001 - classified below
                    from agent_eval_harness.core.schemas import AgentRunOutcome, Trajectory

                    outcome = AgentRunOutcome(
                        case_id=case.id, ok=False, final_answer="",
                        trajectory=Trajectory(termination="error"),
                        failure_class=classify_exception(exc), error=str(exc))
                latency_ms = (time.perf_counter() - t0) * 1000
                if latency_ms > self.limits.total_timeout_ms:
                    outcome.failure_class = FailureClass.TIMEOUT
                    outcome.error = (outcome.error or "") + \
                        f" [total timeout {latency_ms:.0f}ms]"
                outcome.latency_ms = latency_ms
                tokens_in += outcome.tokens_in_est
                tokens_out += outcome.tokens_out_est

                self.events.emit("agent_done", {
                    "case_id": case.id, "ok": outcome.ok,
                    "failure_class": outcome.failure_class.value,
                    "termination": outcome.trajectory.termination,
                    "tool_calls": len(outcome.trajectory.tool_calls),
                    "latency_ms": round(latency_ms, 3)},
                    phase="case", case_id=case.id)

                # ---- isolated evaluation ------------------------------------
                scores: dict[str, float] = {}
                failed_evaluators: list[str] = []
                evaluator_errors: list[str] = []
                for ev in self.evaluators:
                    self.events.emit("evaluator_start",
                                     {"evaluator": ev.name, "case_id": case.id},
                                     phase="evaluate", case_id=case.id)
                    try:
                        res = ev.evaluate(case, outcome)
                        scores[ev.name] = round(res.score, 4)
                        if not res.passed:
                            failed_evaluators.append(ev.name)
                    except Exception as exc:  # noqa: BLE001 - never crash run
                        evaluator_errors.append(ev.name)
                        self.events.emit("evaluator_error",
                                         {"evaluator": ev.name, "error": str(exc)[:300]},
                                         phase="evaluate", case_id=case.id)
                    self.events.emit("evaluator_end",
                                     {"evaluator": ev.name, "case_id": case.id},
                                     phase="evaluate", case_id=case.id)

                # ---- verdict + failure classification ------------------------
                if evaluator_errors:
                    fc = FailureClass.EVALUATOR_ERROR
                elif outcome.failure_class != FailureClass.NONE:
                    fc = outcome.failure_class
                elif failed_evaluators:
                    fc = FailureClass.TEST_FAILURE
                else:
                    fc = FailureClass.NONE
                passed = (not failed_evaluators and not evaluator_errors
                          and outcome.failure_class == FailureClass.NONE)

                verdicts.append(CaseVerdict(
                    case_id=case.id, pattern=case.pattern, category=case.category,
                    passed=passed, failure_class=fc, scores=scores,
                    failed_evaluators=failed_evaluators,
                    evaluator_errors=evaluator_errors,
                    final_answer=outcome.final_answer[:500],
                    latency_ms=round(latency_ms, 3),
                    tokens_in_est=outcome.tokens_in_est,
                    tokens_out_est=outcome.tokens_out_est,
                    tool_calls=len(outcome.trajectory.tool_calls),
                    loop_detected=outcome.trajectory.loop_detected,
                    termination=outcome.trajectory.termination))

                eff = ToolEfficiency().evaluate(case, outcome)
                plan = PlanningQuality().evaluate(case, outcome)
                outcome_rows.append({
                    "fault_injected": outcome.fault_injected,
                    "recovered": outcome.recovered_from_fault,
                    "redundant": outcome.trajectory.redundant_calls,
                    "efficiency": round(eff.score, 4) if outcome.trajectory.tool_calls else None,
                    "planning": round(plan.score, 4) if outcome.trajectory.plan else None,
                })
                self.events.emit("case_end", {
                    "case_id": case.id, "passed": passed,
                    "failure_class": fc.value}, phase="case", case_id=case.id)

        runtime_s = time.perf_counter() - t_start
        metrics = aggregate(
            [{"case_id": v.case_id, "pattern": v.pattern, "category": v.category,
              "passed": v.passed, "failure_class": v.failure_class.value,
              "scores": v.scores, "failed_evaluators": v.failed_evaluators,
              "evaluator_errors": v.evaluator_errors,
              "latency_ms": v.latency_ms, "tool_calls": v.tool_calls,
              "loop_detected": v.loop_detected, "termination": v.termination}
             for v in verdicts],
            outcome_rows, runtime_s, tokens_in, tokens_out)
        metrics["threshold_gates"] = self._threshold_gates(metrics)
        metrics["network_guard_attempts"] = list(guard.attempts)

        record = RunRecord(
            run_id=rid,
            benchmark=self.benchmark.name,
            benchmark_version=self.benchmark.version,
            agent=self.agent_spec,
            agent_pattern=self.benchmark.pattern,
            seed=self.config.seed,
            ablation=self.ablation.name,
            versions=self._versions(ds_sha),
            config={"skill": self.config.skill, "limit": self.config.limit,
                    "limits": dumps(self.limits),
                    "evaluators": self.benchmark.evaluators,
                    "thresholds": self.benchmark.thresholds},
            verdicts=verdicts,
            metrics=metrics,
            recorded_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            command=self._command_str(),
        )
        self.events.emit("run_end", {"run_id": rid, "passed": metrics["passed"],
                                     "cases": metrics["cases"],
                                     "pass_rate": metrics["pass_rate"]})
        self._persist(record)
        return record

    # ------------------------------------------------------------------
    def _threshold_gates(self, metrics: dict) -> dict[str, Any]:
        gates: dict[str, Any] = {}
        for name, threshold in self.benchmark.thresholds.items():
            if name == "overall_pass_rate":
                actual = metrics["pass_rate"]
            else:
                slot = metrics["per_evaluator"].get(name)
                actual = slot["pass_rate"] if slot else None
            gates[name] = {"threshold": float(threshold),
                           "actual": round(actual, 4) if actual is not None else None,
                           "passed": actual is not None and actual >= float(threshold)}
        return gates

    def _versions(self, ds_sha: str) -> dict:
        from agent_eval_harness import HARNESS_VERSION
        from agent_eval_harness.agents.model import MODEL_BACKEND_VERSION

        return {
            "agent": {"component": "agent", "version": self.agent_spec,
                      "revision": ""},
            "model": {"component": "model",
                      "version": MODEL_BACKEND_VERSION + " (deterministic simulation)",
                      "revision": f"skill={self.config.skill}"},
            "harness": {"component": "harness", "version": HARNESS_VERSION,
                        "revision": f"ablation={self.ablation.name}"},
            "benchmark": {"component": "benchmark",
                          "version": self.benchmark.version,
                          "revision": self.benchmark.name},
            "dataset": {"component": "dataset", "version": "1.0.0",
                        "revision": ds_sha[:16]},
            "evaluator": {"component": "evaluator", "version": "1.x",
                          "revision": ",".join(self.benchmark.evaluators)},
            "prompt": {"component": "prompt", "version": "judge_rubric_v1",
                       "revision": ""},
            "environment": {"component": "environment",
                            "version": f"python {platform.python_version()}",
                            "revision": sys.platform},
        }

    def _command_str(self) -> str:
        return (f"agent-eval run --benchmark {self.benchmark.name} "
                f"--agent {self.agent_spec} --seed {self.config.seed} "
                f"--skill {self.config.skill} --ablation {self.ablation.name}")

    def _persist(self, record: RunRecord) -> str:
        os.makedirs(self.config.out_dir, exist_ok=True)
        path = os.path.join(self.config.out_dir, f"{record.run_id}.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(dumps(record))
        events_path = os.path.join(self.config.out_dir,
                                   f"{record.run_id}.events.jsonl")
        self.events.export_jsonl(events_path)
        record.events_path = os.path.normpath(events_path).replace("\\", "/")
        with open(path, "w", encoding="utf-8") as fh:  # rewrite with events path
            fh.write(dumps(record))
        return path


def save_baseline(record: RunRecord, name: str, notes: str = "",
                  out_dir: str = "evals/baselines") -> str:
    """Persist a run record as a named baseline for regression checking."""
    os.makedirs(out_dir, exist_ok=True)
    base = BaselineRecord(
        name=name, run_id=record.run_id, benchmark=record.benchmark,
        created_at=record.recorded_at, metrics=dict(record.metrics),
        versions=dict(record.versions), notes=notes)
    path = os.path.join(out_dir, f"{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumps(base))
    return path
