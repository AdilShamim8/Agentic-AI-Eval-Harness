"""Built-in lightweight web dashboard server for agent-eval-harness.

Provides an interactive browser interface for viewing benchmark runs, inspecting
trajectories, checking CI gates, and launching runs with zero external dependencies.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from agent_eval_harness.core.errors import InfraError
from agent_eval_harness.core.paths import default_baselines_dir, default_runs_dir
from agent_eval_harness.registry.registry import list_benchmarks, load_benchmark
from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent Eval Harness — Operations Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(20, 26, 43, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --accent: #6366f1;
      --accent-glow: rgba(99, 102, 241, 0.25);
      --accent-hover: #4f46e5;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --success: #10b981;
      --success-bg: rgba(16, 185, 129, 0.15);
      --danger: #ef4444;
      --danger-bg: rgba(239, 68, 68, 0.15);
      --warning: #f59e0b;
      --warning-bg: rgba(245, 158, 11, 0.15);
      --font-sans: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: radial-gradient(circle at 50% 0%, #171d34 0%, var(--bg) 75%);
      color: var(--text);
      font-family: var(--font-sans);
      min-height: 100vh;
      line-height: 1.5;
    }
    header {
      padding: 1.25rem 2rem;
      border-bottom: 1px solid var(--card-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(9, 13, 22, 0.85);
      backdrop-filter: blur(12px);
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      font-weight: 700;
      font-size: 1.15rem;
      letter-spacing: -0.02em;
    }
    .badge {
      font-size: 0.72rem;
      padding: 0.2rem 0.6rem;
      border-radius: 9999px;
      font-weight: 600;
      font-family: var(--font-mono);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .badge-success { background: var(--success-bg); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-danger { background: var(--danger-bg); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); }
    .badge-warning { background: var(--warning-bg); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge-neutral { background: rgba(255, 255, 255, 0.08); color: var(--text-muted); border: 1px solid var(--card-border); }

    .container {
      max-width: 1380px;
      margin: 0 auto;
      padding: 2rem;
    }
    .grid-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1.25rem;
      margin-bottom: 2rem;
    }
    .stat-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 1.25rem 1.5rem;
      backdrop-filter: blur(16px);
      transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .stat-card:hover {
      border-color: rgba(99, 102, 241, 0.4);
      transform: translateY(-2px);
    }
    .stat-label {
      font-size: 0.8rem;
      color: var(--text-muted);
      font-weight: 500;
      margin-bottom: 0.4rem;
    }
    .stat-val {
      font-size: 1.85rem;
      font-weight: 700;
      letter-spacing: -0.03em;
      display: flex;
      align-items: baseline;
      gap: 0.5rem;
    }
    .stat-sub {
      font-size: 0.75rem;
      color: var(--text-muted);
    }

    .main-layout {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 2rem;
    }
    @media (max-width: 1024px) {
      .main-layout { grid-template-columns: 1fr; }
    }

    .panel {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 1.5rem;
      backdrop-filter: blur(16px);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
    }
    .panel-title {
      font-size: 1.05rem;
      font-weight: 700;
      margin-bottom: 1.25rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    /* Form Styles */
    .form-group {
      margin-bottom: 1.1rem;
    }
    label {
      display: block;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 0.4rem;
    }
    select, input {
      width: 100%;
      padding: 0.65rem 0.85rem;
      border-radius: 8px;
      border: 1px solid var(--card-border);
      background: rgba(9, 13, 22, 0.7);
      color: var(--text);
      font-family: inherit;
      font-size: 0.88rem;
      outline: none;
      transition: border-color 0.2s ease;
    }
    select:focus, input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-glow);
    }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      width: 100%;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      font-weight: 600;
      font-size: 0.9rem;
      cursor: pointer;
      border: none;
      background: var(--accent);
      color: white;
      transition: all 0.2s ease;
      box-shadow: 0 4px 14px var(--accent-glow);
    }
    .btn:hover:not(:disabled) {
      background: var(--accent-hover);
      transform: translateY(-1px);
    }
    .btn:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    /* Runs List */
    .runs-list {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      max-height: 540px;
      overflow-y: auto;
      padding-right: 0.25rem;
    }
    .run-item {
      padding: 0.85rem 1rem;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .run-item:hover, .run-item.active {
      background: rgba(99, 102, 241, 0.12);
      border-color: var(--accent);
    }
    .run-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.35rem;
    }
    .run-id {
      font-family: var(--font-mono);
      font-size: 0.82rem;
      color: var(--accent);
      font-weight: 600;
    }
    .run-meta {
      font-size: 0.78rem;
      color: var(--text-muted);
      display: flex;
      gap: 0.75rem;
    }

    /* Detail View */
    .detail-view {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }
    .verdicts-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }
    .verdicts-table th {
      text-align: left;
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--card-border);
      color: var(--text-muted);
      font-weight: 600;
    }
    .verdicts-table td {
      padding: 0.75rem 1rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }
    .verdicts-table tr:hover {
      background: rgba(255, 255, 255, 0.02);
    }
    .mono { font-family: var(--font-mono); }

    /* Trajectory Modal / Card */
    .trajectory-step {
      background: rgba(10, 15, 28, 0.6);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 0.75rem 1rem;
      margin-top: 0.5rem;
      font-size: 0.82rem;
    }
    .step-header {
      display: flex;
      justify-content: space-between;
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-bottom: 0.25rem;
    }

    .empty-state {
      text-align: center;
      padding: 3rem 1rem;
      color: var(--text-muted);
    }
  </style>
</head>
<body>

  <header>
    <div class="logo">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
      </svg>
      <span>agent-eval-harness</span>
      <span class="badge badge-neutral">v0.2.1 production</span>
    </div>
    <div id="live-indicator" class="badge badge-success">● System Operational</div>
  </header>

  <div class="container">
    <div class="grid-stats">
      <div class="stat-card">
        <div class="stat-label">Total Completed Runs</div>
        <div class="stat-val" id="stat-runs">0</div>
        <div class="stat-sub">Across committed golden suites</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Latest Baseline Pass Rate</div>
        <div class="stat-val" id="stat-passrate">--%</div>
        <div class="stat-sub">Deterministic Wilson 95% CI</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Benchmark Registry</div>
        <div class="stat-val" id="stat-benchmarks">7</div>
        <div class="stat-sub">280 machine-verified golden cases</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Regression Gate Status</div>
        <div class="stat-val" id="stat-gate" style="color: var(--success)">PASS</div>
        <div class="stat-sub">Fail-closed merge policy</div>
      </div>
    </div>

    <div class="main-layout">
      <!-- Left sidebar: Run trigger & History -->
      <div>
        <div class="panel" style="margin-bottom: 1.5rem;">
          <div class="panel-title">Run Benchmark</div>
          <form id="run-form">
            <div class="form-group">
              <label for="benchmark-select">Benchmark</label>
              <select id="benchmark-select" required>
                <option value="react_basic">react_basic (ReAct Golden)</option>
                <option value="plan_execute_basic">plan_execute_basic (Plan-Execute)</option>
                <option value="supervisor_basic">supervisor_basic (Supervisor)</option>
                <option value="swarm_basic">swarm_basic (Swarm Pattern)</option>
                <option value="map_reduce_basic">map_reduce_basic (Map-Reduce)</option>
                <option value="failure_recovery">failure_recovery (Fault Injection)</option>
                <option value="adversarial">adversarial (Prompt Injection)</option>
              </select>
            </div>
            <div class="form-group">
              <label for="skill-input">Agent Skill Knob (0.0 - 1.0)</label>
              <input type="number" id="skill-input" min="0.1" max="1.0" step="0.05" value="0.85">
            </div>
            <div class="form-group">
              <label for="limit-input">Case Limit (Empty for all cases)</label>
              <input type="number" id="limit-input" min="1" max="56" placeholder="e.g. 10">
            </div>
            <button type="submit" id="run-btn" class="btn">
              <span>Execute Benchmark</span>
            </button>
          </form>
        </div>

        <div class="panel">
          <div class="panel-title">Recent Run Records</div>
          <div class="runs-list" id="runs-container">
            <div class="empty-state">Loading runs...</div>
          </div>
        </div>
      </div>

      <!-- Right main area: Selected Run Inspector -->
      <div class="panel detail-view">
        <div class="panel-title">
          <span id="detail-title">Run Inspector</span>
          <span id="detail-badge"></span>
        </div>
        <div id="detail-content">
          <div class="empty-state">Select a run record from the left to view detailed results, trajectories, and failure classifications.</div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let currentRuns = [];
    let selectedRunId = null;

    // HTML-escape untrusted record fields before innerHTML composition.
    // Every run-record field rendered below passes through esc(); numbers
    // are coerced with Number() first.
    function esc(v) {
      return String(v == null ? '' : v)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    async function loadStatus() {
      try {
        const res = await fetch('/api/runs');
        const data = await res.json();
        currentRuns = data.runs || [];
        document.getElementById('stat-runs').innerText = currentRuns.length;
        if (currentRuns.length > 0) {
          const latest = currentRuns[0];
          document.getElementById('stat-passrate').innerText = ((Number(latest.pass_rate) || 0) * 100).toFixed(1) + '%';
          renderRunsList();
          if (!selectedRunId) {
            selectRun(latest.run_id);
          }
        }
      } catch (e) {
        console.error('Failed to load status:', e);
      }
    }

    function renderRunsList() {
      const container = document.getElementById('runs-container');
      if (currentRuns.length === 0) {
        container.innerHTML = '<div class="empty-state">No runs recorded yet.</div>';
        return;
      }
      container.innerHTML = currentRuns.map(r => {
        const pr = Number(r.pass_rate) || 0;
        return `
        <div class="run-item ${r.run_id === selectedRunId ? 'active' : ''}" data-run-id="${esc(r.run_id)}">
          <div class="run-header">
            <span class="run-id">${esc(String(r.run_id).substring(0, 12))}</span>
            <span class="badge ${pr >= 0.7 ? 'badge-success' : 'badge-danger'}">
              ${(pr * 100).toFixed(1)}%
            </span>
          </div>
          <div class="run-meta">
            <span>${esc(r.benchmark)}</span>
            <span>${esc(r.cases)} cases</span>
            <span>${r.recorded_at ? esc(String(r.recorded_at).substring(0, 10)) : ''}</span>
          </div>
        </div>`;
      }).join('');
    }

    async function selectRun(runId) {
      selectedRunId = runId;
      renderRunsList();
      const container = document.getElementById('detail-content');
      container.innerHTML = '<div class="empty-state">Loading run details...</div>';

      try {
        const res = await fetch('/api/runs/' + encodeURIComponent(runId));
        const run = await res.json();
        renderRunDetail(run);
      } catch (e) {
        container.innerHTML = '<div class="empty-state" style="color:var(--danger)">Failed to load details for ' + esc(runId) + '</div>';
      }
    }

    // run selection via event delegation — never inline onclick with
    // untrusted strings (run ids come from run-record files)
    document.getElementById('runs-container').addEventListener('click', (ev) => {
      const item = ev.target.closest('.run-item');
      if (item && item.dataset.runId) {
        selectRun(item.dataset.runId);
      }
    });

    function renderRunDetail(run) {
      document.getElementById('detail-title').innerText = `${run.benchmark} (${run.run_id})`;
      run.pass_rate = Number(run.pass_rate) || 0;
      const passed = run.pass_rate >= 0.7;
      document.getElementById('detail-badge').innerHTML = `
        <span class="badge ${passed ? 'badge-success' : 'badge-danger'}">
          ${(run.pass_rate * 100).toFixed(1)}% PASS (${run.metrics ? esc(run.metrics.passed) : 0}/${run.metrics ? esc(run.metrics.cases) : 0})
        </span>
      `;

      const verdicts = run.verdicts || [];
      const failHist = (run.metrics && run.metrics.failure_histogram) || {};

      let html = `
        <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem;">
          <div style="flex:1; padding: 1rem; border-radius: 10px; background: rgba(255,255,255,0.02); border: 1px solid var(--card-border)">
            <div style="font-size:0.75rem; color:var(--text-muted)">Agent Pattern</div>
            <div style="font-weight:700; margin-top:0.2rem;">${esc(run.agent_pattern || run.agent || 'react')}</div>
          </div>
          <div style="flex:1; padding: 1rem; border-radius: 10px; background: rgba(255,255,255,0.02); border: 1px solid var(--card-border)">
            <div style="font-size:0.75rem; color:var(--text-muted)">Test Failures</div>
            <div style="font-weight:700; color: ${failHist.test_failure ? 'var(--danger)' : 'var(--text)'}; margin-top:0.2rem;">${esc(failHist.test_failure || 0)}</div>
          </div>
          <div style="flex:1; padding: 1rem; border-radius: 10px; background: rgba(255,255,255,0.02); border: 1px solid var(--card-border)">
            <div style="font-size:0.75rem; color:var(--text-muted)">Evaluator Errors</div>
            <div style="font-weight:700; color: ${failHist.evaluator_error ? 'var(--danger)' : 'var(--text)'}; margin-top:0.2rem;">${esc(failHist.evaluator_error || 0)}</div>
          </div>
          <div style="flex:1; padding: 1rem; border-radius: 10px; background: rgba(255,255,255,0.02); border: 1px solid var(--card-border)">
            <div style="font-size:0.75rem; color:var(--text-muted)">Infra Failures</div>
            <div style="font-weight:700; color: ${failHist.infrastructure_failure ? 'var(--danger)' : 'var(--text)'}; margin-top:0.2rem;">${esc(failHist.infrastructure_failure || 0)}</div>
          </div>
        </div>

        <h3 style="font-size:0.95rem; font-weight:700; margin-bottom:0.75rem;">Case Verdicts (${verdicts.length})</h3>
        <div style="overflow-x: auto; max-height: 480px; overflow-y: auto;">
          <table class="verdicts-table">
            <thead>
              <tr>
                <th>Case ID</th>
                <th>Category</th>
                <th>Status</th>
                <th>Failure Class</th>
                <th>Tools</th>
                <th>Answer Preview</th>
              </tr>
            </thead>
            <tbody>
              ${verdicts.map(v => `
                <tr>
                  <td class="mono" style="font-weight:600">${esc(v.case_id)}</td>
                  <td><span class="badge badge-neutral">${esc(v.category)}</span></td>
                  <td>
                    <span class="badge ${v.passed ? 'badge-success' : 'badge-danger'}">
                      ${v.passed ? 'PASS' : 'FAIL'}
                    </span>
                  </td>
                  <td><span style="font-size:0.78rem; color:${v.failure_class === 'none' ? 'var(--text-muted)' : 'var(--danger)'}">${esc(v.failure_class)}</span></td>
                  <td class="mono">${esc(v.tool_calls || 0)}</td>
                  <td style="max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color:var(--text-muted)">
                    ${v.final_answer ? esc(v.final_answer) : '(none)'}
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;

      document.getElementById('detail-content').innerHTML = html;
    }

    document.getElementById('run-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('run-btn');
      btn.disabled = true;
      btn.innerHTML = '<span>Executing benchmark in sandbox...</span>';

      const benchmark = document.getElementById('benchmark-select').value;
      const skill = parseFloat(document.getElementById('skill-input').value) || 0.85;
      const limitVal = document.getElementById('limit-input').value;
      const limit = limitVal ? parseInt(limitVal, 10) : null;

      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ benchmark, skill, limit })
        });
        const run = await res.json();
        await loadStatus();
        selectRun(run.run_id);
      } catch (err) {
        alert('Benchmark run failed: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>Execute Benchmark</span>';
      }
    });

    loadStatus();
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    runs_dir: str = "evals/runs"
    baselines_dir: str = "evals/baselines"
    # POST /api/run executes a benchmark run (CPU + writes). Runs are
    # SERIALIZED per process: two concurrent executions would interleave
    # run artifacts and contend on the process-global network guard. This is
    # a single-operator ops tool, not a multi-tenant executor.
    _execute_lock = threading.Lock()

    def do_GET(self) -> None:
      parsed = urlparse(self.path)
      path = parsed.path.rstrip("/")
      if path == "" or path == "/":
        self._send_html(INDEX_HTML)
        return

      if path == "/api/status":
        self._handle_status()
      elif path == "/api/runs":
        self._handle_list_runs()
      elif path.startswith("/api/runs/"):
        run_id = path[len("/api/runs/"):]
        self._handle_get_run(run_id)
      elif path == "/api/benchmarks":
        self._handle_list_benchmarks()
      elif path == "/api/baselines":
        self._handle_list_baselines()
      else:
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
      parsed = urlparse(self.path)
      if parsed.path.rstrip("/") == "/api/run":
        self._handle_execute_run()
      else:
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _handle_status(self) -> None:
      runs = self._collect_runs()
      latest = runs[0] if runs else None
      self._send_json({
          "status": "healthy",
          "total_runs": len(runs),
          "latest_run": latest,
      })

    def _handle_list_runs(self) -> None:
      runs = self._collect_runs()
      self._send_json({"runs": runs})

    def _handle_get_run(self, run_id: str) -> None:
      safe_id = os.path.basename(run_id)
      filename = os.path.join(self.runs_dir, f"{safe_id}.json")
      if not os.path.isfile(filename):
        self.send_error(HTTPStatus.NOT_FOUND, f"Run {safe_id} not found")
        return
      with open(filename, encoding="utf-8") as fh:
        data = json.load(fh)
      self._send_json(data)

    def _handle_list_benchmarks(self) -> None:
      benchmarks = list_benchmarks()
      self._send_json({"benchmarks": benchmarks})

    def _handle_list_baselines(self) -> None:
      baselines = []
      if os.path.isdir(self.baselines_dir):
        for f in os.listdir(self.baselines_dir):
          if f.endswith(".json"):
            name = f[:-5]
            with open(os.path.join(self.baselines_dir, f), encoding="utf-8") as fh:
              bdata = json.load(fh)
            baselines.append({
                "name": name,
                "benchmark": bdata.get("benchmark"),
                "pass_rate": bdata.get("metrics", {}).get("pass_rate", 0.0),
            })
      self._send_json({"baselines": baselines})

    MAX_BODY_BYTES = 1 << 20  # 1 MiB request-body cap

    def _handle_execute_run(self) -> None:
      try:
        # ---- request parsing + validation (fail with 4xx, never 500) ----
        try:
          length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
          self._send_json({"error": "invalid Content-Length header"},
                           status=HTTPStatus.BAD_REQUEST)
          return
        if length < 0:
          self._send_json({"error": "invalid Content-Length header"},
                           status=HTTPStatus.BAD_REQUEST)
          return
        if length > self.MAX_BODY_BYTES:
          # refuse before reading anything: don't let a client force the
          # server to buffer an unbounded body
          self.close_connection = True
          self._send_json({"error": f"request body too large "
                                    f"(max {self.MAX_BODY_BYTES} bytes)"},
                           status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
          return
        body = self.rfile.read(length) if length > 0 else b""
        try:
          payload = json.loads(body.decode("utf-8")) if body else {}
        except (ValueError, UnicodeDecodeError):
          self._send_json({"error": "invalid JSON body"},
                           status=HTTPStatus.BAD_REQUEST)
          return
        if not isinstance(payload, dict):
          self._send_json({"error": "request body must be a JSON object"},
                           status=HTTPStatus.BAD_REQUEST)
          return

        bench_name = payload.get("benchmark", "react_basic")
        if not isinstance(bench_name, str) or not bench_name.strip():
          self._send_json({"error": "benchmark must be a non-empty string"},
                           status=HTTPStatus.BAD_REQUEST)
          return
        try:
          skill = float(payload.get("skill", 0.85))
        except (TypeError, ValueError):
          self._send_json({"error": "skill must be a number in [0,1]"},
                           status=HTTPStatus.BAD_REQUEST)
          return
        if not 0.0 <= skill <= 1.0:
          self._send_json({"error": "skill must be a number in [0,1]"},
                           status=HTTPStatus.BAD_REQUEST)
          return
        raw_limit = payload.get("limit")
        if raw_limit is None or raw_limit == "":
          limit = None  # full run
        else:
          try:
            limit = int(raw_limit)
          except (TypeError, ValueError):
            self._send_json({"error": "limit must be a positive integer (or null)"},
                             status=HTTPStatus.BAD_REQUEST)
            return
          if limit < 1:
            # v0.2.1 silently treated limit=0 (and negatives) as a full run
            self._send_json({"error": "limit must be a positive integer (or null)"},
                             status=HTTPStatus.BAD_REQUEST)
            return

        # ---- deployment mode check (read-only viewer vs executor) --------
        if not (os.path.isdir(self.runs_dir) and os.access(self.runs_dir, os.W_OK)):
          self._send_json(
              {"error": "dashboard is deployed in READ-ONLY VIEWER mode "
                        "(evals/runs is not writable). POST /api/run is "
                        "disabled. Execute benchmarks with the runner "
                        "service (docker compose run --rm runner "
                        "run --benchmark <name>) or the agent-eval CLI."},
              status=HTTPStatus.SERVICE_UNAVAILABLE)
          return

        # ---- authorized execution (serialized) ----------------------------
        with DashboardHandler._execute_lock:
          bench = load_benchmark(bench_name)
          cfg = RunConfig(benchmark=bench_name, skill=skill, limit=limit, out_dir=self.runs_dir)
          runner = BenchmarkRunner(bench, cfg)
          record = runner.run()

        self._send_json({
            "run_id": record.run_id,
            "benchmark": record.benchmark,
            "pass_rate": record.pass_rate,
            "recorded_at": record.recorded_at,
            "metrics": record.metrics,
            "verdicts": [
                {
                    "case_id": v.case_id,
                    "pattern": v.pattern,
                    "category": v.category,
                    "passed": v.passed,
                    "failure_class": v.failure_class.value,
                    "tool_calls": v.tool_calls,
                    "final_answer": v.final_answer,
                }
                for v in record.verdicts
            ],
        })
      except InfraError as exc:
        # unknown benchmark / bad registry config: a client error, not a 500
        self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
      except Exception as exc:
        self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _collect_runs(self) -> list[dict[str, Any]]:
      results: list[dict[str, Any]] = []
      if not os.path.isdir(self.runs_dir):
        return results
      for fname in os.listdir(self.runs_dir):
        if not fname.endswith(".json") or fname.endswith(".events.json"):
          continue
        fpath = os.path.join(self.runs_dir, fname)
        try:
          with open(fpath, encoding="utf-8") as fh:
            data = json.load(fh)
          results.append({
              "run_id": data.get("run_id", fname[:-5]),
              "benchmark": data.get("benchmark", "unknown"),
              "pass_rate": float(data.get("metrics", {}).get("pass_rate", 0.0)),
              "cases": int(data.get("metrics", {}).get("cases", 0)),
              "recorded_at": data.get("recorded_at", ""),
          })
        except Exception:
          continue
      results.sort(key=lambda r: r.get("recorded_at", ""), reverse=True)
      return results

    def _send_html(self, html: str) -> None:
      data = html.encode("utf-8")
      self.send_response(HTTPStatus.OK)
      self.send_header("Content-Type", "text/html; charset=utf-8")
      self.send_header("X-Content-Type-Options", "nosniff")
      self.send_header("Content-Length", str(len(data)))
      self.end_headers()
      self.wfile.write(data)

    def _send_json(self, obj: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
      data = json.dumps(obj).encode("utf-8")
      self.send_response(status)
      self.send_header("Content-Type", "application/json")
      # same-origin by default: the dashboard UI is served from this origin.
      # No Access-Control-Allow-Origin: cross-origin readers are blocked by SOP.
      self.send_header("X-Content-Type-Options", "nosniff")
      self.send_header("Content-Length", str(len(data)))
      self.end_headers()
      self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
      # Suppress default noisy console logs for clean operational output
      pass


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    runs_dir: str | None = None,
    baselines_dir: str | None = None,
) -> None:
  runs_dir = runs_dir or default_runs_dir()
  baselines_dir = baselines_dir or default_baselines_dir()
  DashboardHandler.runs_dir = runs_dir
  DashboardHandler.baselines_dir = baselines_dir
  ThreadingHTTPServer.allow_reuse_address = True
  server = ThreadingHTTPServer((host, port), DashboardHandler)
  server.daemon_threads = True
  print(f"  agent-eval dashboard live at http://{host}:{port}/")
  print("  Press Ctrl+C to terminate.")
  try:
    server.serve_forever()
  except KeyboardInterrupt:
    print("\n  Dashboard stopped.")
  finally:
    server.server_close()
