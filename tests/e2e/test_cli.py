"""E2E: CLI subprocess invocations + report generation + pytest bridge."""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def cli(*args, cwd=REPO):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(REPO, "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, "-m", "agent_eval_harness.cli.app", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env, cwd=cwd, timeout=300)


def test_cli_version_and_list():
    r = cli("--version")
    assert r.returncode == 0 and "0.2.1" in r.stdout
    r = cli("list", "benchmarks")
    assert r.returncode == 0 and "react_basic" in r.stdout
    r = cli("list", "evaluators")
    assert "task_checks" in r.stdout and "llm_answer_correctness" in r.stdout
    r = cli("list", "datasets")
    assert "56" in r.stdout


def test_cli_validate():
    r = cli("validate")
    assert r.returncode == 0 and "VALID" in r.stdout


def test_cli_validate_bad_dataset(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "x", "pattern": "nope", "category": "nope", "task": "t", "expected": {}}\n')
    r = cli("validate", "--dataset", str(bad))
    assert r.returncode == 1


def test_cli_run_report_compare_regression(tmp_path):
    out = str(tmp_path / "runs")
    r = cli("run", "--benchmark", "react_basic", "--limit", "5", "--seed", "7",
            "--skill", "0.95", "--out", out)
    assert r.returncode == 0, r.stderr
    run_id = [f[:-5] for f in os.listdir(out) if f.endswith(".json")][0]

    r = cli("report", run_id, "--runs", out, "--format", "md", "--out", str(tmp_path / "r.md"))
    assert r.returncode == 0
    md = open(tmp_path / "r.md", encoding="utf-8").read()
    assert "Evaluation Run Report" in md
    assert "TEST FAILURE" in md and "EVALUATOR ERROR" in md and \
        "INFRASTRUCTURE FAILURE" in md
    assert "Recommendations" in md and "Not measured" in md

    r = cli("report", run_id, "--runs", out, "--format", "json", "--out", str(tmp_path / "r.json"))
    payload = json.load(open(tmp_path / "r.json", encoding="utf-8"))
    assert payload["kind"] == "agent-eval-harness/report"
    assert payload["run"]["run_id"] == run_id

    # second run at low skill -> compare + regression gates
    r = cli("run", "--benchmark", "react_basic", "--limit", "5", "--seed", "7",
            "--skill", "0.4", "--out", out)
    assert r.returncode in (0, 1)
    ids = sorted(f[:-5] for f in os.listdir(out) if f.endswith(".json"))
    assert len(ids) == 2
    r = cli("compare", ids[0], ids[1], "--runs", out)
    assert r.returncode == 0 and "Pass rate" in r.stdout


def test_cli_regression_gate_flow(tmp_path):
    """Baseline vs degraded challenger -> exit 1; vs itself -> exit 0."""
    out = str(tmp_path / "runs")
    cli("run", "--benchmark", "react_basic", "--limit", "12", "--seed", "3",
        "--skill", "0.95", "--out", out, "--baseline", "gate-test",
        )
    base_dir = tmp_path / "baselines"
    base_dir.mkdir()
    # move baseline to tmp dir for isolation
    import shutil

    shutil.move("evals/baselines/gate-test.json", base_dir / "gate-test.json")
    good = sorted(f[:-5] for f in os.listdir(out) if f.endswith(".json"))[0]
    r = cli("regression", good, "--baseline", "gate-test",
            "--baselines", str(base_dir), "--runs", out)
    assert r.returncode == 0, r.stdout + r.stderr

    r = cli("run", "--benchmark", "react_basic", "--limit", "12", "--seed", "3",
            "--skill", "0.4", "--ablation", "no_retry", "--out", out)
    import re as _re

    m = _re.search(r"Run (\w{16})", r.stdout)
    assert m, r.stdout + r.stderr
    bad = m.group(1)
    r = cli("regression", bad, "--baseline", "gate-test",
            "--baselines", str(base_dir), "--runs", out)
    assert r.returncode == 1
    assert "REGRESSION DETECTED" in r.stdout


def test_pytest_bridge_fixture():
    """The eval_case fixture runs a real benchmark slice inside pytest."""
    rate = None
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "bridge_mod", os.path.join(os.path.dirname(__file__), "_bridge_mod.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rate = mod.run_bridge()
    assert 0.0 <= rate <= 1.0
