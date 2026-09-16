"""agent-eval CLI — professional command surface (argparse + rich if available).

Exit codes: 0 ok · 1 gate/regression failure · 2 usage/infrastructure error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from rich.console import Console
    from rich.table import Table

    RICH = True
except ImportError:  # pragma: no cover
    RICH = False

from agent_eval_harness import __version__
from agent_eval_harness.comparison.compare import compare_runs
from agent_eval_harness.core.errors import InfraError
from agent_eval_harness.core.schemas import dumps
from agent_eval_harness.evaluators import available_evaluators
from agent_eval_harness.registry.datasets import (
    dataset_stats,
    validate_dataset,
)
from agent_eval_harness.registry.registry import list_benchmarks, load_benchmark
from agent_eval_harness.regression.engine import (
    check_regression,
    load_baseline,
)
from agent_eval_harness.reporting.reports import (
    build_json_report,
    build_markdown,
)
from agent_eval_harness.runner.experiments import (
    compute_calibration,
    export_calibration_sample,
    run_ablation,
    run_repro,
)
from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig, save_baseline

ERR = Console(stderr=True) if RICH else None
OUT = Console() if RICH else None


def _print_table(title: str, headers: list[str], rows: list[list[str]]) -> None:
    if RICH:
        table = Table(title=title, header_style="bold cyan")
        for h in headers:
            table.add_column(h)
        for row in rows:
            table.add_row(*row)
        assert OUT is not None
        OUT.print(table)
    else:  # pragma: no cover
        print(f"== {title} ==")
        print(" | ".join(headers))
        for row in rows:
            print(" | ".join(row))


def _load_run(run_id: str, runs_dir: str = "evals/runs"):
    if os.path.isfile(run_id):
        path = run_id
    else:
        clean_id = run_id[:-5] if run_id.endswith(".json") else run_id
        path = os.path.join(runs_dir, f"{clean_id}.json")
    if not os.path.isfile(path):
        raise InfraError(f"run '{run_id}' not found at {path}")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    from agent_eval_harness.core.schemas import RunRecord, CaseVerdict
    from agent_eval_harness.core.errors import FailureClass

    verdicts = [CaseVerdict(
        case_id=v["case_id"],
        pattern=v.get("pattern", ""),
        category=v.get("category", ""),
        passed=v.get("passed", False),
        failure_class=FailureClass(v.get("failure_class", "none")),
        scores=v.get("scores", {}),
        failed_evaluators=v.get("failed_evaluators", []),
        evaluator_errors=v.get("evaluator_errors", []),
        final_answer=v.get("final_answer", ""),
        latency_ms=v.get("latency_ms", 0.0),
        tokens_in_est=v.get("tokens_in_est", 0),
        tokens_out_est=v.get("tokens_out_est", 0),
        tool_calls=v.get("tool_calls", 0),
        loop_detected=v.get("loop_detected", False),
        termination=v.get("termination", ""))
        for v in d.get("verdicts", [])]
    return RunRecord(
        run_id=d.get("run_id", ""), benchmark=d.get("benchmark", ""),
        benchmark_version=d.get("benchmark_version", ""), agent=d.get("agent", ""),
        agent_pattern=d.get("agent_pattern", ""), seed=d.get("seed", 0),
        ablation=d.get("ablation", "full"), versions=d.get("versions", {}),
        config=d.get("config", {}), verdicts=verdicts,
        metrics=d.get("metrics", {}), recorded_at=d.get("recorded_at", ""),
        events_path=d.get("events_path", ""), command=d.get("command", ""))


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_run(args) -> int:
    bm = load_benchmark(args.benchmark, args.registry)
    runner = BenchmarkRunner(bm, RunConfig(
        benchmark=args.benchmark, agent_spec=args.agent, seed=args.seed,
        ablation=args.ablation, skill=args.skill, limit=args.limit,
        out_dir=args.out_dir))
    rec = runner.run()
    m = rec.metrics
    if args.json:
        print(dumps(rec))
    else:
        _print_table(
            f"Run {rec.run_id} — {rec.benchmark}",
            ["Metric", "Value"],
            [["Pass rate", f"{m['passed']}/{m['cases']} = {m['pass_rate']:.1%}"],
             ["95% CI", f"[{m['pass_rate_ci95'][0]:.1%}, {m['pass_rate_ci95'][1]:.1%}]"],
             ["Runtime", f"{m['runtime_s']:.2f}s"],
             ["Loop rate", f"{m['behavior']['loop_rate']:.1%}"],
             ["Termination", f"{m['behavior']['termination_success']:.1%}"],
             ["Events", rec.events_path]])
        failed_gates = [g for g, s in m["threshold_gates"].items()
                        if not s.get("passed")]
        if failed_gates and not args.limit:
            msg = f"threshold gates FAILED: {', '.join(failed_gates)}"
            if ERR is not None:
                ERR.print(f"[red]{msg}[/red]")
            else:
                sys.stderr.write(f"{msg}\n")
            return 1
    if args.baseline:
        baselines_dir = getattr(args, "baselines", "evals/baselines")
        path = save_baseline(rec, args.baseline, out_dir=baselines_dir)
        print(f"baseline '{args.baseline}' saved -> {path}")
    return 0


def cmd_list(args) -> int:
    if args.what == "benchmarks":
        rows = [[b["name"], b["version"], b["pattern"], b["dataset"], b["description"]]
                for b in list_benchmarks(args.registry)]
        _print_table("Benchmarks", ["Name", "Ver", "Pattern", "Dataset", "Description"], rows)
    elif args.what == "evaluators":
        _print_table("Evaluators", ["Name"], [[e] for e in available_evaluators()])
    elif args.what == "datasets":
        rows = []
        for pattern in ("react", "plan_execute", "supervisor", "swarm", "map_reduce"):
            path = f"datasets/{pattern}/golden.jsonl"
            if os.path.isfile(path):
                st = dataset_stats(path)
                rows.append([pattern, str(st["cases"]),
                             ", ".join(f"{k}:{v}" for k, v in sorted(st["by_category"].items())),
                             st["sha256"]])
        _print_table("Datasets", ["Pattern", "Cases", "Categories", "sha256"], rows)
    return 0


def cmd_validate(args) -> int:
    issues: list[str] = []
    if args.dataset:
        issues = validate_dataset(args.dataset)
        target = args.dataset
    elif args.benchmark:
        bm = load_benchmark(args.benchmark, args.registry)
        issues = validate_dataset(_resolve_dataset(bm.dataset_path))
        target = args.benchmark
    else:  # all
        for b in list_benchmarks(args.registry):
            ds = _resolve_dataset(b["dataset"])
            issues += [f"{b['name']}: {i}" for i in validate_dataset(ds)]
        target = "all benchmarks"
    if issues:
        assert ERR is not None
        ERR.print("[red]INVALID[/red]")
        for i in issues[:30]:
            ERR.print(f"  - {i}")
        return 1
    print(f"VALID: {target}")
    return 0


def _resolve_dataset(path: str) -> str:
    for cand in (path, os.path.join("datasets", path),
                 os.path.join("datasets", os.path.basename(path))):
        if os.path.isfile(cand):
            return cand
    return path


def cmd_compare(args) -> int:
    a = _load_run(args.run_a, args.runs)
    b = _load_run(args.run_b, args.runs)
    comp = compare_runs(a, b)
    if args.json:
        print(dumps(comp))
        return 0
    _print_table(
        f"{a.benchmark}: {comp.run_a} vs {comp.run_b}",
        ["Metric", "A", "B", "Delta"],
        [["Pass rate", f"{comp.pass_rate_a:.1%}", f"{comp.pass_rate_b:.1%}",
          f"{comp.delta:+.3f}"],
         ["McNemar p", str(comp.mcnemar["p_value"]), "", ""],
         ["Flips P→F", str(len(comp.flips_pass_to_fail)),
          "; ".join(comp.flips_pass_to_fail[:6]), ""],
         ["Flips F→P", str(len(comp.flips_fail_to_pass)), "", ""]]
        + [[f"eval:{ev}", f"{s['mean_a']:.3f}", f"{s['mean_b']:.3f}",
            f"{s['delta']:+.3f}"] for ev, s in comp.per_evaluator.items()])
    for w in comp.version_warnings:
        assert ERR is not None
        ERR.print(f"[yellow]version drift: {w}[/yellow]")
    return 0


def cmd_report(args) -> int:
    rec = _load_run(args.run_id, args.runs)
    comparison = gate = None
    if args.compare:
        comparison = compare_runs(_load_run(args.compare, args.runs), rec)
    if args.baseline:
        gate = check_regression(rec, load_baseline(args.baseline, args.baselines))
    if args.format == "json":
        text = build_json_report(rec, comparison, gate)
    else:
        text = build_markdown(rec, comparison, gate)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"report written -> {args.out}")
    else:
        print(text)
    return 0


def cmd_regression(args) -> int:
    rec = _load_run(args.run_id, args.runs)
    base = load_baseline(args.baseline, args.baselines)
    gate = check_regression(rec, base, args.gates)
    if args.json:
        print(dumps(gate))
    else:
        verdict = "GATE PASS" if gate.passed else "GATE FAIL"
        _print_table(
            f"Regression gate vs '{base.name}' ({rec.benchmark})",
            ["Metric", "Baseline", "New", "Delta", "Threshold", "Verdict"],
            [[f.metric, f"{f.baseline:.3f}", f"{f.new:.3f}", f"{f.delta:+.3f}",
              f"{f.threshold:+.3f}", f.verdict] for f in gate.findings])
        print(f"{verdict}: {gate.summary}")
    return gate.exit_code


def cmd_ablate(args) -> int:
    result = run_ablation(args.benchmark,
                          args.profiles.split(",") if args.profiles else None,
                          skill=args.skill, seed=args.seed)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    rows = [[p, f"{r['pass_rate']:.1%}",
             f"{r['recovery_rate']:.0%}" if r["recovery_rate"] is not None else "n/a",
             f"{r['tool_efficiency']:.2f}" if r["tool_efficiency"] is not None else "n/a",
             f"{r['loop_rate']:.1%}"]
            for p, r in result["profiles"].items()]
    _print_table(f"Ablation study — {args.benchmark}",
                 ["Profile", "Pass rate", "Recovery", "Efficiency", "Loop rate"], rows)
    for p, a in result["attribution"].items():
        print(f"  {p}: pass-rate delta {a['pass_rate_delta']:+.3f}")
    return 0


def cmd_calibrate(args) -> int:
    if args.labels:
        result = compute_calibration(args.labels)
    else:
        result = export_calibration_sample(
            args.benchmark, sample_n=args.sample, seed=args.seed, skill=args.skill)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for k, v in result.items():
            print(f"  {k}: {v}")
    if "cohens_kappa" in result and not result["kappa_met"]:
        return 1
    return 0


def cmd_repro(args) -> int:
    result = run_repro(args.benchmark, repeats=args.repeats, seed=args.seed,
                       vary_seed=args.vary_seed, skill=args.skill)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    _print_table(f"Reproducibility — {args.benchmark}",
                 ["Run", "Pass rate"],
                 [[str(i + 1), f"{r:.1%}"] for i, r in enumerate(result["pass_rates"])])
    print(f"  max spread: {result['max_spread_pp']}pp "
          f"(target <= {result['target_within_pp']}pp: "
          f"{'MET' if result['target_met'] else 'MISSED'})")
    print(f"  byte-identical (same seed): {result['byte_identical_same_seed']}")
    return 0 if result["target_met"] else 1


def cmd_info(args) -> int:
    runs_dir = getattr(args, "runs", "evals/runs")
    rec = _load_run(args.run_id, runs_dir)
    print(dumps({k: v for k, v in rec.__dict__.items() if k != "verdicts"}
                if hasattr(rec, "__dict__") else rec))
    m = rec.metrics
    print(f"verdicts: {len(rec.verdicts)} | failures: "
          f"{sum(1 for v in rec.verdicts if not v.passed)}")
    return 0


# ---------------------------------------------------------------------------
# status — operator one-glance health view (FDE handover: what ops checks)
# ---------------------------------------------------------------------------

def _scan_runs(runs_dir: str) -> dict[str, dict]:
    """Lightweight scan of run records: latest run per benchmark."""
    latest: dict[str, dict] = {}
    if not os.path.isdir(runs_dir):
        return latest
    for fname in os.listdir(runs_dir):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(runs_dir, fname), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        bm = d.get("benchmark")
        if not bm:
            continue
        ts = d.get("recorded_at", "")
        if bm not in latest or ts > latest[bm].get("recorded_at", ""):
            latest[bm] = {"run_id": d.get("run_id", fname[:-5]),
                          "recorded_at": ts,
                          "pass_rate": d.get("metrics", {}).get("pass_rate"),
                          "cases": d.get("metrics", {}).get("cases"),
                          "agent": d.get("agent", ""),
                          "skill": d.get("config", {}).get("skill")}
    return latest


def cmd_status(args) -> int:
    runs = _scan_runs(args.runs)
    baselines: dict[str, dict] = {}
    if os.path.isdir(args.baselines):
        for fname in os.listdir(args.baselines):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(args.baselines, fname),
                          encoding="utf-8") as fh:
                    b = json.load(fh)
            except (OSError, ValueError):
                continue
            baselines[fname[:-5]] = b

    base_name = args.baseline or "main"
    base = baselines.get(base_name)
    bm_names = set(runs)
    try:
        bm_names |= {b["name"] for b in list_benchmarks(None)}
    except Exception:  # registry unavailable — fall back to runs only
        pass

    rows: list[list[str]] = []
    degraded: list[str] = []
    for bm in sorted(bm_names):
        r = runs.get(bm)
        base_pr = (base.get("metrics", {}).get("pass_rate")
                   if base and bm == base.get("benchmark") else None)
        if r is None:
            rows.append([bm, "—", "—", "—", "no runs yet"])
            continue
        pr = r["pass_rate"]
        delta = "—"
        verdict = "ok"
        if base_pr is not None and pr is not None:
            dpp = (pr - base_pr) * 100
            delta = f"{dpp:+.1f}pp"
            if dpp <= -3.0:
                verdict = "REGRESSION"
                degraded.append(bm)
            elif dpp <= -1.0:
                verdict = "watch"
        rows.append([bm, r["run_id"][:12], f"{pr:.1%}" if pr is not None else "—",
                     delta, verdict])

    _print_table(
        "agent-eval status — latest run per benchmark"
        + (f" vs baseline '{base_name}'" if base else ""),
        ["Benchmark", "Latest run", "Pass rate", "vs baseline", "Verdict"],
        rows)

    # dataset health (hash-verified golden sets)
    ds_rows = []
    for pattern in ("react", "plan_execute", "supervisor", "swarm", "map_reduce"):
        path = f"datasets/{pattern}/golden.jsonl"
        if os.path.isfile(path):
            st = dataset_stats(path)
            ds_rows.append([pattern, str(st["cases"]), st["sha256"]])
    if ds_rows:
        _print_table("Golden datasets (sha256-verified)",
                     ["Pattern", "Cases", "sha256[:16]"], ds_rows)

    # judge calibration state, if experiments have been run
    cal_note = "not measured yet (run: agent-eval calibrate)"
    exp_path = "evals/results/experiments.json"
    if os.path.isfile(exp_path):
        try:
            with open(exp_path, encoding="utf-8") as fh:
                exp = json.load(fh)
            cal = exp.get("calibration", {})
            if cal.get("cohens_kappa") is not None:
                cal_note = (f"kappa {cal['cohens_kappa']:.3f} "
                            f"(n={cal.get('n')}, target >= {cal.get('kappa_target')})")
        except (OSError, ValueError):
            pass
    print(f"judge calibration: {cal_note}")
    if degraded:
        msg = (f"REGRESSION in: {', '.join(degraded)} — "
               "run `agent-eval regression <run_id> --baseline main` for the gate")
        if ERR is not None:
            ERR.print(f"[red]{msg}[/red]")
        else:
            print(msg)
        return 1
    print("handover: see RUNBOOK.md (operations) · docs/fde/ (engagement record)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from agent_eval_harness.web.server import run_server

    run_server(host=args.host, port=args.port, runs_dir=args.runs, baselines_dir=args.baselines)
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-eval",
        description="pytest for Agentic AI — evaluation harness & benchmark runner")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a benchmark")
    run.add_argument("--benchmark", required=True)
    run.add_argument("--agent", default="")
    run.add_argument("--seed", type=int, default=20260912)
    run.add_argument("--skill", type=float, default=0.85)
    run.add_argument("--ablation", default=None,
                     help="override benchmark ablation profile")
    run.add_argument("--limit", type=int, default=None)
    run.add_argument("--out", dest="out_dir", default="evals/runs")
    run.add_argument("--registry", default=None)
    run.add_argument("--baseline", default=None, help="save run as named baseline")
    run.add_argument("--baselines", default="evals/baselines", help="output directory for saved baselines")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    ls = sub.add_parser("list", help="list benchmarks|evaluators|datasets")
    ls.add_argument("what", choices=["benchmarks", "evaluators", "datasets"])
    ls.add_argument("--registry", default=None)
    ls.set_defaults(func=cmd_list)

    val = sub.add_parser("validate", help="validate datasets & benchmarks")
    val.add_argument("--dataset", default=None)
    val.add_argument("--benchmark", default=None)
    val.add_argument("--registry", default=None)
    val.set_defaults(func=cmd_validate)

    cmp_ = sub.add_parser("compare", help="compare two runs")
    cmp_.add_argument("run_a")
    cmp_.add_argument("run_b")
    cmp_.add_argument("--runs", default="evals/runs")
    cmp_.add_argument("--json", action="store_true")
    cmp_.set_defaults(func=cmd_compare)

    rep = sub.add_parser("report", help="generate a run report")
    rep.add_argument("run_id")
    rep.add_argument("--format", choices=["md", "json"], default="md")
    rep.add_argument("--out", default=None)
    rep.add_argument("--compare", default=None, help="baseline run id for comparison")
    rep.add_argument("--baseline", default=None, help="named baseline for gate section")
    rep.add_argument("--baselines", default="evals/baselines")
    rep.add_argument("--runs", default="evals/runs")
    rep.set_defaults(func=cmd_report)

    reg = sub.add_parser("regression", help="check a run against a baseline gate")
    reg.add_argument("run_id")
    reg.add_argument("--baseline", required=True)
    reg.add_argument("--baselines", default="evals/baselines")
    reg.add_argument("--runs", default="evals/runs")
    reg.add_argument("--gates", default=None)
    reg.add_argument("--json", action="store_true")
    reg.set_defaults(func=cmd_regression)

    abl = sub.add_parser("ablate", help="harness ablation study")
    abl.add_argument("--benchmark", required=True)
    abl.add_argument("--profiles", default=None, help="comma-separated profile list")
    abl.add_argument("--skill", type=float, default=0.85)
    abl.add_argument("--seed", type=int, default=20260912)
    abl.add_argument("--json", action="store_true")
    abl.set_defaults(func=cmd_ablate)

    cal = sub.add_parser("calibrate", help="judge calibration vs human labels")
    cal.add_argument("--benchmark", default="react_basic")
    cal.add_argument("--sample", type=int, default=60)
    cal.add_argument("--seed", type=int, default=20260912)
    cal.add_argument("--skill", type=float, default=0.85)
    cal.add_argument("--labels", default=None, help="filled hand-label CSV")
    cal.add_argument("--json", action="store_true")
    cal.set_defaults(func=cmd_calibrate)

    repro = sub.add_parser("repro", help="reproducibility repeats")
    repro.add_argument("--benchmark", required=True)
    repro.add_argument("--repeats", type=int, default=5)
    repro.add_argument("--seed", type=int, default=20260912)
    repro.add_argument("--vary-seed", action="store_true")
    repro.add_argument("--skill", type=float, default=0.85)
    repro.add_argument("--json", action="store_true")
    repro.set_defaults(func=cmd_repro)

    info = sub.add_parser("info", help="run metadata")
    info.add_argument("run_id")
    info.add_argument("--runs", default="evals/runs", help="path to runs directory")
    info.set_defaults(func=cmd_info)

    status = sub.add_parser(
        "status", help="operator health view: latest runs vs baseline, datasets, judge")
    status.add_argument("--runs", default="evals/runs")
    status.add_argument("--baselines", default="evals/baselines")
    status.add_argument("--baseline", default=None,
                        help="baseline name to compare against (default: main)")
    status.set_defaults(func=cmd_status)

    srv = sub.add_parser(
        "serve", help="launch interactive web dashboard and API server")
    srv.add_argument("--host", default="127.0.0.1", help="host address (default: 127.0.0.1)")
    srv.add_argument("--port", type=int, default=8000, help="port number (default: 8000)")
    srv.add_argument("--runs", default="evals/runs", help="path to runs directory")
    srv.add_argument("--baselines", default="evals/baselines", help="path to baselines directory")
    srv.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        if ERR is not None:
            ERR.print("\n[yellow]Interrupted by user.[/yellow]")
        else:  # pragma: no cover
            print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except InfraError as exc:
        if ERR is not None:
            ERR.print(f"[red]error:[/red] {exc}")
        else:  # pragma: no cover
            print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        if ERR is not None:
            ERR.print(f"[red]error:[/red] {exc}")
        else:  # pragma: no cover
            print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
