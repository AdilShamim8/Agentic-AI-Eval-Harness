"""Report builders: Markdown (humans) + JSON (tooling) from the same source.

Reports distinguish TEST FAILURE / EVALUATOR ERROR / INFRASTRUCTURE FAILURE
at the schema level, include uncertainty (Wilson CI), and end with
rule-based recommendations derived from measured failure stats.
"""
from __future__ import annotations

import json
from typing import Any

from agent_eval_harness.comparison.compare import ComparisonResult
from agent_eval_harness.core.errors import FailureClass, report_bucket
from agent_eval_harness.core.schemas import (
    BaselineRecord,
    GateDecision,
    RunRecord,
    dumps,
)


def _fmt_pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _bucket_rows(record: RunRecord) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {"TEST FAILURE": [], "EVALUATOR ERROR": [],
                                     "INFRASTRUCTURE FAILURE": [], "PASS": []}
    for v in record.verdicts:
        if v.passed:
            continue
        buckets[report_bucket(v.failure_class)].append(v.case_id)
    return buckets


def recommendations(record: RunRecord) -> list[str]:
    """Rule-based engineering recommendations from measured failure stats."""
    m = record.metrics
    recs: list[str] = []
    b = m.get("behavior", {})
    hist = m.get("failure_histogram", {})
    gates = m.get("threshold_gates", {})
    per_cat = m.get("per_category", {})

    if b.get("loop_rate", 0) > 0.05:
        recs.append(
            f"Loop rate is {b['loop_rate']:.1%} — tighten loop detection "
            f"(identical-call threshold) or add a loop-breaking prompt strategy.")
    if (b.get("recovery_rate") is not None and b["recovery_rate"] < 0.7
            and b.get("recovery_n", 0) >= 5):
        recs.append(
            f"Fault recovery is only {b['recovery_rate']:.0%} on {b['recovery_n']} "
            f"fault-injected cases — verify the retry ablation before shipping.")
    if hist.get("evaluator_error"):
        recs.append(
            f"{hist['evaluator_error']} case(s) hit EVALUATOR_ERROR — fix the "
            f"evaluator; those cases currently score 0 without evidence.")
    if hist.get("infrastructure_failure"):
        recs.append(
            f"{hist['infrastructure_failure']} case(s) hit INFRASTRUCTURE_FAILURE — "
            f"separate harness defects from agent quality before drawing conclusions.")
    if b.get("tool_efficiency_mean") is not None and b["tool_efficiency_mean"] < 0.7:
        recs.append(
            f"Mean tool efficiency is {b['tool_efficiency_mean']:.2f} — trim "
            f"redundant calls (context optimization, dedup observations).")
    failed_gates = [g for g, s in gates.items() if not s.get("passed", True)]
    if failed_gates:
        recs.append(
            f"Benchmark thresholds not met: {', '.join(failed_gates)} — "
            f"either improve the agent or re-baseline the threshold with evidence.")
    adv = per_cat.get("adversarial")
    if adv and adv["pass_rate"] < 0.6 and adv["n"] >= 5:
        recs.append(
            f"Adversarial pass rate is {adv['pass_rate']:.0%} — harden against "
            f"prompt injection (resistance policy, tool-permission tightening).")
    amb = per_cat.get("ambiguous")
    if amb and amb["pass_rate"] < 0.6 and amb["n"] >= 5:
        recs.append(
            f"Ambiguous-case pass rate is {amb['pass_rate']:.0%} — require "
            f"explicit assumption statements in the agent's output contract.")
    if not recs:
        recs.append("No systemic issues detected in this run at current thresholds.")
    return recs


def build_markdown(
    record: RunRecord,
    comparison: ComparisonResult | None = None,
    gate: GateDecision | None = None,
) -> str:
    m = record.metrics
    lines: list[str] = []
    lines.append(f"# Evaluation Run Report — {record.benchmark}")
    lines.append("")
    lines.append(f"- **Run ID**: `{record.run_id}`")
    lines.append(f"- **Agent**: `{record.agent}` (pattern: {record.agent_pattern})")
    lines.append(f"- **Model backend**: {record.versions['model']['version']} "
                 f"({record.versions['model']['revision']})")
    lines.append(f"- **Harness**: v{record.versions['harness']['version']} "
                 f"(ablation: {record.ablation})")
    lines.append(f"- **Benchmark**: {record.benchmark} v{record.benchmark_version} "
                 f"(dataset sha {record.versions['dataset']['revision']})")
    lines.append(f"- **Seed**: {record.seed} | **Skill**: "
                 f"{record.config.get('skill', 'n/a')}")
    lines.append(f"- **Recorded**: {record.recorded_at}")
    lines.append(f"- **Reproduce**: `{record.command}`")
    lines.append("")

    lines.append("## Overall")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Pass rate | **{m['passed']}/{m['cases']} = "
                 f"{m['pass_rate']:.1%}** |")
    ci = m["pass_rate_ci95"]
    lines.append(f"| 95% CI (Wilson) | [{ci[0]:.1%}, {ci[1]:.1%}] |")
    lines.append(f"| Runtime | {m['runtime_s']:.2f} s |")
    lines.append(f"| Latency p50 / p95 | {m['latency_p50_ms']:.1f} ms / "
                 f"{m['latency_p95_ms']:.1f} ms (deterministic backend — not "
                 f"representative of live-LLM latency) |")
    lines.append(f"| Tokens (est.) | in {m['tokens_in_est']:,} / out "
                 f"{m['tokens_out_est']:,} (chars/4 heuristic) |")
    lines.append(f"| Cost (est.) | ${m['cost_estimate_usd']:.4f} "
                 f"({m['cost_note']}) |")
    lines.append("")

    lines.append("## Per-evaluator scores")
    lines.append("")
    lines.append("| Evaluator | Mean score | Pass rate | n | Errors |")
    lines.append("|---|---|---|---|---|")
    for ev, slot in sorted(m["per_evaluator"].items()):
        lines.append(f"| {ev} | {slot['mean_score']:.3f} | "
                     f"{_fmt_pct(slot['pass_rate'])} | {slot['n']} | "
                     f"{slot.get('errors', 0)} |")
    lines.append("")

    lines.append("## Per-pattern / per-category")
    lines.append("")
    lines.append("| Group | Pass rate | 95% CI | n |")
    lines.append("|---|---|---|---|")
    for group, title in (("per_pattern", "Pattern"), ("per_category", "Category")):
        for gname, slot in sorted(m.get(group, {}).items()):
            lines.append(f"| {title}: {gname} | {slot['pass_rate']:.1%} | "
                         f"[{slot.get('ci_low', 0):.1%}, {slot.get('ci_high', 0):.1%}] "
                         f"| {slot['n']} |")
    lines.append("")

    lines.append("## Failure taxonomy")
    lines.append("")
    buckets = _bucket_rows(record)
    lines.append("| Bucket | Cases |")
    lines.append("|---|---|")
    for bucket in ("TEST FAILURE", "EVALUATOR ERROR", "INFRASTRUCTURE FAILURE"):
        ids = buckets.get(bucket, [])
        lines.append(f"| **{bucket}** | {len(ids)}"
                     + (f" — {', '.join(ids[:8])}"
                        + (" …" if len(ids) > 8 else "") if ids else " |"))
    hist = m.get("failure_histogram", {})
    if hist:
        lines.append("")
        lines.append("Granular classes: " + ", ".join(
            f"`{k}`={v}" for k, v in sorted(hist.items())))
    lines.append("")

    lines.append("## Trajectory & behavior")
    lines.append("")
    b = m.get("behavior", {})
    tm = m.get("tool_metrics", {})
    lines.append(f"- Tool calls: {tm.get('total_calls', 0)} total "
                 f"({tm.get('avg_calls_per_case', 0):.2f}/case), "
                 f"{tm.get('redundant_calls', 0)} redundant "
                 f"({tm.get('redundancy_rate', 0):.1%})")
    lines.append(f"- Loop rate: {_fmt_pct(b.get('loop_rate'))}")
    lines.append(f"- Termination success: {_fmt_pct(b.get('termination_success'))}")
    if b.get("recovery_rate") is not None:
        lines.append(f"- Fault recovery: {_fmt_pct(b['recovery_rate'])} "
                     f"(n={b.get('recovery_n')})")
    if b.get("tool_efficiency_mean") is not None:
        lines.append(f"- Tool efficiency (mean): {b['tool_efficiency_mean']:.3f}")
    if b.get("planning_coverage_mean") is not None:
        lines.append(f"- Planning coverage (mean): "
                     f"{b['planning_coverage_mean']:.3f}")
    lines.append("")

    lines.append("## Threshold gates")
    lines.append("")
    lines.append("| Gate | Threshold | Actual | Verdict |")
    lines.append("|---|---|---|---|")
    for g, slot in sorted(m.get("threshold_gates", {}).items()):
        verdict = "PASS" if slot.get("passed") else "**FAIL**"
        lines.append(f"| {g} | {slot['threshold']:.2f} | "
                     f"{_fmt_pct(slot.get('actual'))} | {verdict} |")
    lines.append("")

    if comparison:
        lines.append("## Comparison vs baseline run")
        lines.append("")
        lines.append(f"- `{comparison.run_a}` ({comparison.pass_rate_a:.1%}) vs "
                     f"`{comparison.run_b}` ({comparison.pass_rate_b:.1%}) → "
                     f"delta **{comparison.delta:+.3f}**")
        mc = comparison.mcnemar
        lines.append(f"- Discordant pairs: {mc['n_discordant']} "
                     f"(pass→fail: {mc['b01']}, fail→pass: {mc['c10']}); "
                     f"exact McNemar p={mc['p_value']} "
                     f"({'significant' if mc['significant_at_0.05'] else 'not significant'} "
                     f"at α=0.05)")
        if comparison.flips_pass_to_fail:
            lines.append(f"- Cases that regressed: "
                         f"{', '.join(comparison.flips_pass_to_fail[:12])}")
        if comparison.version_warnings:
            lines.append(f"- ⚠ Version drift: {'; '.join(comparison.version_warnings)}")
        if comparison.per_evaluator:
            lines.append("")
            lines.append("| Evaluator | A | B | Δ |")
            lines.append("|---|---|---|---|")
            for ev, slot in sorted(comparison.per_evaluator.items()):
                lines.append(f"| {ev} | {slot['mean_a']:.3f} | {slot['mean_b']:.3f} "
                             f"| {slot['delta']:+.3f} |")
        lines.append("")

    if gate:
        lines.append("## Regression gate")
        lines.append("")
        lines.append(f"**{'✅ GATE PASS' if gate.passed else '⛔ GATE FAIL'}** — "
                     f"{gate.summary}")
        lines.append("")
        lines.append("| Metric | Baseline | New | Delta | Threshold | Verdict |")
        lines.append("|---|---|---|---|---|---|")
        for f in gate.findings:
            lines.append(f"| {f.metric} | {f.baseline:.3f} | {f.new:.3f} "
                         f"| {f.delta:+.3f} | {f.threshold:+.3f} | {f.verdict} |")
        lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    for i, rec in enumerate(recommendations(record), 1):
        lines.append(f"{i}. {rec}")
    lines.append("")
    lines.append("## Events & artifacts")
    lines.append("")
    lines.append(f"- Event log (redacted): `{record.events_path}`")
    lines.append("- Not measured in this run: live-LLM judge reliability, "
                 "live-backend latency/cost. (Deterministic backend only.)")
    return "\n".join(lines)


def build_json_report(
    record: RunRecord,
    comparison: ComparisonResult | None = None,
    gate: GateDecision | None = None,
) -> str:
    payload = {
        "kind": "agent-eval-harness/report",
        "version": 1,
        "run": json.loads(dumps(record)),
        "comparison": json.loads(dumps(comparison)) if comparison else None,
        "gate": json.loads(dumps(gate)) if gate else None,
        "recommendations": recommendations(record),
    }
    return json.dumps(payload, indent=2, sort_keys=True)
