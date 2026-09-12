"""LLM-judge (rubric backend) unit tests: scoring semantics + metadata."""
from agent_eval_harness.core.schemas import AgentRunOutcome, Trajectory
from agent_eval_harness.evaluators.llm_judge.judge import (
    RUBRIC_BACKEND_ID,
    RubricJudge,
    build_judge,
    _token_f1,
)


def case(answer=None, **expected):
    exp = {"answer": answer or {}, "max_steps": 12}
    exp.update(expected)
    from agent_eval_harness.core.schemas import TestCase

    return TestCase(id="c", pattern="react", category="normal", task="t",
                    expected=exp)


def outcome(answer="42", plan=None):
    traj = Trajectory()
    traj.plan = plan or []
    return AgentRunOutcome(case_id="c", ok=True, final_answer=answer,
                           trajectory=traj)


def test_token_f1_bounds():
    assert _token_f1("the same text", "the same text") == 1.0
    assert _token_f1("", "") == 1.0
    assert _token_f1("a b", "c d") == 0.0
    assert 0.0 < _token_f1("a b c", "a b d") < 1.0


def test_judge_numeric():
    ev = RubricJudge("answer_correctness")
    c = case({"type": "numeric", "value": 1081})
    assert ev.evaluate(c, outcome("1081")).passed
    # dict-dump answer still conveys the number
    assert ev.evaluate(c, outcome("{'value': 1081}")).passed
    assert not ev.evaluate(c, outcome("999")).passed


def test_judge_contains_verbosity_tolerant():
    ev = RubricJudge("answer_correctness")
    c = case({"type": "contains", "values": ["5 days", "90 days"]})
    verbose = ("The maximum vacation carryover into a new year is 5 days. "
               "Rotate secrets every 90 days.")
    assert ev.evaluate(c, outcome(verbose)).passed
    assert not ev.evaluate(c, outcome("unrelated text")).passed


def test_judge_metadata_records_backend():
    ev = RubricJudge("answer_correctness")
    res = ev.evaluate(case({"type": "numeric", "value": 1}), outcome("1"))
    assert res.meta["backend"] == RUBRIC_BACKEND_ID
    assert res.meta["deterministic"] is True
    assert res.meta["prompt_version"]
    assert 0.0 <= res.score <= 1.0 and 0.0 <= res.meta["confidence"] <= 1.0


def test_judge_instruction_following():
    ev = RubricJudge("instruction_following")
    c = case(instructions=[{"kind": "state_assumption"},
                           {"kind": "max_words", "value": 10}])
    assert ev.evaluate(c, outcome("assuming five words")).passed
    assert not ev.evaluate(c, outcome("a much longer answer that definitely exceeds ten words total")).passed


def test_judge_plan_quality():
    ev = RubricJudge("plan_quality")
    c = case(required_tools=["calculator", "knowledge_search"])
    good = outcome(plan=["Use calculator (x)", "Use knowledge_search (y)"])
    assert ev.evaluate(c, good).passed
    bad = outcome(plan=["Use calculator (x)"])
    assert not ev.evaluate(c, bad).passed


def test_judge_synthesis():
    ev = RubricJudge("synthesis_quality")
    c = case({"type": "contains", "values": ["42", "STATUS"]})
    assert ev.evaluate(c, outcome("the result is 42; STATUS OK")).passed
    res = ev.evaluate(c, outcome("only 42"))
    assert not res.passed and 0.0 < res.score < 1.0


def test_build_judge_default_rubric(monkeypatch):
    monkeypatch.delenv("AEH_JUDGE_BACKEND", raising=False)
    assert isinstance(build_judge("answer_correctness"), RubricJudge)


def test_build_judge_live_falls_back_without_key(monkeypatch):
    monkeypatch.setenv("AEH_JUDGE_BACKEND", "live")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ev = build_judge("answer_correctness")  # LiveJudge without key -> rubric note
    res = ev.evaluate(case({"type": "numeric", "value": 1}), outcome("1"))
    assert "no OPENAI_API_KEY" in res.meta.get("fallback", "")
