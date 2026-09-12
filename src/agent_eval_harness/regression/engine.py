"""Regression engine + quality gates.

A baseline stores a run's headline metrics; a challenger run is checked
against per-metric thresholds. Deltas beyond the threshold (default -0.03 on
overall pass rate) produce REGRESSION findings and a failing gate — wired to
CI exit codes by the CLI.
"""
from __future__ import annotations

import json
import os
from typing import Any

from agent_eval_harness.core.schemas import (
    BaselineRecord,
    GateDecision,
    RegressionFinding,
    RunRecord,
)

DEFAULT_GATE_CONFIG_PATH = "configs/gates.yaml"


def _load_gate_config(path: str | None = None) -> dict[str, Any]:
    p = path or os.environ.get("AEH_GATES_CONFIG", DEFAULT_GATE_CONFIG_PATH)
    if not os.path.isfile(p):
        return {}
    import yaml

    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_baseline(name: str, baselines_dir: str = "evals/baselines") -> BaselineRecord:
    path = os.path.join(baselines_dir, f"{name}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"baseline '{name}' not found at {path}")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return BaselineRecord(name=d["name"], run_id=d["run_id"],
                          benchmark=d["benchmark"], created_at=d["created_at"],
                          metrics=d.get("metrics", {}), versions=d.get("versions", {}),
                          notes=d.get("notes", ""))


def check_regression(
    run: RunRecord,
    baseline: BaselineRecord,
    gate_config_path: str | None = None,
) -> GateDecision:
    """Compare a run against a baseline using configured thresholds."""
    cfg = _load_gate_config(gate_config_path)
    defaults: dict[str, float] = cfg.get("default", {"pass_rate": -0.03})
    per_bench = cfg.get("benchmarks", {}).get(run.benchmark, {})

    def threshold_for(metric: str) -> float:
        if metric in per_bench:
            return float(per_bench[metric])
        if metric in defaults:
            return float(defaults[metric])
        return -0.03

    findings: list[RegressionFinding] = []

    base_rate = float(baseline.metrics.get("pass_rate", 0.0))
    new_rate = run.pass_rate
    thr = threshold_for("pass_rate")
    delta = round(new_rate - base_rate, 4)
    n = run.metrics.get("cases", 0)
    if n < int(cfg.get("min_cases_for_gate", 10)):
        findings.append(RegressionFinding(
            metric="overall_pass_rate", baseline=base_rate, new=new_rate,
            delta=delta, threshold=thr, scope="overall",
            verdict="insufficient_data"))
    else:
        findings.append(RegressionFinding(
            metric="overall_pass_rate", baseline=base_rate, new=new_rate,
            delta=delta, threshold=thr, scope="overall",
            verdict="regression" if delta < thr else (
                "improvement" if delta > abs(thr) else "ok")))

    base_eval = baseline.metrics.get("per_evaluator", {})
    new_eval = run.metrics.get("per_evaluator", {})
    for ev, slot in sorted(new_eval.items()):
        if ev not in base_eval:
            continue
        b = float(base_eval[ev].get("pass_rate", 0.0))
        nw = float(slot.get("pass_rate", 0.0))
        ev_thr = threshold_for(f"evaluator:{ev}")
        d = round(nw - b, 4)
        findings.append(RegressionFinding(
            metric=ev, baseline=b, new=nw, delta=d, threshold=ev_thr,
            scope=f"per_evaluator:{ev}",
            verdict="regression" if d < ev_thr else (
                "improvement" if d > abs(ev_thr) else "ok")))

    hard_fail = [f for f in findings if f.verdict == "regression"]
    insufficient = [f for f in findings if f.verdict == "insufficient_data"]
    passed = not hard_fail
    if hard_fail:
        summary = (f"REGRESSION DETECTED: {len(hard_fail)} metric(s) below "
                   f"threshold — " + "; ".join(
                       f"{f.metric} {f.baseline:.3f}->{f.new:.3f} "
                       f"(delta {f.delta:+.3f} < {f.threshold:+.3f})"
                       for f in hard_fail))
    elif insufficient:
        summary = (f"Gate inconclusive: {len(insufficient)} metric(s) with "
                   f"insufficient data (min cases not met).")
        passed = bool(cfg.get("pass_on_insufficient", False))
    else:
        improvements = [f for f in findings if f.verdict == "improvement"]
        summary = (f"No regressions (overall {base_rate:.3f} -> {new_rate:.3f}, "
                   f"delta {delta:+.3f}); {len(improvements)} improvement(s).")
    return GateDecision(gate=f"regression:{baseline.name}", passed=passed,
                        findings=findings, summary=summary)
