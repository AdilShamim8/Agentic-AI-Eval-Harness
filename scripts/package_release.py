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
    with open(os.path.join(RELEASE, "evaluators", "README.md"), "w") as fh:
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

        suite = json.load(open(exp))["full_suite"]
        keep_prefixes = [s["run_id"] for s in suite.values()]
    runs_out = os.path.join(RELEASE, "evals", "runs")
    os.makedirs(runs_out, exist_ok=True)
    for fname in os.listdir(os.path.join(REPO, "evals", "runs")):
        rid = fname.split(".")[0]
        if rid in keep_prefixes:
            copy_file(os.path.join(REPO, "evals", "runs", fname),
                      os.path.join(runs_out, fname))
            n += 1
    with open(os.path.join(RELEASE, "evals", "README.md"), "w") as fh:
        fh.write("""# Evaluation evidence

- `baselines/main.json` — the CI regression baseline (react_basic, skill .85)
- `calibration/hand_labels.csv` — 56 hand-labeled judge calibration sample
- `results/experiments.json` — every measured claim in docs/final-report.md
- `runs/` — canonical full-suite run records (+ .events.jsonl event logs);
  all other runs are reproducible via scripts/run_experiments.py
""")
    n += 1

    # infra README
    with open(os.path.join(RELEASE, "infra", "README.md"), "w") as fh:
        fh.write("""# Infra

- `.github/workflows/` — ci.yml (quality matrix), eval-gate.yml (BLOCKING
  evaluation quality gates), security.yml (secret scan, gitleaks, pip-audit,
  injection evaluation)
- The repo Makefile (in source/) mirrors every CI command for pre-push runs.
""")
    n += 1

    # release notes
    notes = """# RELEASE NOTES — v0.2.0 (2026-09-12)

The FDE rebuild: the platform re-landed against the FDE field guide's
portfolio contract (github.com/AdilShamim8/fde-field-guide). Product core
unchanged; engagement, handover, demo, and presentation layers added.

## What's new in v0.2.0

- `make demo` (python scripts/demo.py) — the two-minute demo: healthy run →
  deliberately injected regression (−26.8pp) → GATE FAIL exit 1 → per-case
  diagnosis (15 flips, McNemar p = 6.1e-05, 18/0/0 failure taxonomy).
  Shows the failure path on purpose; layout-aware (runs from repo tree or
  this extracted zip); ~1.4 s.
- `agent-eval status` — operator weekly health view: latest run per
  benchmark vs baseline drift, golden-dataset sha256s, judge κ state;
  exits 1 on regression (cron-friendly).
- Engagement record (docs/fde/): verbatim fictional-composite customer
  brief, discovery notes, requirements spec, and acceptance criteria with
  outcome metrics frozen in writing BEFORE the build, results filled from
  committed artifacts, each with a reproduce command.
- Handover artifacts at the root: RUNBOOK.md (alarm-by-alarm operations,
  sharp edges), INCIDENTS.md (8 real incidents), DECISIONS.md (10 ADRs).
- Portfolio presentation: docs/fde/WRITE-UP.md (the guide's 8-section
  structure), docs/fde/90-SECOND-STORY.md, docs/fde/FDE-SYNTHESIS.md.
- Fixed INC-7 (pytest plugin missing on clean clones — raw tree now tests
  green without install) and INC-8 (deterministic run ids vs demo run
  discovery). Tests 121 → 126. See CHANGELOG.md.

## Highlights (carried from v0.1.0)
- 5 agent patterns (ReAct, Plan-Execute, Supervisor, Swarm, Map-Reduce) on a
  deterministic scripted backend with real tool execution; LangGraph /
  OpenAI Agents SDK / CrewAI adapters (stub-tested; real frameworks not
  measured yet).
- 280 machine-verified golden cases across 6 categories.
- 20 evaluators incl. LLM-as-judge with calibrated deterministic rubric
  backend (Cohen's κ = 1.000 on the 56-case hand-labeled sample after the
  v1.1 fix; the failing v1.0 κ = 0.082 is preserved in docs/final-report.md).
- Harness ablation attribution (retry −12.5pp on weak agents),
  reproducibility (0.0pp same-seed, byte-identical records), regression
  gates with CI exit codes, fail-closed on insufficient data.

## Measured results (deterministic backend)
react 89.3% · swarm 82.1% · supervisor 80.4% · map-reduce 76.8% ·
plan-execute 73.2% (n=56 each, Wilson CIs in docs/final-report.md).
Live-LLM measurements: Not measured yet.

## Known limitations
- Live judge + framework adapters unmeasured in this environment.
- In-process agent execution: run untrusted agent code in a container.
- Cooperative (bounded) timeouts, not preemption.

## Quick verify from this zip

```bash
unzip production-agentic-ai-eval-harness-v0.2.0-fde.zip -d harness && cd harness
python scripts/demo.py      # the whole story in ~90 seconds, no install needed
pip install -e source/.[dev] && make test   # full suite (126 tests)
```
"""
    with open(os.path.join(RELEASE, "RELEASE_NOTES.md"), "w") as fh:
        fh.write(notes)
    n += 1

    # checklist placeholder (filled by validate_release.py)
    with open(os.path.join(RELEASE, "RELEASE_CHECKLIST.md"), "w") as fh:
        fh.write("""# RELEASE CHECKLIST — v0.2.0

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
    with open(os.path.join(RELEASE, "MANIFEST.sha256"), "w") as fh:
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
