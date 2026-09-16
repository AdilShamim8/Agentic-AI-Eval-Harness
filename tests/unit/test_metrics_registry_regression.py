"""Metrics + regression engine + registry unit tests."""
import math

import pytest

from agent_eval_harness.core.errors import InfraError
from agent_eval_harness.core.schemas import BaselineRecord, RunRecord
from agent_eval_harness.metrics.aggregation import percentile, wilson_ci
from agent_eval_harness.registry.registry import list_benchmarks, load_benchmark


def test_wilson_known_values():
    lo, hi = wilson_ci(0, 0)
    assert (lo, hi) == (0.0, 0.0)
    lo, hi = wilson_ci(50, 50)
    assert lo <= 0.9 <= hi or math.isclose(lo, 0.9, abs_tol=0.05)
    lo, hi = wilson_ci(1, 2)
    assert 0.0 < lo < 0.5 < hi < 1.0


def test_percentile():
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    assert percentile([], 50) == 0.0
    assert percentile([10], 95) == 10


def test_registry_load_and_validate():
    bm = load_benchmark("react_basic")
    assert bm.name == "react_basic" and bm.evaluators
    bm_ext = load_benchmark("react_basic.yaml")
    assert bm_ext.name == "react_basic"
    names = [b["name"] for b in list_benchmarks()]
    assert {"react_basic", "supervisor_basic", "map_reduce_basic",
            "failure_recovery", "adversarial"} <= set(names)
    with pytest.raises(InfraError):
        load_benchmark("no_such_benchmark")


def test_registry_rejects_unknown_evaluator(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("""
benchmark: {name: bad, version: "1.0", pattern: react}
dataset: {path: datasets/react/golden.jsonl}
evaluators: [task_checks, not_a_real_evaluator]
thresholds: {overall_pass_rate: 0.5}
""")
    with pytest.raises(InfraError):
        load_benchmark(str(bad))


def test_registry_rejects_bad_threshold(tmp_path):
    bad = tmp_path / "bad2.yaml"
    bad.write_text("""
benchmark: {name: bad2, version: "1.0", pattern: react}
dataset: {path: datasets/react/golden.jsonl}
evaluators: [task_checks]
thresholds: {overall_pass_rate: 1.5}
""")
    with pytest.raises(InfraError):
        load_benchmark(str(bad))


# ---- regression engine -----------------------------------------------------


def _record(rate_a, n=40, evals=None):
    from agent_eval_harness.core.schemas import CaseVerdict

    verdicts = []
    for i in range(n):
        passed = i < int(rate_a * n)
        verdicts.append(CaseVerdict(
            case_id=f"c{i}", pattern="react", category="normal", passed=passed,
            scores=evals or {}, failed_evaluators=[] if passed else ["task_checks"]))
    return RunRecord(
        run_id="r1", benchmark="react_basic", benchmark_version="1.0",
        agent="builtin:react", agent_pattern="react", seed=1, ablation="full",
        versions={}, config={},
        verdicts=verdicts,
        metrics={"cases": n, "passed": int(rate_a * n), "pass_rate": rate_a,
                 "per_evaluator": evals and {} or {}})


def _baseline(rate):
    return BaselineRecord(name="b", run_id="r0", benchmark="react_basic",
                          created_at="t",
                          metrics={"pass_rate": rate, "per_evaluator": {}})


def test_regression_detected():
    from agent_eval_harness.regression.engine import check_regression

    gate = check_regression(_record(0.84), _baseline(0.84))
    assert gate.passed
    gate = check_regression(_record(0.79), _baseline(0.84))
    assert not gate.passed
    assert "REGRESSION DETECTED" in gate.summary
    assert gate.exit_code == 1


def test_regression_boundary_exact_threshold():
    from agent_eval_harness.regression.engine import check_regression

    # delta exactly -0.03 is NOT below threshold -0.03 -> ok (boundary is inclusive)
    gate = check_regression(_record(0.81), _baseline(0.84))
    assert gate.passed, "delta -0.03 should be within threshold"
    gate = check_regression(_record(0.8099), _baseline(0.84))
    assert not gate.passed


def test_regression_insufficient_data():
    from agent_eval_harness.regression.engine import check_regression

    gate = check_regression(_record(0.5, n=5), _baseline(0.84))
    assert any(f.verdict == "insufficient_data" for f in gate.findings)
    assert not gate.passed  # fail-closed by default


def test_load_baseline_variants(tmp_path):
    import json
    from agent_eval_harness.regression.engine import load_baseline

    bases = tmp_path / "baselines"
    bases.mkdir()
    sample = {"benchmark": "react_basic", "metrics": {"pass_rate": 0.85}}
    file_path = str(bases / "my_base.json")
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(sample, fh)

    b1 = load_baseline("my_base", str(bases))
    assert b1.name == "my_base"
    assert b1.metrics["pass_rate"] == 0.85

    b2 = load_baseline("my_base.json", str(bases))
    assert b2.name == "my_base"

    b3 = load_baseline(file_path)
    assert b3.name == "my_base"


def test_save_baseline_with_json_suffix(tmp_path):
    from agent_eval_harness.runner.runner import save_baseline

    rec = _record(0.88)
    out_dir = str(tmp_path / "baselines")
    p = save_baseline(rec, "my_gate.json", out_dir=out_dir)
    assert p.endswith("my_gate.json")
    assert not p.endswith("my_gate.json.json")
    assert "\\" not in p




def test_runner_persist_posix_events_path(tmp_path):
    from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig

    bm = load_benchmark("react_basic")
    runner = BenchmarkRunner(bm, RunConfig(benchmark="react_basic", limit=1,
                                           out_dir=str(tmp_path)))
    rec = runner.run()
    assert "\\" not in rec.events_path
    assert rec.events_path.endswith(f"{rec.run_id}.events.jsonl")


def test_aggregation_handles_zero_latency_and_none_redundant():
    from agent_eval_harness.metrics.aggregation import aggregate

    verdicts = [
        {"case_id": "c1", "pattern": "react", "category": "normal", "passed": True,
         "failure_class": "none", "scores": {"s1": 1.0}, "failed_evaluators": [],
         "evaluator_errors": [], "latency_ms": 0.0, "tool_calls": 1,
         "loop_detected": False, "termination": "answer"},
        {"case_id": "c2", "pattern": "react", "category": "normal", "passed": True,
         "failure_class": "none", "scores": {"s1": 1.0}, "failed_evaluators": [],
         "evaluator_errors": [], "latency_ms": 10.0, "tool_calls": 1,
         "loop_detected": False, "termination": "answer"},
    ]
    outcomes = [
        {"redundant": None, "fault_injected": False},
        {"redundant": 2, "fault_injected": False},
    ]
    metrics = aggregate(verdicts, outcomes, runtime_s=0.5, tokens_in=10, tokens_out=10)
    assert metrics["latency_p50_ms"] == 5.0
    assert metrics["tool_metrics"]["redundant_calls"] == 2


def test_compare_runs_union_evaluators():
    from agent_eval_harness.comparison.compare import compare_runs
    from agent_eval_harness.core.errors import FailureClass
    from agent_eval_harness.core.schemas import CaseVerdict, RunRecord

    v_a1 = CaseVerdict(case_id="c1", pattern="react", category="normal", passed=True,
                       failure_class=FailureClass.NONE, scores={}, failed_evaluators=[],
                       evaluator_errors=[])
    v_a2 = CaseVerdict(case_id="c2", pattern="react", category="normal", passed=True,
                       failure_class=FailureClass.NONE, scores={"ev2": 0.8}, failed_evaluators=[],
                       evaluator_errors=[])
    v_b1 = CaseVerdict(case_id="c1", pattern="react", category="normal", passed=True,
                       failure_class=FailureClass.NONE, scores={"ev1": 1.0}, failed_evaluators=[],
                       evaluator_errors=[])
    v_b2 = CaseVerdict(case_id="c2", pattern="react", category="normal", passed=True,
                       failure_class=FailureClass.NONE, scores={"ev2": 0.9}, failed_evaluators=[],
                       evaluator_errors=[])

    def _make_rec(rid, verdicts):
        return RunRecord(run_id=rid, benchmark="react_basic", benchmark_version="1.0",
                         agent="builtin:react", agent_pattern="react", seed=1, ablation="full",
                         versions={}, config={}, verdicts=verdicts,
                         metrics={"pass_rate": 1.0, "cases": 2}, recorded_at="")

    rec_a = _make_rec("ra", [v_a1, v_a2])
    rec_b = _make_rec("rb", [v_b1, v_b2])
    rec_a.metrics["per_category"] = {"normal": {"pass_rate": 1.0}}
    rec_b.metrics["per_category"] = {"normal": {"pass_rate": 0.5}}
    res = compare_runs(rec_a, rec_b)
    assert "ev1" in res.per_evaluator
    assert "ev2" in res.per_evaluator
    assert "normal" in res.per_category
    assert res.per_category["normal"]["delta"] == -0.5


def test_load_run_optional_fields(tmp_path):
    import json
    from agent_eval_harness.cli.app import _load_run

    data = {
        "run_id": "test_partial",
        "benchmark": "bench",
        "verdicts": [
            {"case_id": "c1", "passed": True}
        ]
    }
    p = tmp_path / "test_partial.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    run = _load_run(str(p))
    assert run.run_id == "test_partial"
    assert len(run.verdicts) == 1
    assert run.verdicts[0].case_id == "c1"
    assert run.verdicts[0].passed is True
    assert run.verdicts[0].failure_class.value == "none"
