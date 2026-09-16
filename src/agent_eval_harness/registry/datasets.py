"""Dataset loading + validation (JSONL golden datasets)."""
from __future__ import annotations

import hashlib
import json
import os

from agent_eval_harness.core.schemas import TestCase

VALID_CATEGORIES = {"normal", "difficult", "ambiguous", "edge", "adversarial",
                    "failure_inducing"}
VALID_PATTERNS = {"react", "plan_execute", "supervisor", "swarm", "map_reduce"}


def load_dataset(path: str) -> list[TestCase]:
    cases: list[TestCase] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            d.setdefault("context", {})
            d.setdefault("expected", {})
            d.setdefault("tags", [])
            d.setdefault("seed", 0)
            d.setdefault("injection", False)
            d.setdefault("faults", [])
            cases.append(TestCase(
                id=str(d["id"]), pattern=d["pattern"], category=d["category"],
                task=d["task"], context=d["context"], expected=d["expected"],
                difficulty=int(d.get("difficulty", 1)), tags=list(d["tags"]),
                seed=int(d["seed"]), injection=bool(d["injection"]),
                faults=list(d["faults"]),
            ))
    return cases


def validate_dataset(path: str) -> list[str]:
    """Structural + semantic validation. Returns issue list (empty = valid)."""
    issues: list[str] = []
    if not os.path.isfile(path):
        return [f"dataset file not found: {path}"]
    seen_ids: set[str] = set()
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    except OSError as exc:
        return [f"unreadable dataset: {exc}"]
    if not lines:
        return ["dataset is empty"]
    for lineno, line in enumerate(lines, 1):
        where = f"{os.path.basename(path)}:{lineno}"
        try:
            d = json.loads(line)
        except ValueError as exc:
            issues.append(f"{where}: invalid JSON ({exc})")
            continue
        for key in ("id", "pattern", "category", "task", "expected"):
            if key not in d:
                issues.append(f"{where}: missing key '{key}'")
        if "id" in d:
            if d["id"] in seen_ids:
                issues.append(f"{where}: duplicate id '{d['id']}'")
            seen_ids.add(d["id"])
        if d.get("pattern") not in VALID_PATTERNS:
            issues.append(f"{where}: pattern '{d.get('pattern')}' not in "
                          f"{sorted(VALID_PATTERNS)}")
        if d.get("category") not in VALID_CATEGORIES:
            issues.append(f"{where}: category '{d.get('category')}' not in "
                          f"{sorted(VALID_CATEGORIES)}")
        expected = d.get("expected") or {}
        answer = expected.get("answer")
        if not answer and not expected.get("task_checks"):
            issues.append(f"{where}: no answer spec and no task_checks")
        for fault in d.get("faults") or []:
            if fault.get("tool") not in ("calculator", "knowledge_search",
                                         "text_stats", "text_transform",
                                         "summarize", "data_calc", "store_set",
                                         "store_get", "sim_web_get"):
                issues.append(f"{where}: fault names unknown tool "
                              f"'{fault.get('tool')}'")
            if fault.get("kind") not in ("infra", "soft"):
                issues.append(f"{where}: fault kind must be infra|soft")
    return issues


def dataset_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        data = fh.read().replace(b"\r\n", b"\n")
        h.update(data)
    return h.hexdigest()


def dataset_stats(path: str) -> dict:
    cases = load_dataset(path)
    by_cat: dict[str, int] = {}
    for c in cases:
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
    return {"path": path, "cases": len(cases), "by_category": by_cat,
            "sha256": dataset_sha256(path)[:16]}
