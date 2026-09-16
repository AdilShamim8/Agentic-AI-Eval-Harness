"""Benchmark registry: versioned YAML benchmark definitions.

A benchmark defines: name/version/pattern, dataset path, evaluator list,
thresholds (pass gates per evaluator), execution settings (limits, ablation,
permissions), and regression gates. Validated at load time.
"""
from __future__ import annotations

import os

import yaml

from agent_eval_harness.core.errors import InfraError
from agent_eval_harness.evaluators import available_evaluators

DEFAULT_REGISTRY_DIR = "benchmarks"

_REQUIRED_KEYS = ("benchmark", "dataset", "evaluators")


class BenchmarkDef:
    def __init__(self, data: dict, source: str = ""):
        self.data = data
        self.source = source
        issues = self.validate()
        if issues:
            raise InfraError(f"invalid benchmark '{source}': {'; '.join(issues)}")

    # -- accessors ------------------------------------------------------------
    @property
    def name(self) -> str:
        return str(self.data["benchmark"]["name"])

    @property
    def version(self) -> str:
        return str(self.data["benchmark"].get("version", "1.0"))

    @property
    def pattern(self) -> str:
        return str(self.data["benchmark"].get("pattern", ""))

    @property
    def description(self) -> str:
        return str(self.data["benchmark"].get("description", ""))

    @property
    def dataset_path(self) -> str:
        return str(self.data["dataset"]["path"])

    @property
    def evaluators(self) -> list[str]:
        return list(self.data["evaluators"])

    @property
    def thresholds(self) -> dict[str, float]:
        return dict(self.data.get("thresholds", {}))

    @property
    def execution(self) -> dict:
        return dict(self.data.get("execution", {}))

    @property
    def gates(self) -> dict:
        return dict(self.data.get("gates", {}))

    @property
    def agent(self) -> str:
        return str(self.data.get("agent", ""))

    def to_dict(self) -> dict:
        return dict(self.data)

    # -- validation -----------------------------------------------------------
    def validate(self) -> list[str]:
        issues: list[str] = []
        for key in _REQUIRED_KEYS:
            if key not in self.data:
                issues.append(f"missing required key '{key}'")
        if issues:
            return issues
        bench = self.data["benchmark"]
        if not isinstance(bench, dict) or not bench.get("name"):
            issues.append("benchmark.name must be a non-empty string")
        known = set(available_evaluators())
        for ev in self.data["evaluators"]:
            if ev not in known:
                issues.append(f"unknown evaluator '{ev}'")
        for name, thr in self.thresholds.items():
            if name not in known and not name.startswith("overall"):
                issues.append(f"threshold for unknown evaluator '{name}'")
            try:
                if not 0.0 <= float(thr) <= 1.0:
                    issues.append(f"threshold '{name}' out of [0,1]")
            except (TypeError, ValueError):
                issues.append(f"threshold '{name}' not numeric")
        ds = self.data["dataset"]
        if not isinstance(ds, dict) or not ds.get("path"):
            issues.append("dataset.path missing")
        return issues


def load_benchmark(name_or_path: str,
                   registry_dirs: list[str] | None = None) -> BenchmarkDef:
    dirs = registry_dirs or [os.environ.get("AEH_BENCHMARKS_DIR",
                                            DEFAULT_REGISTRY_DIR)]
    candidates: list[str] = []
    if os.path.isfile(name_or_path):
        candidates.append(name_or_path)
    else:
        for d in dirs:
            candidates.append(os.path.join(d, name_or_path))
            if not name_or_path.endswith((".yaml", ".yml", ".json")):
                candidates.append(os.path.join(d, f"{name_or_path}.yaml"))
                candidates.append(os.path.join(d, f"{name_or_path}.json"))
    for path in candidates:
        if os.path.isfile(path):
            if path.endswith(".json"):
                import json

                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            else:
                with open(path, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                raise InfraError(f"benchmark file '{path}' is not a mapping")
            return BenchmarkDef(data, source=path)
    raise InfraError(
        f"benchmark '{name_or_path}' not found (searched: {candidates})")


def list_benchmarks(registry_dir: str | None = None) -> list[dict]:
    d = registry_dir or os.environ.get("AEH_BENCHMARKS_DIR", DEFAULT_REGISTRY_DIR)
    out: list[dict] = []
    if not os.path.isdir(d):
        return out
    for fname in sorted(os.listdir(d)):
        if not fname.endswith((".yaml", ".yml", ".json")):
            continue
        path = os.path.join(d, fname)
        try:
            bm = load_benchmark(path)
            out.append({"name": bm.name, "version": bm.version,
                        "pattern": bm.pattern, "dataset": bm.dataset_path,
                        "source": path, "description": bm.description})
        except InfraError:
            out.append({"name": fname, "version": "?", "pattern": "?",
                        "dataset": "?", "source": path, "description": "INVALID"})
    return out
