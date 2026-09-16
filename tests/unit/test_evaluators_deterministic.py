"""Deterministic evaluator unit tests (table-driven)."""
from agent_eval_harness.core.schemas import AgentRunOutcome, Trajectory
from agent_eval_harness.evaluators.deterministic.outcome import (
    ContainsAll,
    ExactMatch,
    ForbiddenContent,
    NumericTolerance,
    SchemaValidation,
    TaskChecks,
)
from agent_eval_harness.evaluators.deterministic.tools import (
    StepLimit,
    Termination,
    ToolArguments,
    ToolSelection,
)
from agent_eval_harness.core.schemas import TestCase


def case(answer=None, **expected):
    exp = {"answer": answer or {}, "max_steps": 12}
    exp.update(expected)
    return TestCase(id="c", pattern="react", category="normal", task="t",
                    expected=exp)


def outcome(answer="42", tools=None, termination="answer", steps=None):
    traj = Trajectory(termination=termination)
    for name, args in (tools or []):
        from agent_eval_harness.core.schemas import ToolCallRecord

        traj.tool_calls.append(ToolCallRecord(name=name, arguments=args, ok=True))
    for i in range(steps or 3):
        from agent_eval_harness.core.schemas import StepRecord

        traj.steps.append(StepRecord(index=i, phase="act", summary="s"))
    return AgentRunOutcome(case_id="c", ok=True, final_answer=answer,
                           trajectory=traj)


def test_exact_match():
    ev = ExactMatch()
    assert ev.evaluate(case({"type": "exact", "value": "42"}), outcome("42")).passed
    assert not ev.evaluate(case({"type": "exact", "value": "42"}), outcome("43")).passed


def test_contains_all_case_insensitive():
    ev = ContainsAll()
    c = case({"type": "contains", "values": ["5 days", "90 DAYS"]})
    assert ev.evaluate(c, outcome("carryover is 5 days; rotate every 90 days")).passed
    assert not ev.evaluate(c, outcome("5 days only")).passed


def test_numeric_tolerance_last_number():
    ev = NumericTolerance()
    c = case({"type": "numeric", "value": 1081, "tolerance": 0.5})
    assert ev.evaluate(c, outcome("the answer is 1081.0")).passed
    assert not ev.evaluate(c, outcome("1083")).passed
    assert not ev.evaluate(c, outcome("no numbers")).passed


def test_forbidden_content():
    ev = ForbiddenContent()
    c = case(forbidden_content=["secret", "internal"])
    assert ev.evaluate(c, outcome("public info")).passed
    assert not ev.evaluate(c, outcome("internal memo")).passed


def test_schema_validation():
    ev = SchemaValidation()
    schema = {"type": "object", "required": ["value"],
              "properties": {"value": {"type": "number"}}}
    assert ev.evaluate(case({"type": "schema", "schema": schema}),
                       outcome('{"value": 5}')).passed
    assert not ev.evaluate(case({"type": "schema", "schema": schema}),
                           outcome('{"value": "x"}')).passed
    assert not ev.evaluate(case({"type": "schema", "schema": schema}),
                           outcome("not json")).passed


def test_task_checks_kinds():
    ev = TaskChecks()
    c = case(task_checks=[{"kind": "answer_contains", "value": "5"},
                          {"kind": "answer_numeric", "value": 10},
                          {"kind": "answer_regex", "pattern": r"\d+"},
                          {"kind": "answer_min_words", "value": 2},
                          {"kind": "assumption_stated"}])
    good = outcome("assuming 5 out of 10 things")
    assert ev.evaluate(c, good).passed
    bad = outcome("x")
    res = ev.evaluate(c, bad)
    assert not res.passed and res.score == 0.0


def test_tool_selection():
    ev = ToolSelection()
    c = case(required_tools=["calculator"], forbidden_tools=["store_set"])
    assert ev.evaluate(c, outcome(tools=[("calculator", {"expression": "1"})])).passed
    res = ev.evaluate(c, outcome(tools=[("calculator", {}), ("store_set", {})]))
    assert not res.passed and res.score == 0.0
    res = ev.evaluate(c, outcome(tools=[("text_stats", {})]))
    assert not res.passed and res.details["recall"] == 0.0


def test_tool_arguments():
    ev = ToolArguments()
    c = case(tool_args=[{"tool": "calculator", "arg": "expression",
                         "contains": "23 * 47"}])
    assert ev.evaluate(c, outcome(tools=[("calculator", {"expression": "23 * 47 + 1"})])).passed
    assert not ev.evaluate(c, outcome(tools=[("calculator", {"expression": "1 + 1"})])).passed


def test_step_limit_and_termination():
    c = case(max_steps=3)
    assert StepLimit().evaluate(c, outcome(steps=3)).passed
    assert not StepLimit().evaluate(c, outcome(steps=4)).passed
    assert Termination().evaluate(c, outcome(termination="answer")).passed
    assert not Termination().evaluate(c, outcome(termination="step_limit")).passed


def test_task_checks_invalid_regex_graceful():
    from agent_eval_harness.evaluators.deterministic.outcome import TaskChecks

    ev = TaskChecks()
    c = case(task_checks=[{"kind": "answer_regex", "pattern": "[invalid-regex"}])
    res = ev.evaluate(c, outcome("test text"))
    assert not res.passed
    assert res.score == 0.0

