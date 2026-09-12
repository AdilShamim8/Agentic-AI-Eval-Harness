"""Model backend protocol + ScriptedModel deterministic policy backend.

The ScriptedModel is a *policy simulation* of an LLM: it reads the task, derives
an internal action plan ("understanding"), and emits decisions turn by turn
while REAL tools execute for real and REAL observations come back. Its quality
knobs (skill, fault profile, seeded RNG) produce controlled, reproducible
agent-quality variation for ablations, regression demos, and calibration.

Honesty contract: every run using this backend labels itself
`model_backend=scripted-policy-v1 (deterministic simulation)`. Live-LLM
backends implement the same protocol; their measurements are reported
separately (or "Not measured yet").
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from agent_eval_harness.agents import tools as toolmod

# ---------------------------------------------------------------------------
# Decisions (what a model emits each turn)
# ---------------------------------------------------------------------------


@dataclass
class Think:
    content: str


@dataclass
class Plan:
    steps: list[str]


@dataclass
class ToolCallDecision:
    name: str
    args: dict[str, Any]


@dataclass
class Handoff:
    target: str
    payload: str = ""


@dataclass
class FinalAnswer:
    text: str


@dataclass
class Malformed:
    raw: str


ModelDecision = Think | Plan | ToolCallDecision | Handoff | FinalAnswer | Malformed

MODEL_BACKEND_VERSION = "scripted-policy-v1"


# ---------------------------------------------------------------------------
# Understanding — the model's (possibly imperfect) reading of the task
# ---------------------------------------------------------------------------


@dataclass
class Action:
    kind: str  # tool|final|assume
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    note: str = ""


@dataclass
class TaskUnderstanding:
    actions: list[Action] = field(default_factory=list)
    compose: str = "last"  # last|all
    items: list[str] = field(default_factory=list)  # map-reduce items
    aggregate_op: str = ""  # map-reduce reduce op
    clause: str = ""  # map-reduce per-item clause
    concept: str = ""  # map-reduce numeric concept (population/battery/...)
    description: str = ""


# Concept -> extraction pattern for map-reduce numeric extraction. Shared by
# the map-reduce agent AND the dataset generator so gold values are computed
# through the exact same observable pipeline the agent uses.
CONCEPT_PATTERNS: dict[str, str] = {
    "population": r"population of ([\d,]+)",
    "founded": r"founded in (\d{4})",
    "rainfall": r"rainfall of (\d+)",
    "battery": r"(\d+) Wh",
    "warranty": r"warranty of (\d+) months",
    "screen": r"(\d+(?:\.\d+)?) inch",
}


_CORPUS_ALIASES = {
    "employee_handbook": "employee_handbook",
    "employee handbook": "employee_handbook",
    "product_specs": "product_specs",
    "product specs": "product_specs",
    "city_data": "city_data",
    "city data": "city_data",
    "science_facts": "science_facts",
    "science facts": "science_facts",
}

_NUM_RE = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)")


def _find_corpus(text: str) -> str:
    low = text.lower()
    for alias in sorted(_CORPUS_ALIASES, key=len, reverse=True):
        if alias in low:
            return _CORPUS_ALIASES[alias]
    return "employee_handbook"


def _expression_from(text: str) -> str:
    """Extract the arithmetic expression substring from task text."""
    best = ""
    for m in re.finditer(r"[0-9][0-9+\-*/%.() \t]*[0-9)]", text):
        cand = m.group(0).strip()
        if any(op in cand for op in "+-*/%") and len(cand) > len(best):
            best = cand
    return best


def _understand_core(task: str, context: dict[str, Any] | None = None) -> TaskUnderstanding:
    """Parse a benchmark task into the canonical action list.

    Dataset tasks are written from the template families recognized here; the
    integration test `test_understanding_covers_dataset` asserts full coverage.
    """
    t = task.strip()
    low = t.lower()
    ctx = context or {}
    u = TaskUnderstanding(description=t[:80])

    # --- map-reduce family -----------------------------------------------
    m = re.search(r"[Ff]or each of \{([^}]+)\}[, ]*(.+?), then (?:compute|report) "
                  r"the (sum|total|mean|average|max|maximum|min|minimum|median|count)",
                  t)
    if m:
        items = [i.strip() for i in m.group(1).split(",") if i.strip()]
        clause, agg = m.group(2).strip().rstrip("."), m.group(3).lower()
        agg_op = {"total": "sum", "average": "mean", "maximum": "max",
                  "minimum": "min"}.get(agg, agg)
        u.clause = clause
        u.items = items
        u.aggregate_op = agg_op
        u.compose = "last"
        concept_m = re.search(r"(population|founded|rainfall|battery|warranty|screen)", clause)
        if re.search(r"compute (?:the )?(?:value|result)", clause):
            for item in items:
                u.actions.append(Action("tool", "calculator", {"expression": item}))
            return u
        if concept_m:
            u.concept = concept_m.group(1)
            corpus = _find_corpus(clause)
            for item in items:
                u.actions.append(Action(
                    "tool", "knowledge_search",
                    {"query": f"{item} {u.concept}", "corpus": corpus}))
            return u
        corpus = _find_corpus(clause)
        for item in items:
            u.actions.append(Action("tool", "knowledge_search",
                                    {"query": f"{item} {clause}", "corpus": corpus}))
        return u

    # --- compound request families (supervisor / swarm phrasing) -----------
    m = re.search(r"[Hh]andle this request:\s*(.+)$", t, re.S)
    if m:
        body = m.group(1)
        body = re.sub(r",?\s*Combine (?:both|all) results.*$", "", body,
                      flags=re.I).strip(" ;.")
        parts = re.split(r";\s*and\s+|;\s*", body)
        actions = [a for p in parts if (a := _single_action(p.strip(" .")))]
        if len(actions) >= 2:
            u.actions = actions
            u.compose = "all"
            return u
        if actions:
            u.actions = actions
            u.compose = "last"
            return u

    m = re.search(r"[Rr]oute this through the team:\s*(.+)$", t, re.S)
    if m:
        body = m.group(1)
        body = re.sub(r",?\s*then report\b.*$", "", body, flags=re.I).strip(" .")
        parts = re.split(r",\s*then\s+|;\s*", body)
        actions = [a for p in parts if (a := _single_action(p.strip(" .")))]
        if len(actions) >= 2:
            u.actions = actions
            u.compose = "all"
            return u
        if actions:
            u.actions = actions
            u.compose = "last"
            return u

    # --- multi-step (First ... Then ... Finally ...) ----------------------
    if re.search(r"\bFirst\b", t) and re.search(r"\bThen\b|\bFinally\b", t):
        parts = re.split(r"\b(?:First|Then|Finally|Next)\b", t)[1:]
        actions: list[Action] = []
        for part in parts:
            sub = _single_action(part.strip().rstrip("."))
            if sub:
                actions.append(sub)
        if actions:
            u.actions = actions
            u.compose = "all" if len(actions) > 1 else "last"
            return u

    # --- single + follow-up store family ----------------------------------
    m = re.search(r"[Ss]ave the value (.+?) under the key ['\"]([\w.\-]+)['\"]", t)
    if m:
        value_raw = m.group(1).strip()
        value: Any = value_raw
        try:
            value = int(value_raw)
        except ValueError:
            try:
                value = float(value_raw)
            except ValueError:
                value = value_raw
        u.actions.append(Action("tool", "store_set", {"key": m.group(2), "value": value}))
        m2 = re.search(r"[Rr]ead back the key ['\"]([\w.\-]+)['\"]", t)
        if m2:
            u.actions.append(Action("tool", "store_get", {"key": m2.group(1)}))
        u.compose = "last"
        return u

    # --- fetch (simulated web) --------------------------------------------
    m = re.search(r"(?:[Ff]etch|[Rr]etrieve) (fixture://\S+)", t)
    if m:
        url = m.group(1).rstrip(".")
        u.actions.append(Action("tool", "sim_web_get", {"url": url}))
        u.compose = "last"
        return u

    # --- single-action families --------------------------------------------
    single = _single_action(t)
    if single:
        u.actions = [single]
        u.compose = "last"
        if low.startswith("assume"):
            u.actions.insert(0, Action("assume"))
        return u

    return u  # empty understanding -> agent will fail gracefully


def understand_task(task: str, context: dict[str, Any] | None = None) -> TaskUnderstanding:
    """Public parser: handles the assumption marker, then delegates to core.

    Tasks containing 'assume the intended meaning' must produce an explicit
    assumption step before their real actions (ambiguous-case contract).
    """
    low = task.lower()
    if "assume the intended meaning" in low:
        stripped = re.sub(r"\s*[Aa]ssume the intended meaning and answer\.?\s*", " ", task)
        stripped = re.sub(r"\s{2,}", " ", stripped).strip()
        u = _understand_core(stripped, context)
        if u.actions and u.actions[0].kind != "assume":
            u.actions.insert(0, Action("assume"))
        return u
    return _understand_core(task, context)


def _single_action(text: str) -> Action | None:
    low = text.lower()
    # store read-back (supervisor/plan subtask phrasing)
    m = re.search(r"[Rr]ead back the key ['\"]([\w.\-]+)['\"]", text)
    if m:
        return Action("tool", "store_get", {"key": m.group(1)})
    # fetch (subtask phrasing)
    m = re.search(r"(?:[Ff]etch|[Rr]etrieve) (fixture://\S+)", text)
    if m:
        return Action("tool", "sim_web_get", {"url": m.group(1).rstrip(".")})
    # store save (subtask phrasing)
    m = re.search(r"[Ss]ave the value (.+?) under the key ['\"]([\w.\-]+)['\"]", text)
    if m:
        raw = m.group(1).strip()
        try:
            value: Any = int(raw)
        except ValueError:
            try:
                value = float(raw)
            except ValueError:
                value = raw
        return Action("tool", "store_set", {"key": m.group(2), "value": value})
    # word count (subtask phrasing variant)
    m = re.search(r"[Cc]ount the words in the text[:\s]+(.+)$", text, re.S)
    if m:
        return Action("tool", "text_stats", {"text": m.group(1).strip()})
    # calculator
    expr = _expression_from(text)
    if expr and re.search(r"\b(?:compute|calculate|evaluate|what is)\b", low):
        return Action("tool", "calculator", {"expression": expr})
    # knowledge search: "... what is X? Search the <corpus> corpus."
    m = re.search(r"[Ww]hat is (.+?)\? (?:Search|Consult) the [\w ]+ corpus\.?", text)
    if m:
        return Action("tool", "knowledge_search",
                      {"query": m.group(1).strip(), "corpus": _find_corpus(text)})
    m = re.search(r"[Ww]hat is (.+?)[?.] (?:Search|Consult) the ([\w ]+)[.]?", text)
    if m:
        corpus = _CORPUS_ALIASES.get(m.group(2).strip().lower(), "employee_handbook")
        return Action("tool", "knowledge_search",
                      {"query": m.group(1).strip(), "corpus": corpus})
    if re.search(r"(?:look up|find|search for|retrieve) .+ (?:in|from) the [\w ]+ (?:corpus|handbook|specs|facts|data)", low):
        m = re.search(r"(?:look up|find|search for|retrieve) (.+?) (?:in|from) the ([\w ]+?)(?: corpus)?[.?]?\s*$", text)
        if m:
            corpus = _CORPUS_ALIASES.get(m.group(2).strip().lower(), _find_corpus(text))
            return Action("tool", "knowledge_search",
                          {"query": m.group(1).strip(), "corpus": corpus})
    # text transform
    m = re.search(r"[Aa]pply (uppercase|lowercase|reverse|word_count|title case) to the text[:\s]+(.+)$",
                  text, re.S)
    if m:
        op = m.group(1).lower().replace("case", "")
        op = {"upper": "upper", "lower": "lower", "reverse": "reverse",
              "word_count": "word_count", "title": "title"}.get(op, op)
        return Action("tool", "text_transform", {"text": m.group(2).strip(), "op": op})
    # text stats
    m = re.search(r"[Hh]ow many (words|characters|sentences) are in the following text[:\s]+(.+)$",
                  text, re.S)
    if m:
        return Action("tool", "text_stats", {"text": m.group(2).strip()})
    # summarize
    m = re.search(r"[Ss]ummarize the following text in (\d+) sentences?[:\s]+(.+)$", text, re.S)
    if m:
        return Action("tool", "summarize",
                      {"text": m.group(2).strip(), "max_sentences": int(m.group(1))})
    # data calc
    m = re.search(r"[Cc]ompute the (sum|mean|average|median|max|maximum|min|minimum|range|count)"
                  r" of (?:the )?(?:numbers )?\[([^\]]+)\]", text)
    if m:
        op = m.group(1).lower()
        op = {"average": "mean", "maximum": "max", "minimum": "min"}.get(op, op)
        vals = [float(v) if "." in v else int(v)
                for v in re.findall(r"-?\d+\.?\d*", m.group(2))]
        return Action("tool", "data_calc", {"values": vals, "op": op})
    m = re.search(r"[Ww]hat is the (sum|mean|average|median|max|maximum|min|minimum|range|count)"
                  r" of (?:the )?(?:numbers )?\[([^\]]+)\]", text)
    if m:
        op = m.group(1).lower()
        op = {"average": "mean", "maximum": "max", "minimum": "min"}.get(op, op)
        vals = [float(v) if "." in v else int(v)
                for v in re.findall(r"-?\d+\.?\d*", m.group(2))]
        return Action("tool", "data_calc", {"values": vals, "op": op})
    return None


# ---------------------------------------------------------------------------
# Model state
# ---------------------------------------------------------------------------


@dataclass
class ModelState:
    task: str
    context: dict[str, Any] = field(default_factory=dict)
    phase: str = "act"  # plan|act
    pending: list[Action] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)  # observations
    step_index: int = 0
    assigned: str = ""  # e.g. "worker:calc" for supervisor/swarm
    scratchpad: dict[str, Any] = field(default_factory=dict)
    compose_mode: str = "last"


class ModelBackend(Protocol):
    version: str

    def begin_case(self, case_id: str, seed: int) -> None: ...

    def understand(self, task: str, context: dict[str, Any]) -> TaskUnderstanding: ...

    def decide(self, state: ModelState) -> ModelDecision: ...


# ---------------------------------------------------------------------------
# ScriptedModel — deterministic policy backend
# ---------------------------------------------------------------------------


@dataclass
class ScriptedModelConfig:
    skill: float = 0.85
    redundancy: float = 0.05       # p(duplicate a successful call)
    malformed_rate: float = 0.04   # p(emit malformed decision)
    early_termination: float = 0.02  # p(answer immediately, skipping tools)
    loop_tendency: float = 0.02    # p(stuck repeating identical call)
    recovery: float | None = None  # p(retry after tool error) — default skill
    injection_resistance: float | None = None  # default min(0.99, skill + 0.10)
    seed: int = 0
    version: str = MODEL_BACKEND_VERSION

    def __post_init__(self) -> None:
        if self.recovery is None:
            self.recovery = self.skill
        if self.injection_resistance is None:
            self.injection_resistance = min(0.99, self.skill + 0.10)


def estimate_tokens(text: str) -> int:
    """chars/4 heuristic — labeled `estimate` wherever reported."""
    return max(1, (len(text) + 3) // 4)


class ScriptedModel:
    """Policy model with seeded quality noise. One instance per case."""

    version = MODEL_BACKEND_VERSION

    def __init__(self, config: ScriptedModelConfig | None = None):
        self.config = config or ScriptedModelConfig()
        self._rng = random.Random(self.config.seed)
        self._understanding: TaskUnderstanding | None = None
        self._emitted: list[Action] = []
        self._consecutive_same = 0
        self._last_call: tuple[str, dict] | None = None
        self._last_emitted_action: Action | None = None
        self._case_id = ""

    # -- lifecycle ----------------------------------------------------------
    def begin_case(self, case_id: str, seed: int) -> None:
        self._rng = random.Random(seed)
        self._understanding = None
        self._emitted = []
        self._consecutive_same = 0
        self._last_call = None
        self._last_emitted_action = None
        self._case_id = case_id

    def understand(self, task: str, context: dict[str, Any]) -> TaskUnderstanding:
        if self._understanding is None:
            self._understanding = understand_task(task, context)
        return self._understanding

    # -- decision emission ---------------------------------------------------
    def decide(self, state: ModelState) -> ModelDecision:
        rng = self._rng
        cfg = self.config

        # plan phase: describe the pending actions as plan steps
        if state.phase == "plan":
            steps = [self._describe(a) for a in state.pending]
            if not steps:
                steps = ["Answer the task directly."]
            if rng.random() < cfg.malformed_rate:
                return Malformed("plan: " + " and ".join(steps[:2]))
            return Plan(steps)

        # malformed emission gate
        if rng.random() < cfg.malformed_rate:
            return Malformed(self._degraded_text(state))

        # early termination gate (skill failure: answer without tools)
        if rng.random() < cfg.early_termination and state.history:
            return FinalAnswer(self._compose_answer(state, degrade=True))

        # loop gate: stuck repeating the previous call
        if self._last_call and rng.random() < cfg.loop_tendency:
            name, args = self._last_call
            self._consecutive_same += 1
            if self._consecutive_same <= 4:
                return ToolCallDecision(name, dict(args))

        pending = [a for a in state.pending if a not in self._emitted]
        if not pending:
            return FinalAnswer(self._compose_answer(state))

        # redundancy gate: re-issue an already-successful call (wasteful but
        # realistic agent behavior; context optimization dedups the observation)
        if (state.history and rng.random() < cfg.redundancy
                and self._last_emitted_action is not None):
            a = self._last_emitted_action
            if any(h.get("ok") and h.get("tool") == a.tool for h in state.history):
                return ToolCallDecision(a.tool, dict(a.args))

        action = pending[0]

        if action.kind == "assume":
            self._emitted.append(action)
            return Think(self._assumption_text(state))

        if rng.random() > cfg.skill:  # wrong tool / wrong args / skip
            fault = rng.random()
            if fault < 0.5:
                wrong = self._wrong_tool_for(action)
                if wrong:
                    # NOT marked emitted: the model will re-plan this action
                    # next turn (validation failure makes the agent retry).
                    return ToolCallDecision(wrong, {"query": "irrelevant xyzzy"})
            elif fault < 0.8:
                # NOT marked emitted: mutated-arg failures are re-planned.
                return ToolCallDecision(action.tool, self._mutated_args(action))
            else:
                self._emitted.append(action)  # skipped: model forgot this step
                return Think(f"(skipped step: {self._describe(action)})")

        self._emitted.append(action)
        self._consecutive_same = 0
        self._last_call = (action.tool, dict(action.args))
        self._last_emitted_action = action
        return ToolCallDecision(action.tool, dict(action.args))

    # -- policy hooks used by agents ------------------------------------------
    def policy_retry(self) -> bool:
        """Seeded agent-recovery decision after a tool error observation."""
        return self._rng.random() < (self.config.recovery or 0.0)

    def retry_action(self, action: Action) -> None:
        """Make a previously emitted action pending again (recovery path)."""
        if action in self._emitted:
            self._emitted.remove(action)

    def retry_last_action(self) -> None:
        """Un-emit the most recently emitted action so the model re-plans it
        (used when the emitted call failed for validation-type reasons)."""
        if self._last_emitted_action is not None and self._last_emitted_action in self._emitted:
            self._emitted.remove(self._last_emitted_action)

    def policy_injection_resisted(self) -> bool:
        """Seeded adversarial-injection resistance decision."""
        return self._rng.random() < (self.config.injection_resistance or 0.0)

    # -- helpers --------------------------------------------------------------
    def _describe(self, a: Action) -> str:
        if a.kind == "assume":
            return "State the assumption before answering"
        if a.tool == "knowledge_search":
            return (f"Use knowledge_search on the {a.args.get('corpus')} corpus "
                    f"for '{a.args.get('query')}'")
        return f"Use {a.tool} ({', '.join(f'{k}={v}' for k, v in a.args.items())})"

    def _degraded_text(self, state: ModelState) -> str:
        return f"the answer is probably {self._rng.randint(10, 99)} i guess??"

    def _wrong_tool_for(self, a: Action) -> str:
        distract = {
            "calculator": "text_stats", "knowledge_search": "text_transform",
            "text_stats": "calculator", "text_transform": "summarize",
            "summarize": "text_stats", "data_calc": "calculator",
            "sim_web_get": "knowledge_search", "store_set": "store_get",
            "store_get": "store_set",
        }
        return distract.get(a.tool, "text_stats")

    def _mutated_args(self, a: Action) -> dict[str, Any]:
        args = dict(a.args)
        if "values" in args and isinstance(args["values"], list) and args["values"]:
            # format error: CSV string instead of a list — the harness
            # validation layer can repair this; without it the tool errors.
            return {**args, "values": ", ".join(str(v) for v in args["values"])}
        if "expression" in args:
            expr = str(args["expression"])
            digits = re.findall(r"\d", expr)
            if digits:
                bad = str((int(digits[-1]) + 1) % 10)
                args["expression"] = re.sub(r"(\d)$", bad, expr)
        elif "query" in args:
            q = str(args["query"])
            words = q.split()
            if len(words) > 1:
                words[-1] = words[-1][::-1]
                args["query"] = " ".join(words)
        elif "values" in args and isinstance(args["values"], list) and args["values"]:
            vals = list(args["values"])
            if isinstance(vals[-1], int):
                vals[-1] = vals[-1] + 2
            args["values"] = vals
        elif "url" in args:
            args["url"] = "fixture://unknown/page"
        return args

    def _assumption_text(self, state: ModelState) -> str:
        return "Assuming the question refers to the primary context value."

    def _compose_answer(self, state: ModelState, degrade: bool = False) -> str:
        if degrade:
            return f"Based on my internal estimate: {self._rng.randint(2, 99)}"
        obs = [h for h in state.history if h.get("ok")]
        if not obs:
            return "I could not complete the task."
        parts = [p for p in (observation_text(h) for h in obs) if p]
        assumed = state.scratchpad.get("assumption_stated", False)
        if state.compose_mode == "all":
            text = "; ".join(parts)
        else:
            text = parts[-1] if parts else ""
        if assumed:
            text = "Assuming the intended interpretation: " + (text or "the primary value.")
        return text or "I could not complete the task."


def eval_args(args_json: str) -> dict[str, Any]:
    import json

    try:
        return json.loads(args_json) if isinstance(args_json, str) else dict(args_json)
    except (TypeError, ValueError):
        return {}


def observation_text(obs: dict[str, Any]) -> str:
    """Extract the human-meaningful text of an observation (shared by the
    model's answer composition and the supervisor/swarm agents)."""
    v = obs.get("value")
    if isinstance(v, dict):
        if "note" in v:  # context-optimizer dedup marker
            return ""
        if isinstance(v.get("results"), list) and v["results"]:
            first = v["results"][0]
            return str(first.get("snippet", first))
        for key in ("value", "result", "summary", "snippet", "content"):
            if key in v:
                return str(v[key])
        return str(v)
    return str(v)


def observation_from_tool_result(name: str, res: toolmod.ToolResult) -> dict[str, Any]:
    return {"tool": name, "ok": res.ok, "value": res.value, "error": res.error}
