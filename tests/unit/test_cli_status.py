"""Operator `status` command tests (FDE handover surface).

The status command is the weekly one-glance health view an operator checks
after handover — it must degrade gracefully (no runs, no baselines, no
registry) and flag regressions against the named baseline.
"""
from __future__ import annotations

import json
import os

from agent_eval_harness.cli.app import _scan_runs, cmd_status


class _Args:
    def __init__(self, runs: str, baselines: str, baseline: str | None):
        self.runs = runs
        self.baselines = baselines
        self.baseline = baseline


def _write_run(runs_dir: str, run_id: str, benchmark: str, pass_rate: float,
               recorded_at: str = "2026-09-12T00:00:00+0000") -> None:
    os.makedirs(runs_dir, exist_ok=True)
    rec = {"run_id": run_id, "benchmark": benchmark, "recorded_at": recorded_at,
           "agent": "builtin:react",
           "metrics": {"pass_rate": pass_rate, "cases": 56}}
    with open(os.path.join(runs_dir, f"{run_id}.json"), "w",
              encoding="utf-8") as fh:
        json.dump(rec, fh)


def test_scan_runs_picks_latest_per_benchmark(tmp_path):
    runs = str(tmp_path / "runs")
    _write_run(runs, "aaa", "react_basic", 0.89, "2026-09-10T00:00:00+0000")
    _write_run(runs, "bbb", "react_basic", 0.62, "2026-09-12T00:00:00+0000")
    _write_run(runs, "ccc", "swarm_basic", 0.82)
    latest = _scan_runs(runs)
    assert latest["react_basic"]["run_id"] == "bbb"
    assert latest["react_basic"]["pass_rate"] == 0.62
    assert latest["swarm_basic"]["run_id"] == "ccc"


def test_scan_runs_ignores_corrupt_and_events(tmp_path):
    runs = str(tmp_path / "runs")
    os.makedirs(runs)
    with open(os.path.join(runs, "x.events.jsonl"), "w") as fh:
        fh.write("{}")
    with open(os.path.join(runs, "bad.json"), "w") as fh:
        fh.write("{not json")
    assert _scan_runs(runs) == {}


def test_status_degrades_gracefully_when_empty(tmp_path, capsys):
    rc = cmd_status(_Args(str(tmp_path / "none"), str(tmp_path / "none2"), None))
    out = capsys.readouterr().out
    assert rc == 0
    assert "no runs yet" in out


def test_status_flags_regression_vs_baseline(tmp_path, capsys):
    runs = str(tmp_path / "runs")
    bases = str(tmp_path / "bases")
    _write_run(runs, "reg", "react_basic", 0.62)          # -26.8pp vs baseline
    os.makedirs(bases)
    with open(os.path.join(bases, "main.json"), "w", encoding="utf-8") as fh:
        json.dump({"benchmark": "react_basic",
                   "metrics": {"pass_rate": 0.893}}, fh)
    rc = cmd_status(_Args(runs, bases, "main"))
    out = capsys.readouterr().out
    assert rc == 1                                        # operator must be alerted
    assert "REGRESSION" in out
    assert "-27.3pp" in out


def test_status_ok_when_matching_baseline(tmp_path, capsys):
    runs = str(tmp_path / "runs")
    bases = str(tmp_path / "bases")
    _write_run(runs, "ok", "react_basic", 0.89)
    os.makedirs(bases)
    with open(os.path.join(bases, "main.json"), "w", encoding="utf-8") as fh:
        json.dump({"benchmark": "react_basic",
                   "metrics": {"pass_rate": 0.893}}, fh)
    rc = cmd_status(_Args(runs, bases, "main"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "ok" in out
    assert "+0.0pp" in out or "-0.3pp" in out


def test_load_run_direct_path_and_suffix(tmp_path, capsys):
    import argparse
    from agent_eval_harness.cli.app import _load_run, cmd_info

    runs = str(tmp_path / "runs")
    os.makedirs(runs)
    sample_run = {
        "run_id": "test_run_123",
        "benchmark": "react_basic",
        "benchmark_version": "1.0",
        "agent": "builtin:react",
        "agent_pattern": "react",
        "seed": 20260912,
        "ablation": "full",
        "versions": {},
        "config": {},
        "verdicts": [],
        "metrics": {"cases": 0, "passed": 0, "pass_rate": 0.0},
        "recorded_at": "2026-09-12T00:00:00+0000",
    }
    json_path = os.path.join(runs, "test_run_123.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(sample_run, fh)

    # 1. Load by ID
    r1 = _load_run("test_run_123", runs)
    assert r1.run_id == "test_run_123"

    # 2. Load with .json suffix
    r2 = _load_run("test_run_123.json", runs)
    assert r2.run_id == "test_run_123"

    # 3. Load by direct path
    r3 = _load_run(json_path)
    assert r3.run_id == "test_run_123"

    # 4. cmd_info with --runs argument
    args = argparse.Namespace(run_id="test_run_123", runs=runs)
    assert cmd_info(args) == 0
    out = capsys.readouterr().out
    assert "test_run_123" in out



# ---- CLI works without rich (Issue K) ----------------------------------------
# The documented minimal install has NO rich (PyYAML is the only runtime
# dependency). Every error/warning path must work there.


def test_validate_invalid_dataset_without_rich(capsys, tmp_path):
    """v0.2.1 defect: cmd_validate crashed with AssertionError when rich was
    absent and a dataset had issues."""
    from agent_eval_harness import cli

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id":"x1","pattern":"react","category":"nope","task":"t",'
                   '"expected":{}}\n', encoding="utf-8")

    assert cli.app.RICH is False or cli.app.RICH is True  # module accessible
    import agent_eval_harness.cli.app as app
    import argparse

    ns = argparse.Namespace(dataset=str(bad), benchmark=None, registry=None)
    rc = app.cmd_validate(ns)
    assert rc == 1
    err_out = capsys.readouterr().err
    assert "INVALID" in err_out
    assert "category" in err_out
    assert "Traceback" not in err_out and "AssertionError" not in err_out


def test_compare_version_drift_warning_without_rich(capsys):
    import agent_eval_harness.cli.app as app
    import argparse
    from agent_eval_harness.core.schemas import RunRecord, CaseVerdict
    from agent_eval_harness.core.errors import FailureClass

    def _mk(rid, ds_rev):
        v = CaseVerdict(case_id="c1", pattern="react", category="normal",
                        passed=True, failure_class=FailureClass.NONE, scores={})
        return RunRecord(
            run_id=rid, benchmark="react_basic", benchmark_version="1.0",
            agent="builtin:react", agent_pattern="react", seed=1, ablation="full",
            versions={"dataset": {"revision": ds_rev}}, config={}, verdicts=[v],
            metrics={"pass_rate": 1.0, "cases": 1, "per_evaluator": {}})

    import json as _json
    import tempfile
    import os
    from agent_eval_harness.core.schemas import to_jsonable
    with tempfile.TemporaryDirectory() as td:
        for rid, rev in (("ra", "aaa"), ("rb", "bbb")):
            with open(os.path.join(td, f"{rid}.json"), "w", encoding="utf-8") as fh:
                fh.write(_json.dumps(to_jsonable(_mk(rid, rev))))
        ns = argparse.Namespace(run_a="ra", run_b="rb", runs=td, json=False)
        rc = app.cmd_compare(ns)
        assert rc == 0
        err_out = capsys.readouterr().err
        assert "version drift" in err_out
        assert "Traceback" not in err_out


def test_cli_subprocess_without_rich(tmp_path):
    """End-to-end: run the real CLI entry point in a subprocess where `rich`
    is unimportable (simulated absence) — invalid dataset must produce a
    controlled exit 1 with clean INVALID output, not an AssertionError."""
    import subprocess
    import sys

    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "rich").mkdir()
    (shim / "rich" / "__init__.py").write_text(
        "raise ImportError('rich is not installed (simulated)')\n",
        encoding="utf-8")

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id":"x1","pattern":"react","category":"nope","task":"t",'
                   '"expected":{}}\n', encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(shim) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(
        [sys.executable, "-m", "agent_eval_harness.cli.app",
         "validate", "--dataset", str(bad)],
        capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 1, r.stderr[-500:]
    assert "INVALID" in r.stderr or "INVALID" in r.stdout
    assert "AssertionError" not in r.stderr + r.stdout
    assert "Traceback" not in r.stderr + r.stdout
