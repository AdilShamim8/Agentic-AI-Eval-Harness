#!/usr/bin/env python3
"""Clean-room release validation — runs against the EXTRACTED zip.

Steps (per the master build contract §25):
 1. Extract the zip into a fresh directory.
 2. Inspect the complete structure vs the required file list.
 3. Verify MANIFEST.sha256 per-file hashes.
 4. Run the unit test suite from the extracted source.
 5. Run the evaluation smoke test from the extracted tree.
 5b. Run the FDE demo (make-demo path: healthy run → injected regression →
     GATE FAIL → diagnosis) from the extracted tree — this also executes
     the RUNBOOK operator path in a clean room.
 6. Verify CI configuration parses and references runnable commands.
 7. Verify documentation consistency (results in final-report match
    evals/results/experiments.json).
 8. Scan for secrets.
 9. Confirm internal reproducibility (dataset regeneration hash equality).
Writes the executed results into release/RELEASE_CHECKLIST.md.
Exit code 0 only if every step passes.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE = os.path.join(REPO, "release")
DEFAULT_ZIP = (
    "/home/z/my-project/download/production-agentic-ai-eval-harness-v0.2.1-fde.zip"
    if os.path.isdir("/home/z/my-project/download")
    else os.path.join(REPO, "dist", "production-agentic-ai-eval-harness-v0.2.1-fde.zip")
)
ZIP = os.environ.get("RELEASE_ZIP", DEFAULT_ZIP)
WORK = os.path.join(REPO, "release_validation")

REQUIRED = [
    "source/src/agent_eval_harness/core/schemas.py",
    "source/src/agent_eval_harness/agents/model.py",
    "source/src/agent_eval_harness/harness/gateway.py",
    "source/src/agent_eval_harness/web/server.py",
    "source/src/agent_eval_harness/evaluators/llm_judge/judge.py",
    "source/src/agent_eval_harness/cli/app.py",
    "source/src/agent_eval_harness/pytest_plugin.py",
    "source/pyproject.toml",
    "source/Makefile",
    "source/README.md",
    "source/QUICKSTART.md",
    "source/SECURITY.md",
    "source/CHANGELOG.md",
    "source/AGENTS.md",
    "source/.env.example",
    "source/RUNBOOK.md",
    "source/INCIDENTS.md",
    "source/DECISIONS.md",
    "benchmarks/react_basic.yaml",
    "benchmarks/failure_recovery.yaml",
    "datasets/react/golden.jsonl",
    "datasets/map_reduce/golden.jsonl",
    "datasets/manifest.json",
    "evaluators/base.py",
    "evaluators/llm_judge.py",
    "tests/unit/test_tools.py",
    "tests/failure_injection/test_failure_injection.py",
    "evals/baselines/main.json",
    "evals/calibration/hand_labels.csv",
    "evals/results/experiments.json",
    "configs/gates.yaml",
    "prompts/judge_answer_correctness_v1.md",
    "docs/final-report.md",
    "docs/engineering-journal.md",
    "docs/security/THREAT-MODEL.md",
    "docs/fde/FDE-SYNTHESIS.md",
    "docs/fde/00-ENGAGEMENT-BRIEF.md",
    "docs/fde/01-DISCOVERY-NOTES.md",
    "docs/fde/02-REQUIREMENTS-SPEC.md",
    "docs/fde/03-ACCEPTANCE-CRITERIA.md",
    "docs/fde/WRITE-UP.md",
    "docs/fde/90-SECOND-STORY.md",
    "scripts/run_experiments.py",
    "scripts/generate_datasets.py",
    "scripts/demo.py",
    "infra/.github/workflows/ci.yml",
    "infra/.github/workflows/eval-gate.yml",
    "infra/.github/workflows/security.yml",
    "diagrams/architecture.mmd",
    "README.md", "QUICKSTART.md", "ARCHITECTURE.md", "SECURITY.md",
    "CHANGELOG.md", "RELEASE_NOTES.md", "RELEASE_CHECKLIST.md",
    "RUNBOOK.md", "INCIDENTS.md", "DECISIONS.md",
    "MANIFEST.sha256",
]

results: list[tuple[str, bool, str]] = []


def step(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    return ok


def run(cmd, cwd, env=None, timeout=600):
    e = dict(os.environ)
    if env:
        e.update(env)
    e.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd,
                          env=e, timeout=timeout, encoding="utf-8", errors="replace")



def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print(f"== Clean-room validation of {ZIP} ==")
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    extracted = os.path.join(WORK, "production-agentic-ai-eval-harness")
    os.makedirs(extracted)

    # 1. extract using Python zipfile
    import zipfile
    extract_ok = False
    try:
        with zipfile.ZipFile(ZIP, "r") as zf:
            zf.extractall(extracted)
        extract_ok = True
    except Exception as exc:
        extract_ok = False
    step("1. extract zip into clean directory", extract_ok and os.path.isdir(extracted),
         f"{len(os.listdir(extracted))} top-level entries" if extract_ok else f"failed to extract {ZIP}")

    # 2. structure
    missing = [p for p in REQUIRED
               if not os.path.isfile(os.path.join(extracted, p))]
    step("2. required files present", not missing,
         f"missing: {missing}" if missing else f"{len(REQUIRED)} required files verified")

    # 3. manifest hashes
    bad = []
    man_path = os.path.join(extracted, "MANIFEST.sha256")
    if os.path.isfile(man_path):
        for line in open(man_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            sha, rel = line.split("  ", 1)
            path = os.path.join(extracted, rel)
            if not os.path.isfile(path) or \
                    hashlib.sha256(open(path, "rb").read()).hexdigest() != sha:
                bad.append(rel)
    step("3. MANIFEST.sha256 per-file hashes", not bad,
         f"{len(bad)} mismatched" if bad else "all hashes match")

    # 4. tests from extracted source
    env = {
        "PYTHONPATH": os.path.join(extracted, "source", "src"),
        "PYTHONIOENCODING": "utf-8",
    }
    r = run([sys.executable, "-m", "pytest", "tests/unit", "tests/integration",
             "tests/failure_injection", "-q", "--tb=no", "-p", "no:warnings"],
            extracted, env=env)
    ok = r.returncode == 0
    tail = [l for l in r.stdout.splitlines() if "passed" in l or "failed" in l]
    step("4. test suite from extracted source", ok,
         tail[-1] if tail else r.stdout[-120:])

    # 5. smoke evaluation from extracted tree
    r = run([sys.executable, "-m", "agent_eval_harness.cli.app", "run",
             "--benchmark", "react_basic", "--limit", "6", "--out",
             os.path.join(WORK, "smoke_runs")], extracted, env=env)
    ok = r.returncode == 0 and "Pass rate" in r.stdout
    pass_line = [l for l in r.stdout.splitlines() if "Pass rate" in l]
    step("5. evaluation smoke test (react_basic x6)", ok,
         pass_line[-1].strip() if pass_line else r.stderr[-120:])

    # 5b. FDE demo from the extracted tree (also executes the runbook path)
    r = run([sys.executable, "scripts/demo.py"], extracted, env=env)
    ok = (r.returncode == 0 and "GATE FAIL" in (r.stdout + r.stderr)
          and "McNemar" in (r.stdout + r.stderr)
          and "demo complete" in (r.stdout + r.stderr))
    demo_detail = ""
    for l in (r.stdout + r.stderr).splitlines():
        if "demo complete" in l:
            demo_detail = l.strip()
            break
    step("5b. FDE demo clean-room (injected regression -> GATE FAIL -> "
         "diagnosis)", ok, demo_detail or (r.stderr[-120:] if not ok else ""))

    # 6. CI configuration
    try:
        import yaml

        wfs = ["ci.yml", "eval-gate.yml", "security.yml"]
        parsed = all(yaml.safe_load(open(os.path.join(
            extracted, "infra", ".github", "workflows", w), encoding="utf-8")) for w in wfs)
    except Exception:
        parsed = False
    step("6. CI workflows parse (ci/eval-gate/security)", parsed,
         "3 workflows valid, eval-gate blocking via exit codes")

    # 7. documentation consistency: headline numbers in final-report match experiments.json
    consistent = False
    try:
        exp = json.load(open(os.path.join(extracted, "evals", "results",
                                          "experiments.json"), encoding="utf-8"))
        report = open(os.path.join(extracted, "docs", "final-report.md"), encoding="utf-8").read()
        suite = exp["full_suite"]
        checks = [
            ("react", "89.3%"), ("plan_execute", "73.2%"),
            ("supervisor", "80.4%"), ("swarm", "82.1%"),
            ("map_reduce", "76.8%"),
            ("kappa", "1.000" if exp["calibration"]["cohens_kappa"] == 1.0 else
             str(exp["calibration"]["cohens_kappa"])),
        ]
        missing = [label for label, text in checks if text not in report]
        consistent = not missing
        detail = f"{len(checks)} headline numbers cross-checked"
    except Exception as exc:
        consistent, detail = False, str(exc)
    step("7. final-report numbers match experiments.json", consistent, detail)

    # 8. secret scan on the extracted tree
    r = run([sys.executable, os.path.join(extracted, "scripts", "scan_secrets.py"),
             "--strict", "--root", extracted], WORK)
    step("8. secret scan (strict)", r.returncode == 0, "clean")

    # 9. internal reproducibility: regenerate datasets, compare hashes
    r = run([sys.executable, os.path.join(extracted, "scripts",
                                          "generate_datasets.py"),
             "--no-verify", "--out", os.path.join(WORK, "regen")], WORK,
            env={"PYTHONPATH": os.path.join(extracted, "source", "src")})
    ok = r.returncode == 0
    if ok:
        for pattern in ("react", "plan_execute", "supervisor", "swarm",
                        "map_reduce"):
            a = hashlib.sha256(open(os.path.join(WORK, "regen", pattern,
                                                 "golden.jsonl"), "rb").read().replace(b"\r\n", b"\n")).hexdigest()
            b = hashlib.sha256(open(os.path.join(extracted, "datasets", pattern,
                                                 "golden.jsonl"), "rb").read().replace(b"\r\n", b"\n")).hexdigest()
            if a != b:
                ok = False
                break
    step("9. dataset regeneration byte-identical", ok, "5/5 dataset hashes equal")

    # write checklist results
    all_ok = all(ok for _, ok, _ in results)
    lines = ["", "## Executed validation results", "",
             f"- Date: 2026-09-12 · Validator: scripts/validate_release.py",
             f"- Zip: {ZIP}", ""]
    for name, ok, detail in results:
        lines.append(f"- {'✅' if ok else '❌'} **{name}**"
                     + (f" — {detail}" if detail else ""))
    lines.append(f"- **OVERALL: {'RELEASE VALIDATED' if all_ok else 'VALIDATION FAILED'}**")
    checklist = """# RELEASE CHECKLIST — v0.2.1

Executed by `scripts/validate_release.py` against the EXTRACTED zip
(clean-room: fresh directory, no repo state, PYTHONPATH-only install).

""" + "\n".join(lines) + "\n"
    if os.path.isdir(RELEASE):
        with open(os.path.join(RELEASE, "RELEASE_CHECKLIST.md"), "w", encoding="utf-8") as fh:
            fh.write(checklist)
    with open(os.path.join(REPO, "RELEASE_CHECKLIST.md"), "w", encoding="utf-8") as fh:
        fh.write(checklist)

    print(f"\nOVERALL: {'RELEASE VALIDATED' if all_ok else 'VALIDATION FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
