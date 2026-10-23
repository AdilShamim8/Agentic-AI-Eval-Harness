"""Environment-aware default paths.

The Dockerfile declares AEH_RUNS_DIR / AEH_BASELINES_DIR; these helpers are
the single source of truth for every runs/baselines default in the platform
(CLI, runner, experiments, dashboard). Container deployments configure
storage locations exclusively through these variables.
"""
from __future__ import annotations

import os


def default_runs_dir() -> str:
    return os.environ.get("AEH_RUNS_DIR", "evals/runs")


def default_baselines_dir() -> str:
    return os.environ.get("AEH_BASELINES_DIR", "evals/baselines")
