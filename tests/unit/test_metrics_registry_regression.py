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


def test_export_calibration_sample_flat_path(tmp_path):
    import os
    from agent_eval_harness.runner.experiments import export_calibration_sample

    flat_path = "test_sample_flat.csv"
    try:
        res = export_calibration_sample("react_basic", sample_n=2, out_path=flat_path,
                                        run_out_dir=str(tmp_path / "runs"))
        assert os.path.isfile(flat_path)
        assert res["exported"] == 2
    finally:
        if os.path.isfile(flat_path):
            os.remove(flat_path)




# ---- regression gate compatibility (Issue H) ---------------------------------


def _compat_record(rate, n=56, benchmark="react_basic", selection=None,
                   ds_rev="6b2d6a9a48bc7c96", evaluators="task_checks,tool_selection,trajectory,termination,tool_efficiency,loop_detection"):
    """A run record with the identity fields real runner records carry."""
    from agent_eval_harness.core.schemas import CaseVerdict

    verdicts = []
    for i in range(n):
        passed = i < int(rate * n)
        verdicts.append(CaseVerdict(
            case_id=f"c{i}", pattern="react", category="normal", passed=passed,
            scores={}, failed_evaluators=[] if passed else ["task_checks"]))
    cfg = {}
    if selection:
        cfg["case_selection"] = selection
    return RunRecord(
        run_id="r-compat", benchmark=benchmark, benchmark_version="1.0",
        agent="builtin:react", agent_pattern="react", seed=1, ablation="full",
        versions={"dataset": {"revision": ds_rev},
                  "evaluator": {"revision": evaluators}},
        config=cfg, verdicts=verdicts,
        metrics={"cases": n, "passed": int(rate * n), "pass_rate": rate,
                 "per_evaluator": {}})


def _compat_baseline(rate, benchmark="react_basic", n=56, selection=None,
                     ds_rev="6b2d6a9a48bc7c96",
                     evaluators="task_checks,tool_selection,trajectory,termination,tool_efficiency,loop_detection"):
    metrics = {"pass_rate": rate, "per_evaluator": {}, "cases": n}
    if selection:
        metrics["case_selection"] = selection
    return BaselineRecord(
        name="b", run_id="r0", benchmark=benchmark, created_at="t",
        metrics=metrics,
        versions={"dataset": {"revision": ds_rev}, "evaluator": {"revision": evaluators}})


def test_regression_rejects_cross_benchmark():
    from agent_eval_harness.regression.engine import check_regression

    gate = check_regression(_compat_record(0.75, benchmark="failure_recovery"),
                            _compat_baseline(0.89))
    assert not gate.passed
    assert gate.exit_code == 1
    assert any(f.verdict == "incompatible_benchmark" for f in gate.findings)
    assert "GATE INCOMPATIBLE" in gate.summary
    # must NOT present numeric deltas as if they were meaningful evidence
    assert not any(f.verdict in ("ok", "regression", "improvement")
                   for f in gate.findings)


def test_regression_rejects_case_count_mismatch():
    from agent_eval_harness.regression.engine import check_regression

    # a --limit 8 smoke run gated against a 56-case full baseline
    gate = check_regression(_compat_record(0.9, n=8), _compat_baseline(0.89, n=56))
    assert not gate.passed
    assert any(f.verdict == "incompatible_selection" for f in gate.findings)


def test_regression_rejects_selection_digest_mismatch():
    from agent_eval_harness.regression.engine import check_regression

    gate = check_regression(
        _compat_record(0.9, selection="n=56;sha=aaaaaaaaaaaa"),
        _compat_baseline(0.89, selection="n=56;sha=bbbbbbbbbbbb"))
    assert not gate.passed
    assert any(f.verdict == "incompatible_selection" for f in gate.findings)


def test_regression_rejects_dataset_revision_mismatch():
    from agent_eval_harness.regression.engine import check_regression

    gate = check_regression(_compat_record(0.9, ds_rev="ffffffffffffffff"),
                            _compat_baseline(0.89, ds_rev="6b2d6a9a48bc7c96"))
    assert not gate.passed
    assert any(f.verdict == "incompatible_dataset" for f in gate.findings)


def test_regression_rejects_evaluator_set_mismatch():
    from agent_eval_harness.regression.engine import check_regression

    gate = check_regression(
        _compat_record(0.9, evaluators="task_checks,termination"),
        _compat_baseline(0.89, evaluators="task_checks,tool_selection"))
    assert not gate.passed
    assert any(f.verdict == "incompatible_evaluators" for f in gate.findings)


def test_regression_accepts_comparable_samples():
    from agent_eval_harness.regression.engine import check_regression

    # same benchmark, same dataset, same selection digest, same evaluators
    gate = check_regression(
        _compat_record(0.88, selection="n=56;sha=deadbeef1234"),
        _compat_baseline(0.89, selection="n=56;sha=deadbeef1234"))
    assert gate.passed  # -0.01 within -0.03 threshold
    assert not any(f.verdict.startswith("incompatible") for f in gate.findings)


def test_regression_legacy_baseline_count_fallback():
    from agent_eval_harness.regression.engine import check_regression

    # legacy baseline: no selection digest, no versions — equal counts pass
    base = _compat_baseline(0.89)
    base.versions = {}
    base.metrics = {"pass_rate": 0.89, "per_evaluator": {}, "cases": 56}
    gate = check_regression(_compat_record(0.88), base)
    assert gate.passed
    assert not any(f.verdict.startswith("incompatible") for f in gate.findings)


def test_regression_runnerlevel_cross_benchmark_rejected(tmp_path):
    """The exact CI failure mode: failure_recovery run gated vs react_basic
    'main' baseline used to be accepted silently."""
    from agent_eval_harness.regression.engine import check_regression, load_baseline
    from agent_eval_harness.registry.registry import load_benchmark
    from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig

    main_base = load_baseline("main")
    bm = load_benchmark("failure_recovery")
    fr_run = BenchmarkRunner(bm, RunConfig(benchmark="failure_recovery",
                                           out_dir=str(tmp_path))).run()
    gate = check_regression(fr_run, main_base)
    assert not gate.passed
    assert any(f.verdict == "incompatible_benchmark" for f in gate.findings)


# ---- min_cases_for_gate configuration (Issue B) ------------------------------


def _gate_cfg(tmp_path, default_min=None, top_min=None, bench_min=None,
              pass_on_insufficient=None):
    import yaml
    cfg = {"default": {"pass_rate": -0.03}, "benchmarks": {}}
    if default_min is not None:
        cfg["default"]["min_cases_for_gate"] = default_min
    if bench_min is not None:
        cfg["benchmarks"]["react_basic"] = {"min_cases_for_gate": bench_min}
    if top_min is not None:
        cfg["min_cases_for_gate"] = top_min
    if pass_on_insufficient is not None:
        cfg["pass_on_insufficient"] = pass_on_insufficient
    p = tmp_path / "gates.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return str(p)


def test_min_cases_configured_under_default_is_honored(tmp_path):
    """The shipped gates.yaml level: default.min_cases_for_gate."""
    from agent_eval_harness.regression.engine import check_regression

    # operator raises the bar from 10 to 30; a 20-case run must be inconclusive
    gates = _gate_cfg(tmp_path, default_min=30)
    gate = check_regression(_compat_record(0.88, n=20), _compat_baseline(0.89, n=20),
                            gate_config_path=gates)
    assert any(f.verdict == "insufficient_data" for f in gate.findings)
    assert not gate.passed, "fail-closed when configured minimum is not met"


def test_min_cases_per_benchmark_override_wins(tmp_path):
    from agent_eval_harness.regression.engine import check_regression

    gates = _gate_cfg(tmp_path, default_min=10, bench_min=40)
    gate = check_regression(_compat_record(0.88, n=20), _compat_baseline(0.89, n=20),
                            gate_config_path=gates)
    assert any(f.verdict == "insufficient_data" for f in gate.findings)
    assert not gate.passed


def test_min_cases_boundary_exact_and_below(tmp_path):
    from agent_eval_harness.regression.engine import check_regression

    gates = _gate_cfg(tmp_path, default_min=20)
    # exactly at the minimum -> sufficient -> normal comparison
    gate = check_regression(_compat_record(0.88, n=20), _compat_baseline(0.89, n=20),
                            gate_config_path=gates)
    assert not any(f.verdict == "insufficient_data" for f in gate.findings)
    assert gate.passed
    # one below the minimum -> inconclusive
    gate = check_regression(_compat_record(0.88, n=19), _compat_baseline(0.89, n=19),
                            gate_config_path=gates)
    assert any(f.verdict == "insufficient_data" for f in gate.findings)
    assert not gate.passed


def test_min_cases_zero_cases_is_insufficient(tmp_path):
    from agent_eval_harness.regression.engine import check_regression

    gates = _gate_cfg(tmp_path, default_min=10)
    gate = check_regression(_compat_record(0.0, n=0), _compat_baseline(0.89, n=0),
                            gate_config_path=gates)
    assert any(f.verdict == "insufficient_data" for f in gate.findings)
    assert not gate.passed


def test_min_cases_legacy_top_level_still_honored(tmp_path):
    from agent_eval_harness.regression.engine import check_regression

    gates = _gate_cfg(tmp_path, top_min=30)
    gate = check_regression(_compat_record(0.88, n=20), _compat_baseline(0.89, n=20),
                            gate_config_path=gates)
    assert any(f.verdict == "insufficient_data" for f in gate.findings)


def test_pass_on_insufficient_policy_both_ways(tmp_path):
    from agent_eval_harness.regression.engine import check_regression

    # fail closed (default, what CI needs)
    gates = _gate_cfg(tmp_path, default_min=30, pass_on_insufficient=False)
    gate = check_regression(_compat_record(0.88, n=20), _compat_baseline(0.89, n=20),
                            gate_config_path=gates)
    assert not gate.passed
    # explicitly authorized to pass: must still be visible as inconclusive
    gates = _gate_cfg(tmp_path, default_min=30, pass_on_insufficient=True)
    gate = check_regression(_compat_record(0.88, n=20), _compat_baseline(0.89, n=20),
                            gate_config_path=gates)
    assert gate.passed
    assert "insufficient" in gate.summary


# ---- run artifact atomicity (Issue G) ----------------------------------------


def test_persist_is_atomic_and_leaves_no_tmp(tmp_path, monkeypatch):
    """_persist: tmp file + os.replace — a crash mid-write must not clobber
    an existing record, and no .tmp residue may remain."""
    import agent_eval_harness.runner.runner as runner_mod
    from agent_eval_harness.registry.registry import load_benchmark
    from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig

    bm = load_benchmark("react_basic")
    r = BenchmarkRunner(bm, RunConfig(benchmark="react_basic", limit=2,
                                      out_dir=str(tmp_path))).run()
    rec_path = tmp_path / f"{r.run_id}.json"
    assert rec_path.read_text(encoding="utf-8").startswith("{")
    assert not list(tmp_path.glob("*.tmp")), "no .tmp residue after success"

    # now force a failure mid-persist on a re-run: existing record must survive
    target = tmp_path / f"{r.run_id}.json"
    sentinel = '{"sentinel": true}'
    target.write_text(sentinel, encoding="utf-8")

    def boom(obj):
        raise ValueError("simulated serialization crash")

    monkeypatch.setattr(runner_mod, "dumps", boom)
    try:
        BenchmarkRunner(bm, RunConfig(benchmark="react_basic", limit=2,
                                      out_dir=str(tmp_path))).run()
    except ValueError:
        pass
    finally:
        monkeypatch.undo()
    assert target.read_text(encoding="utf-8") == sentinel, \
        "existing record clobbered by a failed persist"
    assert not list(tmp_path.glob("*.tmp")), "no .tmp residue after failure"
