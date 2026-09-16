"""Unit tests for the built-in web dashboard server and REST API."""
import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from agent_eval_harness.web.server import DashboardHandler


@pytest.fixture(scope="module")
def test_server():
    DashboardHandler.runs_dir = "evals/runs"
    DashboardHandler.baselines_dir = "evals/baselines"
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

