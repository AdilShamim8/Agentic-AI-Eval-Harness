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
        "run_id": "webtest0001",
        "benchmark": "react_basic",
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
        headers={"Content-Type": "application/json"},
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
            headers={"Content-Type": "application/json"},
        )
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


# ---- dashboard hardening (Issues F + J) --------------------------------------


def _post(test_server, payload, raw=None, headers=None):
    data = raw if raw is not None else json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{test_server}/api/run", data=data, headers=headers or {"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            body = json.loads(body)
        except ValueError:
            pass
        return exc.code, body


def test_web_rejects_invalid_benchmark(test_server):
    code, body = _post(test_server, {"benchmark": "no_such_benchmark"})
    assert code == 400
    assert "error" in body


def test_web_rejects_invalid_skill(test_server):
    code, body = _post(test_server, {"benchmark": "react_basic", "skill": 1.5})
    assert code == 400
    code, body = _post(test_server, {"benchmark": "react_basic", "skill": "high"})
    assert code == 400


def test_web_rejects_invalid_limit(test_server):
    # v0.2.1 silently treated limit=0 (and negatives) as a FULL run
    code, body = _post(test_server, {"benchmark": "react_basic", "limit": 0})
    assert code == 400
    code, body = _post(test_server, {"benchmark": "react_basic", "limit": -3})
    assert code == 400
    code, body = _post(test_server, {"benchmark": "react_basic", "limit": "eight"})
    assert code == 400


def test_web_rejects_malformed_json_and_non_object(test_server):
    code, body = _post(test_server, None, raw=b"{not json")
    assert code == 400
    code, body = _post(test_server, None, raw=b"[1,2,3]")
    assert code == 400


def test_web_rejects_oversized_body(test_server):
    # declared length over the cap: refused before any body is read
    req = urllib.request.Request(
        f"{test_server}/api/run",
        data=b"",
        headers={"Content-Type": "application/json", "Content-Length": str(100 * 1024 * 1024)},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        code, body = resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        code, body = exc.code, json.loads(exc.read().decode("utf-8"))
    assert code == 413
    assert "too large" in body["error"]


def test_web_read_only_mode_refuses_execution(test_server, monkeypatch):
    """Issue F: a dashboard deployed with a read-only runs mount (the compose
    default) must refuse POST /api/run with an explicit 503, not fail at
    write time with an opaque 500."""
    monkeypatch.setattr(DashboardHandler, "runs_dir", "/nonexistent-readonly")
    code, body = _post(test_server, {"benchmark": "react_basic"})
    assert code == 503
    assert "READ-ONLY VIEWER" in body["error"]
    monkeypatch.undo()
    # writable dir (the fixture's tmp runs dir) still executes
    code, body = _post(test_server, {"benchmark": "react_basic", "limit": 2})
    assert code == 200
    assert body["benchmark"] == "react_basic"


def test_web_index_escapes_untrusted_record_fields(test_server):
    """Stored-XSS regression: a malicious run record (run_id/benchmark/
    category/failure_class/final_answer carrying markup and quotes) must be
    rendered inert by the client (esc() + data-run-id, no inline onclick)."""
    import os

    payload = {
        "run_id": "xss'); alert(1); ('",
        "benchmark": 'react"><img src=x onerror=alert(2)>',
        "metrics": {"pass_rate": 0.5, "cases": 1},
        "recorded_at": '"><script>alert(3)</script>',
        "verdicts": [
            {
                "case_id": "c1'><script>alert(4)</script>",
                "category": "normal onload=alert(5)",
                "passed": False,
                "failure_class": "test_failure",
                "tool_calls": 0,
                "final_answer": "<b>bold</b> 'quoted' \"dq\"",
            }
        ],
    }
    with open(os.path.join(DashboardHandler.runs_dir, "xssrec.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    with urllib.request.urlopen(f"{test_server}/") as resp:
        html = resp.read().decode("utf-8")
    # the page ships an esc() helper and never builds inline onclick strings
    assert "function esc(" in html
    assert "onclick=" not in html
    # the record data is fetched via /api — server renders it as inert JSON
    with urllib.request.urlopen(f"{test_server}/api/runs/xssrec") as resp:
        served = json.loads(resp.read().decode("utf-8"))
    assert served["benchmark"] == payload["benchmark"]  # stored payload served
    # no raw HTML reflection server-side: JSON content-type + nosniff
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    os.unlink(os.path.join(DashboardHandler.runs_dir, "xssrec.json"))
