"""AEH_RUNS_DIR / AEH_BASELINES_DIR wiring — the Dockerfile declares these;
they are the single source of truth for storage defaults (container
deployments configure locations exclusively through them)."""

import json
import os

import pytest

from agent_eval_harness.core.paths import default_baselines_dir, default_runs_dir


def test_defaults_without_env(monkeypatch):
    monkeypatch.delenv("AEH_RUNS_DIR", raising=False)
    monkeypatch.delenv("AEH_BASELINES_DIR", raising=False)
    assert default_runs_dir() == "evals/runs"
    assert default_baselines_dir() == "evals/baselines"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("AEH_RUNS_DIR", "/custom/runs")
    monkeypatch.setenv("AEH_BASELINES_DIR", "/custom/baselines")
    assert default_runs_dir() == "/custom/runs"
    assert default_baselines_dir() == "/custom/baselines"


def test_runconfig_default_out_dir_follows_env(tmp_path, monkeypatch):
    """RunConfig() with no out_dir must land records in $AEH_RUNS_DIR."""
    from agent_eval_harness.registry.registry import load_benchmark
    from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig

    monkeypatch.setenv("AEH_RUNS_DIR", str(tmp_path))
    bm = load_benchmark("react_basic")
    runner = BenchmarkRunner(bm, RunConfig(benchmark="react_basic", limit=2))
    assert runner.config.out_dir == str(tmp_path)
    rec = runner.run()
    assert os.path.isfile(os.path.join(str(tmp_path), f"{rec.run_id}.json"))
    assert rec.events_path.startswith(str(tmp_path))


def test_cli_run_respects_env_runs_dir(tmp_path, monkeypatch):
    """End-to-end CLI: `agent-eval run` writes to $AEH_RUNS_DIR when --out is
    absent, and `agent-eval regression` finds the record there."""
    import subprocess
    import sys

    runs = tmp_path / "env_runs"
    monkeypatch.setenv("AEH_RUNS_DIR", str(runs))
    monkeypatch.setenv("AEH_BASELINES_DIR", str(tmp_path / "env_baselines"))
    env = dict(os.environ)
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_eval_harness.cli.app",
            "run",
            "--benchmark",
            "react_basic",
            "--limit",
            "2",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr[-500:]
    rec = json.loads(r.stdout)
    assert (runs / f"{rec['run_id']}.json").is_file(), "CLI run must persist into $AEH_RUNS_DIR"
