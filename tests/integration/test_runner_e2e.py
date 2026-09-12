"""Integration: runner end-to-end on every pattern (small slices)."""
import json
import os

import pytest

from agent_eval_harness.registry.registry import load_benchmark
from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig

PATTERNS = ["react_basic", "plan_execute_basic", "supervisor_basic",
            "swarm_basic", "map_reduce_basic"]


@pytest.mark.parametrize("benchmark", PATTERNS)
def test_runner_produces_valid_record(tmp_path, benchmark):
    bm = load_benchmark(benchmark)
    runner = BenchmarkRunner(bm, RunConfig(benchmark=benchmark, skill=0.9,
                                           seed=99, limit=6,
                                           out_dir=str(tmp_path)))
    rec = runner.run()
    assert 0 < len(rec.verdicts) <= 6
    assert rec.metrics["cases"] == len(rec.verdicts)
    assert 0.0 <= rec.pass_rate <= 1.0
    assert len(rec.metrics["pass_rate_ci95"]) == 2
    # run record + events persisted
    assert os.path.isfile(f"{tmp_path}/{rec.run_id}.json")
    assert os.path.isfile(rec.events_path)
    data = json.load(open(f"{tmp_path}/{rec.run_id}.json"))
    assert data["run_id"] == rec.run_id
    assert data["versions"]["dataset"]["revision"]
    # events are valid JSONL and redacted
    lines = [json.loads(l) for l in open(rec.events_path)]
    assert any(e["kind"] == "run_start" for e in lines)
    assert any(e["kind"] == "case_end" for e in lines)
    assert all("sk-" not in json.dumps(e) for e in lines)


def test_full_dataset_integrity_counts():
    total = 0
    for pattern in ("react", "plan_execute", "supervisor", "swarm", "map_reduce"):
        path = f"datasets/{pattern}/golden.jsonl"
        cases = [json.loads(l) for l in open(path) if l.strip()]
        assert len(cases) >= 50, pattern
        total += len(cases)
        cats = {c["category"] for c in cases}
        assert cats == {"normal", "difficult", "ambiguous", "edge",
                        "adversarial", "failure_inducing"}
        ids = [c["id"] for c in cases]
        assert len(ids) == len(set(ids))
    assert total >= 250


def test_dataset_regenerates_byte_identical(tmp_path):
    """Deterministic generation: rerunning the generator yields identical hashes."""
    import hashlib
    import subprocess
    import sys

    env = dict(os.environ)
    out = tmp_path / "ds"
    r = subprocess.run([sys.executable, "scripts/generate_datasets.py",
                        "--no-verify", "--out", str(out)],
                       capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr[-500:]
    for pattern in ("react", "plan_execute", "supervisor", "swarm", "map_reduce"):
        fresh = hashlib.sha256((out / pattern / "golden.jsonl").read_bytes()).hexdigest()
        committed = hashlib.sha256(
            open(f"datasets/{pattern}/golden.jsonl", "rb").read()).hexdigest()
        assert fresh == committed, f"{pattern} dataset drifted"
