"""Unit tests for the built-in web dashboard server and REST API."""
import json
import os
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from agent_eval_harness.web.server import DashboardHandler


@pytest.fixture(scope="module")
def test_server(tmp_path_factory):
    # ISOLATION: serve from throwaway dirs — tests must not write into the
    # repo's shared evals/runs (tracked run records must not be churned by tests).
    import tempfile
    runs_dir = str(tmp_path_factory.mktemp("web_runs"))
    baselines_dir = str(tmp_path_factory.mktemp("web_baselines"))
    # seed the throwaway runs dir with one valid record so list endpoints have data
    import json as _json
    _rec = {
        "run_id": "webtest0001", "benchmark": "react_basic",
        "metrics": {"pass_rate": 0.9, "cases": 10},
        "recorded_at": "2026-10-01T00:00:00+0000",
    }
    with open(os.path.join(runs_dir, "webtest0001.json"), "w", encoding="utf-8") as fh:
        _json.dump(_rec, fh)
    DashboardHandler.runs_dir = runs_dir
    DashboardHandler.baselines_dir = baselines_dir
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{host}:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


def test_web_index(test_server):
    with urllib.request.urlopen(f"{test_server}/") as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "agent-eval-harness" in content
        assert "Run Inspector" in content


def test_web_api_status(test_server):
    with urllib.request.urlopen(f"{test_server}/api/status") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "healthy"
        assert "total_runs" in data


def test_web_api_runs(test_server):
    with urllib.request.urlopen(f"{test_server}/api/runs") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "runs" in data
        assert isinstance(data["runs"], list)


def test_web_api_benchmarks(test_server):
    with urllib.request.urlopen(f"{test_server}/api/benchmarks") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "benchmarks" in data
        names = [b["name"] for b in data["benchmarks"]]
        assert "react_basic" in names


def test_web_api_baselines(test_server):
    with urllib.request.urlopen(f"{test_server}/api/baselines") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "baselines" in data


def test_web_api_execute_run(test_server):
    req = urllib.request.Request(
        f"{test_server}/api/run",
        data=json.dumps({"benchmark": "react_basic", "limit": 2, "skill": 0.9}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "run_id" in data
        assert data["benchmark"] == "react_basic"
        assert len(data["verdicts"]) == 2


def test_web_api_get_run_not_found(test_server):
    import urllib.error
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{test_server}/api/runs/nonexistent_run_id_12345")
    assert exc_info.value.code == 404


def test_web_api_path_traversal_sanitized(test_server):
    import urllib.error
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{test_server}/api/runs/../../etc/passwd")
    assert exc_info.value.code == 404


def test_web_api_unknown_route(test_server):
    import urllib.error
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{test_server}/api/unknown_endpoint")
    assert exc_info.value.code == 404



# ---- POST /api/run serialization (Issue G) -----------------------------------


def test_web_execute_run_is_serialized(test_server, monkeypatch):
    """Two concurrent POST /api/run executions must not overlap: runs write
    shared artifacts and contend on the process-global network guard. The
    handler serializes them via a lock (single-operator ops tool)."""
    import agent_eval_harness.web.server as server_mod

    spans = []  # (start, end) per execution
    import time as _time

    class _FakeRecord:
        run_id = "fake0001"
        benchmark = "react_basic"
        pass_rate = 0.9
        recorded_at = "2026-10-01T00:00:00+0000"
        metrics = {"pass_rate": 0.9, "cases": 2, "threshold_gates": {}}
        verdicts = []

    def fake_run(self):
        t0 = _time.perf_counter()
        _time.sleep(0.25)
        spans.append((t0, _time.perf_counter()))
        return _FakeRecord()

    monkeypatch.setattr(server_mod.BenchmarkRunner, "run", fake_run)

    import concurrent.futures
    reqs = [
        urllib.request.Request(
            f"{test_server}/api/run",
            data=json.dumps({"benchmark": "react_basic", "limit": 2}).encode(),
            headers={"Content-Type": "application/json"})
        for _ in range(2)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda r: urllib.request.urlopen(r, timeout=10), reqs))
    for resp in results:
        assert resp.status == 200
        body = json.loads(resp.read().decode("utf-8"))
        assert body["run_id"] == "fake0001"

    assert len(spans) == 2
    a, b = sorted(spans)
    assert b[0] >= a[1], f"executions overlapped: {spans}"
