#!/usr/bin/env python3
"""Canonical experiment runner — reproduces every measured claim in the docs.

Usage: python scripts/run_experiments.py [--quick]
Writes results to evals/results/ and refreshes the 'main' baseline.
Every number in docs/final-report.md comes from a run of this script.
"""
from __future__ import annotations

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
os.chdir(REPO)

from agent_eval_harness.runner.experiments import (  # noqa: E402
    compute_calibration,
    run_ablation,
    run_repro,
)
from agent_eval_harness.registry.registry import load_benchmark  # noqa: E402
from agent_eval_harness.runner.runner import (  # noqa: E402
    BenchmarkRunner,
    RunConfig,
    save_baseline,
)

RESULTS = "evals/results"
BENCHMARKS = ["react_basic", "plan_execute_basic", "supervisor_basic",
              "swarm_basic", "map_reduce_basic"]


def main() -> int:
    os.makedirs(RESULTS, exist_ok=True)
    quick = "--quick" in sys.argv
    summary: dict = {}

    # ---- 1. full suite + baselines ----------------------------------------
    print("== Full suite (skill 0.85, seed 20260912, ablation full) ==")
    suite = {}
    for name in BENCHMARKS:
        bm = load_benchmark(name)
        rec = BenchmarkRunner(bm, RunConfig(benchmark=name, skill=0.85,
                                            seed=20260912)).run()
        m = rec.metrics
        suite[name] = {
            "run_id": rec.run_id, "cases": m["cases"], "passed": m["passed"],
            "pass_rate": m["pass_rate"], "ci95": m["pass_rate_ci95"],
            "per_category": m["per_category"], "per_evaluator": m["per_evaluator"],
            "behavior": m["behavior"], "latency_p50_ms": m["latency_p50_ms"],
            "latency_p95_ms": m["latency_p95_ms"],
            "tokens_in_est": m["tokens_in_est"], "tokens_out_est": m["tokens_out_est"],
            "cost_estimate_usd": m["cost_estimate_usd"],
            "runtime_s": m["runtime_s"],
        }
        print(f"  {name}: {m['passed']}/{m['cases']} = {m['pass_rate']:.1%} "
              f"CI={m['pass_rate_ci95']}")
    save_baseline(BenchmarkRunner(load_benchmark("react_basic"), RunConfig(
        benchmark="react_basic", skill=0.85, seed=20260912)).run(), "main")
    summary["full_suite"] = suite

    # ---- 2. harness ablation ----------------------------------------------
    print("== Harness ablation (failure_recovery: fault+difficult, 16 cases) ==")
    ablation = {}
    for skill in ((0.85,) if quick else (0.85, 0.60)):
        res = run_ablation("failure_recovery", skill=skill)
        ablation[f"skill_{skill}"] = res
        print(f"  skill={skill}: " + " ".join(
            f"{p}={r['pass_rate']:.1%}" for p, r in res["profiles"].items()))
    if not quick:
        res = run_ablation("react_basic", skill=0.85)
        ablation["react_basic_skill_0.85"] = res
        print("  react_basic: " + " ".join(
            f"{p}={r['pass_rate']:.1%}" for p, r in res["profiles"].items()))
    summary["ablation"] = ablation

    # ---- 3. judge calibration ----------------------------------------------
    print("== Judge calibration (rubric v1.1 vs hand labels, n=56) ==")
    cal = compute_calibration("evals/calibration/hand_labels.csv")
    summary["calibration"] = cal
    print(f"  kappa={cal['cohens_kappa']} agreement={cal['agreement']} "
          f"FN={cal['judge_false_negatives']} FP={cal['judge_false_positives']}")

    # ---- 4. reproducibility --------------------------------------------------
    print("== Reproducibility ==")
    repro = {}
    repro["react_same_seed_x5"] = run_repro("react_basic", repeats=5)
    if not quick:
        repro["supervisor_same_seed_x3"] = run_repro("supervisor_basic", repeats=3)
        repro["supervisor_varied_seed_x3"] = run_repro(
            "supervisor_basic", repeats=3, vary_seed=True)
    summary["repro"] = repro
    for key, r in repro.items():
        print(f"  {key}: spread={r['max_spread_pp']}pp "
              f"identical={r['byte_identical_same_seed']}")

    # ---- 5. regression demo ---------------------------------------------------
    print("== Regression demo (baseline vs degraded challenger) ==")
    bm = load_benchmark("react_basic")
    challenger = BenchmarkRunner(bm, RunConfig(
        benchmark="react_basic", skill=0.70, seed=20260912,
        ablation="no_retry")).run()
    from agent_eval_harness.regression.engine import check_regression, load_baseline

    gate = check_regression(challenger, load_baseline("main"))
    summary["regression_demo"] = {
        "challenger_run_id": challenger.run_id,
        "challenger_pass_rate": challenger.pass_rate,
        "gate_passed": gate.passed,
        "summary": gate.summary,
        "findings": [
            {"metric": f.metric, "baseline": f.baseline, "new": f.new,
             "delta": f.delta, "verdict": f.verdict} for f in gate.findings],
    }
    print(f"  challenger {challenger.pass_rate:.1%} -> "
          f"{'GATE FAIL (expected)' if not gate.passed else 'GATE PASS (unexpected!)'}")

    with open(os.path.join(RESULTS, "experiments.json"), "w") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
    print(f"\nresults -> {RESULTS}/experiments.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
