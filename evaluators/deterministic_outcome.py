"""Deterministic evaluators — outcome checks (no LLM, CI-safe, free).

Reads expectations from case.expected:
- answer: {type: exact|contains|numeric|schema, ...}
- forbidden_content: [...]
- task_checks: [{kind: answer_contains|answer_numeric|answer_regex|answer_min_words, ...}]
"""
from __future__ import annotations

import json
import re
from typing import Any

from agent_eval_harness.core.schemas import AgentRunOutcome, EvaluationResult, TestCase
from agent_eval_harness.evaluators.base import _result

_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _answer_text(outcome: AgentRunOutcome) -> str:
    return (outcome.final_answer or "").strip()


def _to_number(text: str) -> float | None:
    m = _NUM.findall(text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m[-1])
    except ValueError:
        return None


class ExactMatch:
    name, version = "exact_match", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        spec = case.answer_spec
        expected = str(spec.get("value", ""))
        actual = _answer_text(outcome)
        passed = actual == expected
        return _result(case, self.name, self.version, 1.0 if passed else 0.0, passed,
                       {"expected": expected[:200], "actual": actual[:200]},
                       {"deterministic": True})


class ContainsAll:
    name, version = "contains_all", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        values = case.answer_spec.get("values", [])
        if not values:
            return _result(case, self.name, self.version, 1.0, True,
                           {"note": "no required values specified"})
        actual = _answer_text(outcome).lower()
        hits = [v for v in values if str(v).lower() in actual]
        score = len(hits) / len(values)
        return _result(case, self.name, self.version, score, len(hits) == len(values),
                       {"required": values, "found": hits},
                       {"deterministic": True})


class NumericTolerance:
    name, version = "numeric_tolerance", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        spec = case.answer_spec
        expected = spec.get("value")
        tol = float(spec.get("tolerance", 1e-6))
        actual_num = _to_number(_answer_text(outcome))
        if expected is None or actual_num is None:
            return _result(case, self.name, self.version, 0.0, False,
                           {"expected": expected, "actual": _answer_text(outcome)[:200],
                            "reason": "missing numeric answer"})
        diff = abs(actual_num - float(expected))
        passed = diff <= tol
        score = 1.0 if passed else max(0.0, 1.0 - diff / (abs(float(expected)) + 1))
        return _result(case, self.name, self.version, score, passed,
                       {"expected": expected, "actual": actual_num, "diff": round(diff, 9)},
                       {"deterministic": True})


class ForbiddenContent:
    name, version = "forbidden_content", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        forbidden = case.expected.get("forbidden_content", [])
        text = _answer_text(outcome)
        hits = [f for f in forbidden if str(f).lower() in text.lower()]
        return _result(case, self.name, self.version, 1.0 - len(hits) / max(1, len(forbidden)) if forbidden else 1.0,
                       not hits, {"forbidden": forbidden, "hits": hits},
                       {"deterministic": True})


class SchemaValidation:
    """Minimal JSON-schema validator: type, required, properties, enum, items."""

    name, version = "schema_validation", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        schema: dict[str, Any] = case.answer_spec.get("schema", {})
        if not schema:
            return _result(case, self.name, self.version, 1.0, True,
                           {"note": "no schema specified"})
        try:
            data = json.loads(_answer_text(outcome))
        except (ValueError, TypeError):
            return _result(case, self.name, self.version, 0.0, False,
                           {"reason": "final answer is not valid JSON"})
        errors = _validate(data, schema, "$")
        passed = not errors
        return _result(case, self.name, self.version, 1.0 if passed else 0.0, passed,
                       {"errors": errors[:10]}, {"deterministic": True})


def _validate(data: Any, schema: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    t = schema.get("type")
    type_ok = {
        "object": isinstance(data, dict), "array": isinstance(data, list),
        "string": isinstance(data, str), "number": isinstance(data, (int, float))
        and not isinstance(data, bool),
        "integer": isinstance(data, int) and not isinstance(data, bool),
        "boolean": isinstance(data, bool),
    }
    if t and not type_ok.get(t, True):
        errors.append(f"{path}: expected {t}, got {type(data).__name__}")
        return errors
    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: {data!r} not in enum {schema['enum']}")
    if isinstance(data, dict):
        for req in schema.get("required", []):
            if req not in data:
                errors.append(f"{path}: missing required '{req}'")
        for key, sub in (schema.get("properties") or {}).items():
            if key in data:
                errors.extend(_validate(data[key], sub, f"{path}.{key}"))
    if isinstance(data, list) and "items" in schema:
        for i, item in enumerate(data):
            errors.extend(_validate(item, schema["items"], f"{path}[{i}]"))
    return errors


class TaskChecks:
    """Per-case deterministic task checks composed by the dataset author."""

    name, version = "task_checks", "1.0"

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        checks = case.expected.get("task_checks", [])
        if not checks:
            return _result(case, self.name, self.version, 1.0, True,
                           {"note": "no task_checks specified"})
        text = _answer_text(outcome)
        results: list[dict[str, Any]] = []
        ok_count = 0
        for chk in checks:
            kind = chk.get("kind", "")
            if kind == "answer_contains":
                ok = str(chk.get("value", "")).lower() in text.lower()
            elif kind == "answer_numeric":
                num = _to_number(text)
                ok = num is not None and abs(num - float(chk.get("value", 0))) <= float(
                    chk.get("tolerance", 1e-6))
            elif kind == "answer_regex":
                ok = re.search(str(chk.get("pattern", "")), text) is not None
            elif kind == "answer_min_words":
                ok = len(text.split()) >= int(chk.get("value", 1))
            elif kind == "assumption_stated":
                ok = "assuming" in text.lower()
            else:
                ok = False
            results.append({"kind": kind, "ok": ok})
            ok_count += int(ok)
        score = ok_count / len(checks)
        return _result(case, self.name, self.version, score, ok_count == len(checks),
                       {"checks": results}, {"deterministic": True})
