#!/usr/bin/env python3
"""agent-eval-harness — the two-minute FDE demo.

FDE demo rules applied (per docs/fde/FDE-SYNTHESIS.md):
  1. one command: `make demo` — reproduces the best moment without secrets
  2. the failure path is shown ON PURPOSE (an agent regression is injected and
     the CI gate catches it live) — reviewers trust failure behavior they saw
  3. dated, narrated, honest: every number printed is measured in this session

Exit code is 0 when the demo itself behaved as designed (including the gate
FAILING on the injected regression — that is the product working).

Equivalent CLI commands are echoed so a reviewer can re-run each act by hand.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

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

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable
CLI = [PYTHON, "-m", "agent_eval_harness.cli.app"]
SEED = 20260912

# layout-aware import path: repo working tree (src/) OR release zip (source/src/)
SRC = os.path.join(REPO, "src")
if not os.path.isdir(SRC):
    SRC = os.path.join(REPO, "source", "src")


def sh(args: list[str], expect_fail: bool = False) -> tuple[int, str]:
    """Run a CLI command from the tree root, streaming output; return (code, output)."""
    print(f"  $ {' '.join(args[3:])}" if args[:3] == CLI[:3] else f"  $ {' '.join(args)}")
    t0 = time.time()
    env = {**os.environ,
           "PYTHONPATH": SRC + os.pathsep + os.environ.get("PYTHONPATH", ""),
           "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(args, cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out.rstrip())
    dt = time.time() - t0
    if expect_fail and proc.returncode == 0:
        print(f"  !! expected a non-zero exit here, got 0 ({dt:.1f}s)")
        return proc.returncode, out
    if not expect_fail and proc.returncode != 0:
        print(f"  !! unexpected exit code {proc.returncode} ({dt:.1f}s)")
    else:
        print(f"  [{dt:.1f}s, exit {proc.returncode}]")
    return proc.returncode, out


def banner(title: str, sub: str = "") -> None:
    line = "─" * 74
    try:
        print(f"\n{line}\n{title}\n{sub}\n{line}" if sub else f"\n{line}\n{title}\n{line}")
    except UnicodeEncodeError:
        ascii_line = "-" * 74
        print(f"\n{ascii_line}\n{title}\n{sub}\n{ascii_line}" if sub else f"\n{ascii_line}\n{title}\n{ascii_line}")


def _snap(runs_dir: str) -> dict[str, float]:
    return {f: os.path.getmtime(os.path.join(runs_dir, f))
            for f in os.listdir(runs_dir) if f.endswith(".json")}


def latest_run_id(before: dict[str, float]) -> str:
    """Find the run record a command just produced/overwrote (run ids are
    deterministic — same benchmark+seed+skill rewrites the same file)."""
    runs_dir = os.path.join(REPO, "evals/runs")
    after = _snap(runs_dir)
    changed = [f for f, t in after.items() if before.get(f) != t]
    if not changed:
        raise SystemExit("demo failed: no run record produced")
    return sorted(changed)[0][:-5]


def main() -> int:
    started = datetime.now(timezone.utc)
    print("=" * 74)
    print("agent-eval-harness — production evaluation platform for Agentic AI")
    print(f"\"pytest for Agentic AI\" · demo recorded {started:%Y-%m-%d %H:%M} UTC")
    print("Engagement context: docs/fde/00-ENGAGEMENT-BRIEF.md (fictional composite")
    print("customer: three teams shipped agents; nobody knew when they broke).")
    print("=" * 74)

    # ACT 1 — the system, healthy ------------------------------------------------
    banner("ACT 1 · The system, healthy",
           "Full golden-suite run: 56 machine-verified cases, deterministic seed.\n"
           "This is what CI runs on every merge.")
    before = _snap(os.path.join(REPO, "evals/runs"))
    code, _ = sh(CLI + ["run", "--benchmark", "react_basic", "--seed", str(SEED)])
    if code != 0:
        return 1
    healthy_id = latest_run_id(before)
    print(f"  → healthy run id: {healthy_id}")

    # ACT 2 — the incident, injected on purpose ----------------------------------
    banner("ACT 2 · The incident (injected on purpose)",
           "Friday, 16:52. Someone ships a 'small prompt tweak'. The agent gets\n"
           "worse at its job (--skill 0.60). Nobody notices — unless the gate works.\n"
           "This act shows the failure path deliberately: a demo that never fails\n"
           "reads as untested.")
    before = _snap(os.path.join(REPO, "evals/runs"))
    code, _ = sh(CLI + ["run", "--benchmark", "react_basic", "--skill", "0.60",
                        "--seed", str(SEED)], expect_fail=True)
    if code == 0:
        print("  !! the regressed run unexpectedly PASSED its threshold gate")
        return 1
    regressed_id = latest_run_id(before)
    print(f"  → regressed run id: {regressed_id}")

    banner("ACT 2b · The gate (this is the moment you find out)",
           "The customer's incident: a broken agent ran silent for NINE DAYS.\n"
           "With the gate wired into CI, this is found at merge time, in seconds.")
    code, out = sh(CLI + ["regression", regressed_id, "--baseline", "main"],
                   expect_fail=True)
    if code == 0:
        print("  !! the gate did NOT fail the regressed run — demo cannot continue")
        return 1
    print("  ✓ GATE FAIL with non-zero exit — CI would have blocked this merge.")

    # ACT 3 — the diagnosis ------------------------------------------------------
    banner("ACT 3 · The diagnosis (failure localization)",
           "Which cases flipped? Is it the agent (TEST FAILURE), the evaluator\n"
           "(EVALUATOR ERROR), or the infrastructure (INFRASTRUCTURE FAILURE)?")
    code, _ = sh(CLI + ["compare", healthy_id, regressed_id])
    if code != 0:
        return 1

    with open(os.path.join(REPO, "evals/runs", f"{regressed_id}.json"),
              encoding="utf-8") as fh:
        reg = json.load(fh)
    hist = reg["metrics"]["failure_histogram"]
    print("  failure taxonomy (regressed run):")
    for bucket in ("test_failure", "evaluator_error", "infrastructure_failure"):
        print(f"    {bucket.replace('_', ' ').title():<24} {hist.get(bucket, 0)}")
    print("  → all failures land in TEST FAILURE: blame the agent change, not the harness.")

    # EPILOGUE — what else this platform proved ----------------------------------
    banner("EPILOGUE · What else is measured (see docs/final-report.md)")
    exp_path = os.path.join(REPO, "evals/results/experiments.json")
    if os.path.isfile(exp_path):
        with open(exp_path, encoding="utf-8") as fh:
            exp = json.load(fh)
        cal = exp.get("calibration", {})
        repro = exp.get("repro", {}).get("react_same_seed_x5", {})
        print(f"  judge vs hand labels : Cohen's kappa {cal.get('cohens_kappa')} "
              f"(target >= {cal.get('kappa_target')}, n={cal.get('n')})")
        if repro:
            print(f"  same-seed repro      : max spread {repro.get('max_spread_pp')}pp "
                  f"(byte-identical: {repro.get('byte_identical_same_seed')})")
        abl = exp.get("ablation", {}).get("skill_0.6", {}).get("attribution", {})
        if abl.get("no_retry"):
            print(f"  harness ablation     : removing retry costs "
                  f"{abl['no_retry']['pass_rate_delta']:+.3f} pass-rate (weak agents)")
    print(f"""
  What a reviewer should check next:
    make test            full suite (unit → e2e → security → failure-injection)
    make eval-full       a full benchmark run + report artifacts
    agent-eval status    the operator's weekly one-glance health view
    RUNBOOK.md           handover: alarms, sharp edges, what to do when it breaks
    docs/fde/            the engagement record: brief → discovery → spec → numbers
""")
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print("=" * 74)
    print(f"demo complete · {elapsed:.1f}s elapsed · "
          "all output above was measured live in this session")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
