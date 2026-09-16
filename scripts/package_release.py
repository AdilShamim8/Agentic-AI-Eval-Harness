#!/usr/bin/env python3
"""Build the release tree + zip for production-agentic-ai-eval-harness.

Structure (per the master build contract):
    release/{source, benchmarks, datasets, evaluators, tests, evals, configs,
             prompts, docs, scripts, infra, diagrams}
    release/{README,QUICKSTART,ARCHITECTURE,SECURITY,CHANGELOG,
             RELEASE_NOTES,RELEASE_CHECKLIST,RUNBOOK,INCIDENTS,DECISIONS}.md
Outputs: release/ tree + a per-file sha256 manifest, then zips to
    /home/z/my-project/download/production-agentic-ai-eval-harness-v0.2.0-fde.zip
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE = os.path.join(REPO, "release")
DEFAULT_ZIP = (
    "/home/z/my-project/download/production-agentic-ai-eval-harness-v0.2.1-fde.zip"
    if os.path.isdir("/home/z/my-project/download")
    else os.path.join(REPO, "dist", "production-agentic-ai-eval-harness-v0.2.1-fde.zip")
)
ZIP_OUT = os.environ.get("RELEASE_ZIP", DEFAULT_ZIP)


def copy_tree(src: str, dst: str, ignore=None) -> int:
    if not os.path.isdir(src):
        return 0
    shutil.copytree(src, dst,
                    ignore=shutil.ignore_patterns(*(ignore or [])))
    return sum(len(files) for _, _, files in os.walk(dst))


def copy_file(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    if os.path.isdir(RELEASE):
        shutil.rmtree(RELEASE)
    os.makedirs(RELEASE)

    n = 0
    # source/ — the platform itself
    n += copy_tree(os.path.join(REPO, "src"), os.path.join(RELEASE, "source", "src"),
                   ignore=["__pycache__", "*.egg-info", "py.typed.bak"])
    for f in ("pyproject.toml", "Makefile", ".env.example", "AGENTS.md",
              "README.md", "QUICKSTART.md", "SECURITY.md", "CHANGELOG.md",
              "RUNBOOK.md", "INCIDENTS.md", "DECISIONS.md",
              "Dockerfile", "docker-compose.yml", ".dockerignore"):
        if os.path.exists(os.path.join(REPO, f)):
            copy_file(os.path.join(REPO, f), os.path.join(RELEASE, "source", f))
            n += 1
    copy_file(os.path.join(REPO, "docs", "ARCHITECTURE.md"),
              os.path.join(RELEASE, "ARCHITECTURE.md"))
    n += 1

    # top-level doc copies required by the contract (+ FDE handover artifacts)
    for f in ("README.md", "QUICKSTART.md", "SECURITY.md", "CHANGELOG.md",
              "RUNBOOK.md", "INCIDENTS.md", "DECISIONS.md",
              "Dockerfile", "docker-compose.yml", ".dockerignore"):
        if os.path.exists(os.path.join(REPO, f)):
            copy_file(os.path.join(REPO, f), os.path.join(RELEASE, f))
            n += 1
    # Makefile at release root so `make demo` works from the extracted zip
    copy_file(os.path.join(REPO, "Makefile"), os.path.join(RELEASE, "Makefile"))
    n += 1

    # content trees
    n += copy_tree(os.path.join(REPO, "benchmarks"), os.path.join(RELEASE, "benchmarks"))
    n += copy_tree(os.path.join(REPO, "datasets"), os.path.join(RELEASE, "datasets"))
    n += copy_tree(os.path.join(REPO, "tests"), os.path.join(RELEASE, "tests"),
                   ignore=["__pycache__"])
    n += copy_tree(os.path.join(REPO, "configs"), os.path.join(RELEASE, "configs"))
    n += copy_tree(os.path.join(REPO, "prompts"), os.path.join(RELEASE, "prompts"))
    n += copy_tree(os.path.join(REPO, "docs"), os.path.join(RELEASE, "docs"),
                   ignore=["__pycache__"])
    n += copy_tree(os.path.join(REPO, "scripts"), os.path.join(RELEASE, "scripts"),
                   ignore=["__pycache__"])
    n += copy_tree(os.path.join(REPO, "diagrams"), os.path.join(RELEASE, "diagrams"))
    n += copy_tree(os.path.join(REPO, ".github"), os.path.join(RELEASE, "infra", ".github"))

    # evaluators/ — the evaluator contract surface for consumers
    os.makedirs(os.path.join(RELEASE, "evaluators"), exist_ok=True)
    copy_file(os.path.join(REPO, "src", "agent_eval_harness", "evaluators", "base.py"),
              os.path.join(RELEASE, "evaluators", "base.py"))
    copy_file(os.path.join(REPO, "src", "agent_eval_harness", "evaluators", "__init__.py"),
              os.path.join(RELEASE, "evaluators", "registry.py"))
    copy_file(os.path.join(REPO, "src", "agent_eval_harness", "evaluators",
                           "deterministic", "outcome.py"),
              os.path.join(RELEASE, "evaluators", "deterministic_outcome.py"))
    copy_file(os.path.join(REPO, "src", "agent_eval_harness", "evaluators",
                           "deterministic", "tools.py"),
              os.path.join(RELEASE, "evaluators", "deterministic_tools.py"))
    copy_file(os.path.join(REPO, "src", "agent_eval_harness", "evaluators",
                           "trajectory", "behavior.py"),
              os.path.join(RELEASE, "evaluators", "trajectory_behavior.py"))
    copy_file(os.path.join(REPO, "src", "agent_eval_harness", "evaluators",
                           "llm_judge", "judge.py"),
              os.path.join(RELEASE, "evaluators", "llm_judge.py"))
    with open(os.path.join(RELEASE, "evaluators", "README.md"), "w", encoding="utf-8") as fh:
        fh.write("""# Evaluators (release copies)

Reference copies of the evaluator contract surface. The canonical source is
`source/src/agent_eval_harness/evaluators/` (importable as
`agent_eval_harness.evaluators`). These copies exist so reviewers can read the
evaluation logic without walking the package tree.

- `base.py` — Evaluator protocol
- `deterministic_outcome.py` / `deterministic_tools.py` — deterministic checks
- `trajectory_behavior.py` — trajectory + behavioral evaluators
- `llm_judge.py` — rubric + live judge backends (versioned prompts in ../prompts/)
- `registry.py` — name -> factory registry (20 evaluators)
""")
    n += 7

    # evals/ — evidence (baselines, calibration, results) + selected runs
    n += copy_tree(os.path.join(REPO, "evals", "baselines"),
                   os.path.join(RELEASE, "evals", "baselines"))
    n += copy_tree(os.path.join(REPO, "evals", "calibration"),
                   os.path.join(RELEASE, "evals", "calibration"))
    n += copy_tree(os.path.join(REPO, "evals", "results"),
                   os.path.join(RELEASE, "evals", "results"))
    # curate: keep the canonical full-suite run records (5 patterns), drop exploratory
    keep_prefixes = []
    exp = os.path.join(REPO, "evals", "results", "experiments.json")
    if os.path.isfile(exp):
        import json

        suite = json.load(open(exp, encoding="utf-8"))["full_suite"]
        keep_prefixes = [s["run_id"] for s in suite.values()]
    runs_out = os.path.join(RELEASE, "evals", "runs")
    os.makedirs(runs_out, exist_ok=True)
    for fname in os.listdir(os.path.join(REPO, "evals", "runs")):
        rid = fname.split(".")[0]
        if rid in keep_prefixes:
            copy_file(os.path.join(REPO, "evals", "runs", fname),
                      os.path.join(runs_out, fname))
            n += 1
    with open(os.path.join(RELEASE, "evals", "README.md"), "w", encoding="utf-8") as fh:
        fh.write("""# Evaluation evidence

- `baselines/main.json` — the CI regression baseline (react_basic, skill .85)
- `calibration/hand_labels.csv` — 56 hand-labeled judge calibration sample
- `results/experiments.json` — every measured claim in docs/final-report.md
- `runs/` — canonical full-suite run records (+ .events.jsonl event logs);
  all other runs are reproducible via scripts/run_experiments.py
""")
    n += 1

    # infra README
    with open(os.path.join(RELEASE, "infra", "README.md"), "w", encoding="utf-8") as fh:
        fh.write("""# Infra

- `.github/workflows/` — ci.yml (quality matrix), eval-gate.yml (BLOCKING
  evaluation quality gates), security.yml (secret scan, gitleaks, pip-audit,
  injection evaluation)
- The repo Makefile (in source/) mirrors every CI command for pre-push runs.
""")
    n += 1

    notes = """# RELEASE NOTES — v0.2.1 (2026-09-16)

Enterprise hardening, Web Dashboard, and cross-platform CI matrix.

## What's new in v0.2.1

- Zero-dependency Web Dashboard (`agent-eval serve --port 8000`) powered by
  Python standard library `http.server`, with interactive pass rate cards,
  cross-run diffs, failure localization, and observable trajectory replay.
- Enterprise containerization: multi-stage `Dockerfile` (python:3.12-slim,
  non-root user `aeh` UID 10001) and `docker-compose.yml` (`runner`, `status`, `dashboard`).
- Cross-platform determinism & encoding fixes: Windows UTF-8 stdout reconfiguration
  (INC-9) and CRLF byte normalization for golden dataset SHA-256 integrity (INC-10).
- Multi-OS GitHub Actions CI matrix: `ubuntu-latest` and `windows-latest` across Python 3.11/3.12.
- 132 tests passing (100% green).

## Quick verify from this zip

```bash
python scripts/demo.py      # the whole story in ~90 seconds, no install needed
pip install -e source/.[dev] && make test   # full suite (132 tests)
agent-eval serve            # open http://127.0.0.1:8000
```
"""
    with open(os.path.join(RELEASE, "RELEASE_NOTES.md"), "w", encoding="utf-8") as fh:
        fh.write(notes)
    n += 1

    # checklist placeholder (filled by validate_release.py)
    with open(os.path.join(RELEASE, "RELEASE_CHECKLIST.md"), "w", encoding="utf-8") as fh:
        fh.write("""# RELEASE CHECKLIST — v0.2.1

Completed by `scripts/validate_release.py` against the extracted zip
(clean-room). See the bottom of this file for the executed results.
""")
    n += 1

    # manifest with per-file sha256
    manifest = {}
    for dirpath, _, files in os.walk(RELEASE):
        for fname in sorted(files):
            path = os.path.join(dirpath, fname)
            rel = os.path.relpath(path, RELEASE)
            manifest[rel] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    with open(os.path.join(RELEASE, "MANIFEST.sha256"), "w", encoding="utf-8") as fh:
        for rel in sorted(manifest):
            fh.write(f"{manifest[rel]}  {rel}\n")

    # zip using Python stdlib zipfile for cross-platform portability
    import zipfile
    os.makedirs(os.path.dirname(ZIP_OUT), exist_ok=True)
    if os.path.exists(ZIP_OUT):
        os.remove(ZIP_OUT)
    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(RELEASE):
            for file in sorted(files):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, RELEASE)
                zf.write(full_path, rel_path)
    size_mb = os.path.getsize(ZIP_OUT) / 1e6
    print(f"release tree: {n} files copied + manifest "
          f"({len(manifest)} hashed)")
    print(f"zip -> {ZIP_OUT} ({size_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
