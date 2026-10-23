"""Integration: runner end-to-end on every pattern (small slices)."""

import json
import os

import pytest

from agent_eval_harness.registry.registry import load_benchmark
from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig

PATTERNS = [
    "react_basic",
    "plan_execute_basic",
    "supervisor_basic",
    "swarm_basic",
    "map_reduce_basic",
]


@pytest.mark.parametrize("benchmark", PATTERNS)
def test_runner_produces_valid_record(tmp_path, benchmark):
    bm = load_benchmark(benchmark)
    runner = BenchmarkRunner(
        bm, RunConfig(benchmark=benchmark, skill=0.9, seed=99, limit=6, out_dir=str(tmp_path))
    )
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
        cases = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        assert len(cases) >= 50, pattern
        total += len(cases)
        cats = {c["category"] for c in cases}
        assert cats == {
            "normal",
            "difficult",
            "ambiguous",
            "edge",
            "adversarial",
            "failure_inducing",
        }
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
    r = subprocess.run(
        [sys.executable, "scripts/generate_datasets.py", "--no-verify", "--out", str(out)],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-500:]
    for pattern in ("react", "plan_execute", "supervisor", "swarm", "map_reduce"):
        fresh = hashlib.sha256(
            (out / pattern / "golden.jsonl").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        committed = hashlib.sha256(
            open(f"datasets/{pattern}/golden.jsonl", "rb").read().replace(b"\r\n", b"\n")
        ).hexdigest()
        assert fresh == committed, f"{pattern} dataset drifted"


# ---- live-judge fallback visibility at run level (Issue E) -------------------


def test_live_judge_fallbacks_are_counted_and_visible(tmp_path, monkeypatch):
    """A blocking live-judge evaluator that degrades to the rubric backend
    must be visible in the run record: metrics.judge_fallbacks + events.
    Uses a transport double (HTTPError 429) — no real endpoint, no cost."""
    import urllib.error
    import yaml

    registry = tmp_path / "benchmarks"
    registry.mkdir()
    (registry / "live_probe.yaml").write_text(
        yaml.safe_dump(
            {
                "benchmark": {"name": "live_probe", "version": "1.0", "pattern": "react"},
                "dataset": {"path": "datasets/react/golden.jsonl"},
                "evaluators": ["llm_answer_correctness", "task_checks"],
                "thresholds": {"overall_pass_rate": 0.5},
                "execution": {"limit": 3},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AEH_JUDGE_BACKEND", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("AEH_PROMPTS_DIR", "prompts")

    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        raise urllib.error.HTTPError("url", 429, "Too Many Requests", hdrs=None, fp=None)

    monkeypatch.setattr(
        "agent_eval_harness.evaluators.llm_judge.judge.urllib.request.urlopen", fake_urlopen
    )

    bm = load_benchmark("live_probe", registry_dirs=[str(registry), "benchmarks"])
    runner = BenchmarkRunner(bm, RunConfig(benchmark="live_probe", out_dir=str(tmp_path / "runs")))
    rec = runner.run()

    # every judged case fell back — and it is RECORDED, not silent
    assert rec.metrics.get("judge_fallbacks", {}).get("llm_answer_correctness") == 3
    # deterministic evaluators (task_checks) are NOT fallbacks and NOT errors
    assert "task_checks" not in rec.metrics.get("judge_fallbacks", {})
    assert all("llm_answer_correctness" not in v.evaluator_errors for v in rec.verdicts), (
        "fallback must not be an evaluator error"
    )
    # verdicts still carry rubric scores as evidence
    assert all("llm_answer_correctness" in v.scores for v in rec.verdicts)
    # event log carries per-case fallback evidence
    lines = [json.loads(l) for l in open(rec.events_path, encoding="utf-8")]
    fb_events = [e for e in lines if e["kind"] == "judge_fallback"]
    assert len(fb_events) == 3
    assert "live judge failed" in fb_events[0]["payload"]["note"]
    # the persisted record keeps the counts
    data = json.load(open(f"{tmp_path}/runs/{rec.run_id}.json"))
    assert data["metrics"]["judge_fallbacks"]["llm_answer_correctness"] == 3


def test_live_judge_reaches_local_endpoint_during_sandboxed_run(tmp_path, monkeypatch):
    """Issue D regression: a live judge must be able to perform its AUTHORIZED
    HTTP evaluation while the benchmark run's network sandbox is active.

    Uses a controlled local HTTP double (no external service, no cost):
    the double records every request it serves — proof that judge traffic
    flowed during the run while arbitrary agent socket creation stays blocked.
    """
    import http.server
    import json as _json
    import threading
    import urllib.error

    served = []  # (path, body) of every judge request served during the run

    class _JudgeDouble(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length)
            served.append((self.path, body))
            payload = _json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": _json.dumps(
                                    {
                                        "score": 0.95,
                                        "passed": True,
                                        "rationale": "live double",
                                        "confidence": 0.9,
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _JudgeDouble)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        import yaml

        registry = tmp_path / "benchmarks"
        registry.mkdir(exist_ok=True)
        (registry / "live_probe2.yaml").write_text(
            yaml.safe_dump(
                {
                    "benchmark": {"name": "live_probe2", "version": "1.0", "pattern": "react"},
                    "dataset": {"path": "datasets/react/golden.jsonl"},
                    "evaluators": ["llm_answer_correctness"],
                    "thresholds": {"overall_pass_rate": 0.5},
                    "execution": {"limit": 3},
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setenv("AEH_JUDGE_BACKEND", "live")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{srv.server_address[1]}/v1")
        monkeypatch.setenv("AEH_PROMPTS_DIR", "prompts")

        bm = load_benchmark("live_probe2", registry_dirs=[str(registry), "benchmarks"])
        runner = BenchmarkRunner(
            bm, RunConfig(benchmark="live_probe2", out_dir=str(tmp_path / "runs"))
        )
        rec = runner.run()

        # the judge served every case over HTTP DURING the sandboxed run
        assert len(served) == 3
        assert all(p == "/v1/chat/completions" for p, _ in served)
        # no fallback occurred (all live responses valid)
        assert "judge_fallbacks" not in rec.metrics
        # live scores came from the double (0.95), not the rubric
        assert all(v.scores["llm_answer_correctness"] == 0.95 for v in rec.verdicts)
        # and agent-side network creation was blocked the whole time — the
        # guard stayed installed for the run (no attempts by the built-in
        # agent, which is offline by construction)
        assert rec.metrics["network_guard_attempts"] == []
    finally:
        srv.shutdown()
        srv.server_close()
