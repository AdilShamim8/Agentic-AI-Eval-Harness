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
    if os.path.isfile(name):
        path = name
    else:
        clean_name = name[:-5] if name.endswith(".json") else name
        path = os.path.join(baselines_dir, f"{clean_name}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"baseline '{name}' not found at {path}")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    base_name = d.get("name") or os.path.splitext(os.path.basename(path))[0]
    return BaselineRecord(name=base_name, run_id=d.get("run_id", ""),
                          benchmark=d.get("benchmark", ""), created_at=d.get("created_at", ""),
                          metrics=d.get("metrics", {}), versions=d.get("versions", {}),
                          notes=d.get("notes", ""))


def _compatibility_problems(run: RunRecord,
                            baseline: BaselineRecord) -> list[tuple[str, str]]:
    """Identity checks a regression comparison must pass before any numbers
    are trusted. Returns a list of (kind, human description) problems; an
    empty list means the samples are comparable. Checks that cannot be
    verified (fields absent on legacy records) are skipped rather than
    guessed — but every check that CAN be verified is enforced."""
    problems: list[tuple[str, str]] = []

    # 1. benchmark identity — hard requirement whenever the baseline declares one
    if baseline.benchmark and run.benchmark != baseline.benchmark:
        problems.append(("benchmark",
                          f"run is '{run.benchmark}' but baseline '{baseline.name}' "
                          f"measured '{baseline.benchmark}'"))

    # 2. dataset identity — same golden data, by revision (sha) when recorded
    ds_run = (run.versions or {}).get("dataset", {}).get("revision")
    ds_base = (baseline.versions or {}).get("dataset", {}).get("revision")
    if ds_run and ds_base and ds_run != ds_base:
        problems.append(("dataset",
                          f"dataset revision differs: run {ds_run} vs baseline {ds_base}"))

    # 3. case selection — the gate compares identical case subsets.
    #    Exact digest when both sides record it; fall back to case counts for
    #    legacy baselines (equal count is necessary, not sufficient).
    sel_run = (run.config or {}).get("case_selection")
    sel_base = (baseline.metrics or {}).get("case_selection")
    n_run = (run.metrics or {}).get("cases")
    n_base = (baseline.metrics or {}).get("cases")
    if sel_run and sel_base:
        if sel_run != sel_base:
            problems.append(("selection",
                              f"case selection differs: run {sel_run} "
                              f"vs baseline {sel_base}"))
    elif n_run is not None and n_base is not None and n_run != n_base:
        problems.append(("selection",
                          f"case count differs: run has {n_run} cases, "
                          f"baseline measured {n_base} (different subsets are "
                          "not comparable evidence)"))

    # 4. evaluator set — comparing different metrics is meaningless.
    ev_run = (run.versions or {}).get("evaluator", {}).get("revision")
    ev_base = (baseline.versions or {}).get("evaluator", {}).get("revision")
    if ev_run and ev_base:
        if sorted(ev_run.split(",")) != sorted(ev_base.split(",")):
            problems.append(("evaluators",
                              f"evaluator set differs: run [{ev_run}] vs "
                              f"baseline [{ev_base}]"))
    return problems

def check_regression(
    run: RunRecord,
    baseline: BaselineRecord,
    gate_config_path: str | None = None,
) -> GateDecision:
    """Compare a run against a baseline using configured thresholds.

    The comparison is only meaningful when the two samples are compatible:
    same benchmark, same dataset, same case selection, same evaluator set.
    Incompatible comparisons (e.g. gating a failure_recovery run against a
    react_basic baseline) used to be accepted silently and produced a
    seemingly valid quality delta — the gate now rejects them explicitly
    and fails closed.
    """
    cfg = _load_gate_config(gate_config_path)
    problems = _compatibility_problems(run, baseline)
    if problems:
        findings = [
            RegressionFinding(
                metric=f"compatibility:{kind}", baseline=baseline.metrics.get("pass_rate", 0.0),
                new=run.pass_rate, delta=round(run.pass_rate - baseline.metrics.get("pass_rate", 0.0), 4),
                threshold=0.0, scope="compatibility", verdict=f"incompatible_{kind}")
            for kind, _desc in problems
        ]
        summary = ("GATE INCOMPATIBLE: run and baseline are not comparable — "
                   + "; ".join(desc for _k, desc in problems)
                   + ". Refusing to report a quality delta on incomparable evidence.")
        return GateDecision(gate=f"regression:{baseline.name}", passed=False,
                            findings=findings, summary=summary)

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
