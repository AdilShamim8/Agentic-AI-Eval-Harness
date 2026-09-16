"""Run comparison: A vs B with per-case flips and a paired significance test."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from agent_eval_harness.core.schemas import RunRecord


@dataclass
class ComparisonResult:
    run_a: str
    run_b: str
    benchmark: str
    pass_rate_a: float
    pass_rate_b: float
    delta: float
    per_evaluator: dict[str, dict[str, float]] = field(default_factory=dict)
    per_pattern: dict[str, dict[str, float]] = field(default_factory=dict)
    flips_pass_to_fail: list[str] = field(default_factory=list)
    flips_fail_to_pass: list[str] = field(default_factory=list)
    mcnemar: dict[str, Any] = field(default_factory=dict)
    same_cases: int = 0
    version_warnings: list[str] = field(default_factory=list)


def compare_runs(a: RunRecord, b: RunRecord) -> ComparisonResult:
    if a.benchmark != b.benchmark:
        raise ValueError(f"cannot compare different benchmarks: "
                         f"{a.benchmark} vs {b.benchmark}")
    res = ComparisonResult(
        run_a=a.run_id, run_b=b.run_id, benchmark=a.benchmark,
        pass_rate_a=a.pass_rate, pass_rate_b=b.pass_rate,
        delta=round(b.pass_rate - a.pass_rate, 4))

    # version drift warnings (comparisons are only meaningful on shared parts)
    for comp in ("dataset", "benchmark"):
        ra, rb = a.versions.get(comp, {}), b.versions.get(comp, {})
        if ra.get("revision") != rb.get("revision"):
            res.version_warnings.append(
                f"{comp} revision differs: {ra.get('revision')} vs {rb.get('revision')}")

    va = {v.case_id: v for v in a.verdicts}
    vb = {v.case_id: v for v in b.verdicts}
    common = sorted(set(va) & set(vb))
    res.same_cases = len(common)
    b01 = sum(1 for cid in common if va[cid].passed and not vb[cid].passed)
    c10 = sum(1 for cid in common if not va[cid].passed and vb[cid].passed)
    res.flips_pass_to_fail = [cid for cid in common
                              if va[cid].passed and not vb[cid].passed]
    res.flips_fail_to_pass = [cid for cid in common
                              if not va[cid].passed and vb[cid].passed]
    res.mcnemar = _mcnemar(b01, c10)

    evals = sorted({ev for cid in common for v in (va[cid], vb[cid]) for ev in v.scores})
    for ev in evals:
        sa = [va[cid].scores.get(ev, 0.0) for cid in common]
        sb = [vb[cid].scores.get(ev, 0.0) for cid in common]
        res.per_evaluator[ev] = {
            "mean_a": round(sum(sa) / len(sa), 4) if sa else 0.0,
            "mean_b": round(sum(sb) / len(sb), 4) if sb else 0.0,
            "delta": round((sum(sb) - sum(sa)) / max(1, len(sb)), 4),
        }
    for group in ("per_pattern", "per_category"):
        ga, gb = a.metrics.get(group, {}), b.metrics.get(group, {})
        out = {}
        for key in sorted(set(ga) & set(gb)):
            out[key] = {"a": ga[key].get("pass_rate"), "b": gb[key].get("pass_rate"),
                        "delta": round((gb[key].get("pass_rate", 0)
                                        - ga[key].get("pass_rate", 0)), 4)}
        if group == "per_pattern":
            res.per_pattern = out
    return res


def _mcnemar(b01: int, c10: int) -> dict[str, Any]:
    """Exact McNemar test (two-sided) on paired pass/fail outcomes."""
    n = b01 + c10
    if n == 0:
        return {"b01": 0, "c10": 0, "n_discordant": 0, "p_value": 1.0,
                "significant_at_0.05": False, "note": "no discordant pairs"}
    k = min(b01, c10)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n) * 2
    p = min(1.0, p)
    return {"b01": b01, "c10": c10, "n_discordant": n,
            "p_value": round(p, 6), "significant_at_0.05": p < 0.05}
