"""Run identity v2 — distinct experiments must never share a run id.

Regression tests for the v1 defect where two experiments differing only in
case selection (--limit / category filters) or model configuration collided
on the same run id, so the later run silently overwrote the earlier run's
artifacts (a --limit 8 smoke run replaced a full 56-case record).
"""
import json

from agent_eval_harness.core.ids import (
    case_selection_digest,
    run_id,
)
from agent_eval_harness.agents.model import ScriptedModelConfig
from agent_eval_harness.registry.registry import load_benchmark
from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig


# ---- pure identity function -------------------------------------------------


def test_run_id_deterministic_same_inputs():
    a = run_id("react_basic", "builtin:react", 1, "full", "deadbeef",
               extra="skill=0.85", case_selection="n=56;sha=abc", model_identity="default")
    b = run_id("react_basic", "builtin:react", 1, "full", "deadbeef",
               extra="skill=0.85", case_selection="n=56;sha=abc", model_identity="default")
    c = run_id("react_basic", "builtin:react", 2, "full", "deadbeef",
               extra="skill=0.85", case_selection="n=56;sha=abc", model_identity="default")
    assert a == b, "same experiment must map to the same identity"
    assert a != c, "different seed is a different experiment"


def test_run_id_differs_by_case_selection():
    a = run_id("react_basic", "builtin:react", 1, "full", "deadbeef",
               case_selection="n=56;sha=full56")
    b = run_id("react_basic", "builtin:react", 1, "full", "deadbeef",
               case_selection="n=8;sha=first8")
    assert a != b, "same benchmark, different case subset -> different experiment"


def test_run_id_differs_by_model_identity():
    a = run_id("react_basic", "builtin:react", 1, "full", "deadbeef",
               model_identity="default")
    b = run_id("react_basic", "builtin:react", 1, "full", "deadbeef",
               model_identity="cfg:abcdef123456")
    assert a != b, "explicit model configuration is a different experiment"


def test_case_selection_digest_order_sensitive_and_stable():
    ids1 = ["c1", "c2", "c3"]
    ids2 = ["c3", "c2", "c1"]
    ids3 = ["c1", "c2"]
    assert case_selection_digest(ids1) == case_selection_digest(list(ids1))
    assert case_selection_digest(ids1) != case_selection_digest(ids2), \
        "permutation changes which cases ran (order follows the dataset)"
    assert case_selection_digest(ids1) != case_selection_digest(ids3), \
        "subset must differ from superset"


def test_v2_ids_do_not_collide_with_v1_ids():
    # v1 preimage tag was "v1"; historical records keep their ids and must
    # never be overwritten by v2 re-runs of the same benchmark.
    v1_style = run_id("react_basic", "builtin:react", 1, "full", "deadbeef",
                      extra="skill=0.85")  # no selection/identity -> still v2 tag
    different_inputs = run_id("react_basic", "builtin:react", 9, "no_retry",
                              "otherbeef", extra="skill=0.60")
    assert v1_style != different_inputs


# ---- runner-level: the actual overwrite defect ------------------------------


def test_full_run_not_overwritten_by_limited_run(tmp_path):
    """The exact v1 defect: a --limit 8 run replaced the full run record."""
    bm = load_benchmark("react_basic")
    r_full = BenchmarkRunner(bm, RunConfig(benchmark="react_basic",
                                           out_dir=str(tmp_path))).run()
    r_limited = BenchmarkRunner(bm, RunConfig(benchmark="react_basic", limit=8,
                                              out_dir=str(tmp_path))).run()
    assert r_full.run_id != r_limited.run_id, \
        "full run and limit-8 run are different experiments"
    # the full record must still hold 56 cases after the limited run persisted
    full = json.loads((tmp_path / f"{r_full.run_id}.json").read_text(encoding="utf-8"))
    limited = json.loads((tmp_path / f"{r_limited.run_id}.json").read_text(encoding="utf-8"))
    assert full["metrics"]["cases"] == 56
    assert full["metrics"]["pass_rate"] == r_full.metrics["pass_rate"]
    assert limited["metrics"]["cases"] == 8
    assert full["config"]["case_selection"].startswith("n=56;")
    assert limited["config"]["case_selection"].startswith("n=8;")


def test_model_config_run_gets_distinct_identity(tmp_path):
    bm = load_benchmark("react_basic")
    r_default = BenchmarkRunner(bm, RunConfig(
        benchmark="react_basic", out_dir=str(tmp_path))).run()
    r_cfg = BenchmarkRunner(bm, RunConfig(
        benchmark="react_basic",
        model_config=ScriptedModelConfig(skill=0.85, seed=20260912,
                                         malformed_rate=0.5),
        out_dir=str(tmp_path))).run()
    assert r_default.run_id != r_cfg.run_id, \
        "explicit model config changes verdicts -> different experiment"
    assert r_default.config["model_identity"] == "default"
    assert r_cfg.config["model_identity"].startswith("cfg:")


def test_same_experiment_reproducible_same_id(tmp_path):
    bm = load_benchmark("react_basic")
    r1 = BenchmarkRunner(bm, RunConfig(benchmark="react_basic", limit=5,
                                       out_dir=str(tmp_path))).run()
    r2 = BenchmarkRunner(bm, RunConfig(benchmark="react_basic", limit=5,
                                       out_dir=str(tmp_path))).run()
    assert r1.run_id == r2.run_id, \
        "identical experiment re-run maps to the same identity (documented behavior)"


def test_command_string_includes_limit(tmp_path):
    bm = load_benchmark("react_basic")
    r = BenchmarkRunner(bm, RunConfig(benchmark="react_basic", limit=8,
                                      out_dir=str(tmp_path))).run()
    assert "--limit 8" in r.command
    r_full = BenchmarkRunner(bm, RunConfig(benchmark="react_basic",
                                           out_dir=str(tmp_path))).run()
    assert "--limit" not in r_full.command
