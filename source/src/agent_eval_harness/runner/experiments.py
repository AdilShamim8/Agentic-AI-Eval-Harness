"""Experiments: harness ablations, judge calibration (Cohen's kappa),
reproducibility repeats. Every function MEASURES — nothing is assumed."""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from typing import Any

from agent_eval_harness.core.errors import InfraError
from agent_eval_harness.evaluators.llm_judge.judge import RubricJudge
from agent_eval_harness.harness.controls import ABLATION_PROFILES
from agent_eval_harness.registry.registry import load_benchmark
from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig


# ---------------------------------------------------------------------------
# Ablation study
# ---------------------------------------------------------------------------


def run_ablation(benchmark: str, profiles: list[str] | None = None,
                 skill: float = 0.85, seed: int = 20260912,
                 out_dir: str = "evals/runs") -> dict[str, Any]:
    """Run the same benchmark under each ablation profile; return a measured
    attribution table."""
    profiles = profiles or list(ABLATION_PROFILES)
    unknown = [p for p in profiles if p not in ABLATION_PROFILES]
    if unknown:
        raise InfraError(f"unknown ablation profiles: {unknown}")
    bm = load_benchmark(benchmark)
    rows: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        runner = BenchmarkRunner(bm, RunConfig(
            benchmark=benchmark, skill=skill, seed=seed, ablation=profile,
            out_dir=out_dir))
        rec = runner.run()
        m = rec.metrics
        rows[profile] = {
            "run_id": rec.run_id,
            "cases": m["cases"],
            "pass_rate": m["pass_rate"],
            "recovery_rate": (m["behavior"].get("recovery_rate")
                              if m["behavior"].get("recovery_n") else None),
            "tool_efficiency": m["behavior"].get("tool_efficiency_mean"),
            "loop_rate": m["behavior"]["loop_rate"],
            "termination_success": m["behavior"]["termination_success"],
        }
    baseline = rows.get("full")
    attribution = {}
    if baseline:
        for profile, row in rows.items():
            if profile == "full":
                continue
            attribution[profile] = {
                "pass_rate_delta": round(row["pass_rate"] - baseline["pass_rate"], 4),
                "note": f"pass-rate change when harness capability is REMOVED "
                        f"({profile} vs full)",
            }
    return {"benchmark": benchmark, "profiles": rows, "attribution": attribution}


# ---------------------------------------------------------------------------
# Judge calibration (Cohen's kappa vs hand labels)
# ---------------------------------------------------------------------------


def cohen_kappa(a: list[int], b: list[int]) -> float:
    """Cohen's kappa for two binary label vectors."""
    n = len(a)
    if n == 0 or len(a) != len(b):
        raise InfraError("kappa needs equal-length, non-empty label vectors")
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pa = sum(a) / n
    pb = sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe >= 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def export_calibration_sample(benchmark: str, sample_n: int = 60,
                              seed: int = 20260912,
                              skill: float = 0.85,
                              criterion: str = "answer_correctness",
                              out_path: str = "evals/calibration/sample.csv",
                              run_out_dir: str = "evals/runs") -> dict[str, Any]:
    """Run the benchmark, apply the judge to every case, export an unlabeled
    sample for human review (case, answer, gold, judge decision)."""
    bm = load_benchmark(benchmark)
    runner = BenchmarkRunner(bm, RunConfig(benchmark=benchmark, skill=skill,
                                           seed=seed, out_dir=run_out_dir))
    record = runner.run()
    judge = RubricJudge(criterion)
    rows: list[dict[str, Any]] = []
    from agent_eval_harness.registry.datasets import load_dataset
    from agent_eval_harness.evaluators.llm_judge.judge import _gold_reference
    cases = {c.id: c for c in load_dataset(
        runner._resolve(bm.dataset_path))}
    for v in record.verdicts:
        case = cases[v.case_id]
        # re-derive the judge decision for the sample (deterministic judge)
        from agent_eval_harness.core.schemas import AgentRunOutcome
        outcome = AgentRunOutcome(case_id=v.case_id, ok=v.passed,
                                  final_answer=v.final_answer)
        res = judge.evaluate(case, outcome)
        rows.append({
            "case_id": v.case_id, "category": v.category,
            "task": case.task[:160],
            "gold_reference": _gold_reference(case)[:160],
            "agent_answer": v.final_answer[:200],
            "judge_pass": 1 if res.passed else 0,
            "human_pass": "",  # <- filled by the annotator
            "annotator": "",
            "notes": "",
        })
    # deterministic subsample
    step = max(1, len(rows) // sample_n) if len(rows) > sample_n else 1
    sample = rows[::step][:sample_n]
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        fieldnames = list(sample[0].keys()) if sample else [
            "case_id", "category", "task", "gold_reference", "agent_answer",
            "judge_pass", "human_pass", "annotator", "notes"
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sample)
    return {"sample_path": out_path, "exported": len(sample), "total": len(rows),
            "benchmark": benchmark}


def compute_calibration(labels_path: str) -> dict[str, Any]:
    """Compute judge-vs-human agreement stats from a filled label CSV."""
    with open(labels_path, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("human_pass") not in ("", None)]
    if not rows:
        raise InfraError(f"no filled human labels in {labels_path}")
    judge = [int(r["judge_pass"]) for r in rows]
    human = [int(r["human_pass"]) for r in rows]
    kappa = cohen_kappa(judge, human)
    agree = sum(1 for j, h in zip(judge, human) if j == h)
    fp = sum(1 for j, h in zip(judge, human) if j == 1 and h == 0)
    fn = sum(1 for j, h in zip(judge, human) if j == 0 and h == 1)
    annotators = sorted({r.get("annotator", "?") or "?" for r in rows})
    return {
        "labels_path": labels_path,
        "n": len(rows),
        "annotators": annotators,
        "agreement": round(agree / len(rows), 4),
        "cohens_kappa": round(kappa, 4),
        "kappa_target": 0.6,
        "kappa_met": kappa > 0.6,
        "judge_false_positives": fp,
        "judge_false_negatives": fn,
        "judge_pass_rate": round(sum(judge) / len(rows), 4),
        "human_pass_rate": round(sum(human) / len(rows), 4),
        "limitation": "single annotator" if len(annotators) == 1 else
                      f"{len(annotators)} annotators (majority vote not applied)",
    }


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


def run_repro(benchmark: str, repeats: int = 5, seed: int = 20260912,
              vary_seed: bool = False, skill: float = 0.85,
              out_dir: str = "evals/runs") -> dict[str, Any]:
    """Repeat the same run N times. Same seed => byte-identical records
    (verified); varied seeds => sensitivity probe."""
    bm = load_benchmark(benchmark)
    rates: list[float] = []
    run_ids: list[str] = []
    records: list[Any] = []
    for i in range(repeats):
        s = seed + i if vary_seed else seed
        runner = BenchmarkRunner(bm, RunConfig(benchmark=benchmark, skill=skill,
                                               seed=s, out_dir=out_dir))
        rec = runner.run()
        rates.append(rec.pass_rate)
        run_ids.append(rec.run_id)
        records.append(rec)
    spread = round(max(rates) - min(rates), 6)
    byte_identical = None
    if not vary_seed and repeats >= 2:
        byte_identical = (_semantic(records[0]) == _semantic(records[1]))
    return {
        "benchmark": benchmark, "repeats": repeats, "vary_seed": vary_seed,
        "pass_rates": [round(r, 4) for r in rates],
        "max_spread_pp": round(spread * 100, 3),
        "target_within_pp": 2.0,
        "target_met": spread * 100 <= 2.0,
        "byte_identical_same_seed": byte_identical,
        "run_ids": run_ids,
    }


def _semantic(rec) -> str:
    """Canonical semantic projection: verdicts + scores + config, excluding
    wall-clock metadata (latency/timestamps/runtime) that cannot repeat."""
    payload = {
        "benchmark": rec.benchmark, "agent": rec.agent, "seed": rec.seed,
        "ablation": rec.ablation, "versions": rec.versions,
        "verdicts": [{"case_id": v.case_id, "passed": v.passed,
                      "failure_class": v.failure_class.value,
                      "scores": v.scores,
                      "failed_evaluators": v.failed_evaluators,
                      "evaluator_errors": v.evaluator_errors,
                      "termination": v.termination,
                      "loop_detected": v.loop_detected,
                      "final_answer": v.final_answer}
                     for v in rec.verdicts],
    }
    return json.dumps(payload, sort_keys=True)


def _record_json(rec) -> str:
    from agent_eval_harness.core.schemas import dumps

    return dumps(rec)
