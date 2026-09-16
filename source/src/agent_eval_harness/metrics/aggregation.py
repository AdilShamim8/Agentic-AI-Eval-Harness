"""Metrics aggregation with statistical honesty (Wilson 95% intervals).

Token counts are ESTIMATES (chars/4 heuristic); cost uses a simulated price
table for live-equivalent comparison and is labeled `estimate` in reports.
Latency is real measured wall-clock (on the deterministic backend it is NOT
representative of live-LLM latency — reports say so explicitly).
"""
from __future__ import annotations

import math
from typing import Any

# Simulated price table (USD per 1M tokens) — for live-equivalent cost modeling
# only; labeled `estimate` wherever reported.
PRICE_TABLE = {"in": 0.15, "out": 0.60}


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = (len(s) - 1) * pct / 100.0
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _rate(num: int, den: int) -> float:
    return round(num / den, 6) if den else 0.0


def aggregate(verdicts: list[dict], outcomes: list[dict], runtime_s: float,
              tokens_in: int, tokens_out: int) -> dict[str, Any]:
    """Build the metrics block of a run record from per-case dicts.

    verdicts: {case_id, pattern, category, passed, failure_class, scores,
               failed_evaluators, evaluator_errors, latency_ms, tool_calls,
               loop_detected, termination, applicable_evaluators}
    outcomes: {recovered, fault_injected, redundant, efficiency, planning,
               termination_quality ...}
    """
    n = len(verdicts)
    passed = sum(1 for v in verdicts if v["passed"])
    ci = wilson_ci(passed, n)

    per_evaluator: dict[str, dict[str, float]] = {}
    for v in verdicts:
        failed = set(v.get("failed_evaluators") or [])
        errored = set(v.get("evaluator_errors") or [])
        for name, score in v.get("scores", {}).items():
            slot = per_evaluator.setdefault(
                name, {"sum": 0.0, "n": 0, "pass": 0, "err": 0})
            slot["sum"] += score
            slot["n"] += 1
            if name in errored:
                slot["err"] += 1
            elif name not in failed:
                slot["pass"] += 1
    eval_out: dict[str, dict[str, float]] = {}
    for name, slot in per_evaluator.items():
        eval_out[name] = {
            "mean_score": round(slot["sum"] / slot["n"], 4) if slot["n"] else 0.0,
            "pass_rate": _rate(slot["pass"], slot["n"]),
            "n": slot["n"],
            "errors": slot["err"],
        }

    def _group(key: str) -> dict[str, dict[str, float]]:
        groups: dict[str, list[dict]] = {}
        for v in verdicts:
            groups.setdefault(v[key], []).append(v)
        out = {}
        for gname, items in groups.items():
            gpass = sum(1 for i in items if i["passed"])
            lo, hi = wilson_ci(gpass, len(items))
            out[gname] = {"pass_rate": _rate(gpass, len(items)), "n": len(items),
                          "ci_low": round(lo, 4), "ci_high": round(hi, 4)}
        return out

    failure_hist: dict[str, int] = {}
    for v in verdicts:
        fc = v.get("failure_class") or "none"
        if not v["passed"] or fc != "none":
            failure_hist[fc] = failure_hist.get(fc, 0) + 1

    latencies = [v["latency_ms"] for v in verdicts if v.get("latency_ms") is not None]
    tool_calls_total = sum(v.get("tool_calls", 0) for v in verdicts)
    loops = sum(1 for v in verdicts if v.get("loop_detected"))
    terminated_answer = sum(1 for v in verdicts if v.get("termination") == "answer")

    fault_cases = [o for o in outcomes if o.get("fault_injected")]
    recovered = sum(1 for o in fault_cases if o.get("recovered"))
    redund = sum((o.get("redundant") or 0) for o in outcomes)
    effs = [o["efficiency"] for o in outcomes if o.get("efficiency") is not None]
    plans = [o["planning"] for o in outcomes if o.get("planning") is not None]

    cost = (tokens_in / 1e6) * PRICE_TABLE["in"] + (tokens_out / 1e6) * PRICE_TABLE["out"]

    return {
        "cases": n,
        "passed": passed,
        "pass_rate": _rate(passed, n),
        "pass_rate_ci95": [round(ci[0], 4), round(ci[1], 4)],
        "per_evaluator": eval_out,
        "per_pattern": _group("pattern"),
        "per_category": _group("category"),
        "failure_histogram": failure_hist,
        "tool_metrics": {
            "total_calls": tool_calls_total,
            "avg_calls_per_case": round(tool_calls_total / n, 3) if n else 0.0,
            "redundant_calls": redund,
            "redundancy_rate": _rate(redund, tool_calls_total),
        },
        "behavior": {
            "loop_rate": _rate(loops, n),
            "termination_success": _rate(terminated_answer, n),
            "recovery_rate": _rate(recovered, len(fault_cases)) if fault_cases else None,
            "recovery_n": len(fault_cases),
            "tool_efficiency_mean": round(sum(effs) / len(effs), 4) if effs else None,
            "planning_coverage_mean": round(sum(plans) / len(plans), 4) if plans else None,
        },
        "latency_p50_ms": round(percentile(latencies, 50), 3),
        "latency_p95_ms": round(percentile(latencies, 95), 3),
        "tokens_in_est": tokens_in,
        "tokens_out_est": tokens_out,
        "cost_estimate_usd": round(cost, 6),
        "cost_note": "estimate: simulated pricing (in $0.15/1M, out $0.60/1M) on "
                     "estimated tokens (chars/4); not a live-backend measurement",
        "runtime_s": round(runtime_s, 3),
    }
