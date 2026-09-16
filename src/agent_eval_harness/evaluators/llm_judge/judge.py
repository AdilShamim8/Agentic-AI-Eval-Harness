"""LLM-as-Judge: criterion evaluators with two backends.

Backends:
- `rubric` (default): deterministic offline scoring against gold reference +
  checklist — reproducible, free, CI-safe. THIS is the backend measured in
  this release (calibration vs hand labels, Cohen's kappa).
- `live`: any OpenAI-compatible endpoint via stdlib urllib
  (OPENAI_API_KEY / OPENAI_BASE_URL / JUDGE_MODEL env). Structured JSON
  output, versioned prompts, judge metadata recorded. On request failure it
  falls back to the rubric backend and records the failure in metadata —
  judged cases never silently vanish. Live-backend reliability: Not measured
  yet (no endpoint available in the build environment).

Selection: env AEH_JUDGE_BACKEND=live|rubric, or constructor argument.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

from agent_eval_harness.core.schemas import AgentRunOutcome, EvaluationResult, TestCase
from agent_eval_harness.evaluators.base import _result

RUBRIC_BACKEND_ID = "deterministic-rubric-v1"
RUBRIC_PROMPT_VERSION = "judge_rubric_v1"

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _token_f1(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 1.0 if not ta and not tb else 0.0
    counts: dict[str, int] = {}
    for t in ta:
        counts[t] = counts.get(t, 0) + 1
    hit = 0
    for t in tb:
        if counts.get(t, 0) > 0:
            counts[t] -= 1
            hit += 1
    precision = hit / len(tb)
    recall = hit / len(ta)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _gold_reference(case: TestCase) -> str:
    spec = case.answer_spec
    if spec.get("type") == "contains":
        return "; ".join(str(v) for v in spec.get("values", []))
    if spec.get("value") is not None:
        return str(spec["value"])
    checks = case.expected.get("task_checks", [])
    parts = [str(c.get("value", "")) for c in checks if c.get("kind") == "answer_contains"]
    return "; ".join(p for p in parts if p)


def _last_number(text: str) -> float | None:
    m = re.findall(r"-?\d[\d,]*(?:\.\d+)?", text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m[-1])
    except ValueError:
        return None


def _any_number(text: str) -> float | None:
    """Any number in the text matching the gold counts (dict-dump answers
    like {'words': 15, ...} still convey the answer)."""
    for m in re.findall(r"-?\d[\d,]*(?:\.\d+)?", text.replace(",", "")):
        try:
            return float(m)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Rubric backend
# ---------------------------------------------------------------------------


class RubricJudge:
    """Deterministic fallback judge. Scores per criterion with explicit rubric
    items so every judgment is auditable and bit-reproducible."""

    name = "llm_answer_correctness"
    version = "1.0"
    criterion = "answer_correctness"

    def __init__(self, criterion: str = "answer_correctness"):
        self.criterion = criterion
        self.name = f"llm_{criterion}"

    # -- scoring ------------------------------------------------------------
    def score(self, case: TestCase, outcome: AgentRunOutcome) -> dict[str, Any]:
        answer = (outcome.final_answer or "").strip()
        gold = _gold_reference(case)
        if self.criterion == "answer_correctness":
            spec = case.answer_spec
            if spec.get("type") == "numeric":
                got = _any_number(answer)
                want = _last_number(gold)
                if got is not None and want is not None:
                    ok = abs(got - want) <= float(spec.get("tolerance", 1e-6))
                    s = 1.0 if ok else max(0.0, _token_f1(answer, gold))
                elif answer:
                    s = max(0.0, _token_f1(answer, gold))
                else:
                    s = 0.0
            elif spec.get("type") == "contains":
                # containment semantics: a correct answer CONTAINS the required
                # facts; verbosity is not penalized (calibrated v1.1: the
                # token-F1 variant produced 24/56 false negatives vs human
                # labels, kappa 0.082; see docs/final-report.md).
                values = [str(v) for v in spec.get("values", [])]
                if not values:
                    s = 1.0 if answer else 0.0
                else:
                    low = answer.lower()
                    hits = sum(1 for v in values if v.lower() in low)
                    s = hits / len(values)
            elif spec.get("type") == "exact":
                s = 1.0 if answer == str(spec.get("value", "")) else 0.0
            else:
                s = _token_f1(answer, gold) if gold else (
                    1.0 if answer else 0.0)
            conf = min(1.0, abs(s - 0.5) * 2)  # far from boundary = confident
            return {"score": s, "passed": s >= 0.7,
                    "rationale": f"answer-correctness={s:.2f} "
                                 f"(type={spec.get('type', 'reference')}); "
                                 f"gold='{gold[:60]}'",
                    "confidence": round(conf, 2), "items": [
                        {"item": "answer conveys the reference facts",
                         "score": round(s, 3)}]}
        if self.criterion == "instruction_following":
            instructions = case.expected.get("instructions", [])
            if not instructions:
                return {"score": 1.0 if answer else 0.0, "passed": bool(answer),
                        "rationale": "no explicit instructions on case",
                        "confidence": 0.5, "items": []}
            items = []
            for ins in instructions:
                kind = ins.get("kind", "")
                if kind == "must_contain":
                    ok = str(ins.get("value", "")).lower() in answer.lower()
                elif kind == "must_not_contain":
                    ok = str(ins.get("value", "")).lower() not in answer.lower()
                elif kind == "max_words":
                    ok = len(answer.split()) <= int(ins.get("value", 999))
                elif kind == "state_assumption":
                    ok = "assuming" in answer.lower()
                else:
                    ok = True
                items.append({"item": ins, "ok": ok})
            s = sum(1 for i in items if i["ok"]) / len(items)
            return {"score": s, "passed": s == 1.0,
                    "rationale": f"{sum(1 for i in items if i['ok'])}/{len(items)} "
                                 "instruction items satisfied",
                    "confidence": 0.8, "items": items}
        if self.criterion == "plan_quality":
            plan = outcome.trajectory.plan
            required = case.required_tools
            if not required or not plan:
                s = 0.5 if required else 1.0
                return {"score": s, "passed": s >= 0.7,
                        "rationale": "plan absent or nothing to plan",
                        "confidence": 0.4, "items": []}
            blob = " ".join(plan).lower()
            covered = [t for t in required
                       if t.replace("_", " ") in blob or t in blob]
            s = len(covered) / len(required)
            return {"score": s, "passed": s >= 0.7,
                    "rationale": f"plan covers {len(covered)}/{len(required)} required tools",
                    "confidence": 0.7,
                    "items": [{"tool": t, "covered": t in covered} for t in required]}
        if self.criterion == "synthesis_quality":
            values = case.answer_spec.get("values", [])
            if not values:
                s = _token_f1(answer, gold) if gold else 0.5
                return {"score": s, "passed": s >= 0.6,
                        "rationale": "single-source synthesis overlap",
                        "confidence": 0.5, "items": []}
            items = []
            low = answer.lower()
            for v in values:
                contained = str(v).lower() in low  # containment, calibrated v1.1
                items.append({"part": str(v)[:60], "present": contained})
            s = sum(1 for i in items if i["present"]) / len(items)
            return {"score": s, "passed": s >= 0.6,
                    "rationale": f"mean per-part overlap {s:.2f}",
                    "confidence": 0.6, "items": items}
        return {"score": 0.0, "passed": False,
                "rationale": f"unknown criterion {self.criterion}",
                "confidence": 0.0, "items": []}

    # -- evaluator protocol ---------------------------------------------------
    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        res = self.score(case, outcome)
        return _result(case, self.name, self.version, res["score"], res["passed"],
                       {"rationale": res["rationale"], "items": res["items"]},
                       {"backend": RUBRIC_BACKEND_ID,
                        "model": None,
                        "prompt_version": RUBRIC_PROMPT_VERSION,
                        "confidence": res["confidence"],
                        "deterministic": True})


# ---------------------------------------------------------------------------
# Live backend (OpenAI-compatible), rubric fallback
# ---------------------------------------------------------------------------

PROMPT_FILES = {
    "answer_correctness": "judge_answer_correctness_v1.md",
    "instruction_following": "judge_instruction_following_v1.md",
    "plan_quality": "judge_plan_quality_v1.md",
    "synthesis_quality": "judge_synthesis_quality_v1.md",
}


def _prompt_path(criterion: str) -> str:
    fname = PROMPT_FILES.get(criterion, "judge_answer_correctness_v1.md")
    root = os.environ.get("AEH_PROMPTS_DIR", "prompts")
    return os.path.join(root, fname)


class LiveJudge(RubricJudge):
    """Calls an OpenAI-compatible endpoint with the versioned judge prompt;
    falls back to the deterministic rubric on any failure (recorded)."""

    def __init__(self, criterion: str = "answer_correctness",
                 model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, timeout_s: float = 30.0):
        super().__init__(criterion)
        self.model = model or os.environ.get("JUDGE_MODEL", "gpt-4o-mini")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL",
                                                    "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.timeout_s = timeout_s

    def evaluate(self, case: TestCase, outcome: AgentRunOutcome) -> EvaluationResult:
        rubric = super().evaluate(case, outcome)
        if not self.api_key:
            return self._with_fallback_note(rubric, "no OPENAI_API_KEY configured")
        try:
            t0 = time.perf_counter()
            prompt = self._build_prompt(case, outcome)
            body = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            }
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.api_key}"},
                method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            parsed = json.loads(content)
            latency = round((time.perf_counter() - t0) * 1000, 1)
            score = max(0.0, min(1.0, float(parsed.get("score", 0))))
            passed = bool(parsed.get("passed", score >= 0.7))
            return _result(
                case, self.name, self.version, score, passed,
                {"rationale": str(parsed.get("rationale", ""))[:500],
                 "items": parsed.get("items", [])},
                {"backend": "openai-compatible-live",
                 "model": self.model,
                 "prompt_version": os.path.basename(
                     PROMPT_FILES.get(self.criterion, "?")),
                 "prompt_sha": self._prompt_sha(),
                 "latency_ms": latency,
                 "confidence": parsed.get("confidence"),
                 "fallback": None})
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError,
                OSError) as exc:
            return self._with_fallback_note(rubric, f"live judge failed: {exc}")

    # -- helpers ---------------------------------------------------------------
    def _build_prompt(self, case: TestCase, outcome: AgentRunOutcome) -> str:
        path = _prompt_path(self.criterion)
        try:
            template = open(path, encoding="utf-8").read()
        except OSError:
            template = ("Judge the agent's answer for {criterion}.\nTASK: {task}\n"
                        "REFERENCE: {reference}\nANSWER: {answer}\n"
                        "Respond as JSON: {{score, passed, rationale, confidence}}.")
        tools = ", ".join(outcome.trajectory.tool_names()[:20]) or "(none)"
        return (template
                .replace("{task}", case.task[:2000])
                .replace("{reference}", _gold_reference(case)[:1000])
                .replace("{answer}", (outcome.final_answer or "")[:2000])
                .replace("{trajectory}", tools))

    def _prompt_sha(self) -> str:
        try:
            blob = open(_prompt_path(self.criterion), "rb").read()
            return hashlib.sha256(blob).hexdigest()[:12]
        except OSError:
            return "unknown"

    def _with_fallback_note(self, rubric: EvaluationResult, note: str) -> EvaluationResult:
        meta = dict(rubric.meta)
        meta["fallback"] = note
        meta["backend"] = RUBRIC_BACKEND_ID
        rubric.meta = meta
        return rubric


def build_judge(criterion: str, backend: str | None = None) -> RubricJudge:
    backend = backend or os.environ.get("AEH_JUDGE_BACKEND", "rubric")
    if backend == "live":
        return LiveJudge(criterion)
    return RubricJudge(criterion)
