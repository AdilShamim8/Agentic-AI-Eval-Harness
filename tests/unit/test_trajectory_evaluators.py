"""Trajectory + behavioral evaluator unit tests."""
from agent_eval_harness.core.schemas import (
    AgentRunOutcome,
    StepRecord,
    TestCase,
    ToolCallRecord,
    Trajectory,
)
from agent_eval_harness.evaluators.trajectory.behavior import (
    LoopDetection,
    PlanningQuality,
    RecoveryBehavior,
    TerminationQuality,
    ToolEfficiency,
    TrajectoryAlignment,
    _lcs_len,
)


def make_case(golden=None, required=None, max_steps=12, faults=None):
    return TestCase(
        id="c", pattern="react", category="normal", task="t",
        expected={"answer": {}, "golden_trajectory": golden or [],
                  "required_tools": required or [], "max_steps": max_steps},
        faults=faults or [])


def make_outcome(calls=None, termination="answer", loop=False, final="x",
                 recovered=False, fault_injected=False, plan=None,
                 steps=4, last_phase="final"):
    traj = Trajectory(termination=termination, loop_detected=loop)
    traj.plan = plan or []
    for name, args in (calls or []):
        traj.tool_calls.append(ToolCallRecord(name=name, arguments=args, ok=True))
    for i in range(steps):
        traj.steps.append(StepRecord(index=i, phase="act", summary="s"))
    if last_phase:
        traj.steps.append(StepRecord(index=steps, phase=last_phase, summary="final"))
    return AgentRunOutcome(case_id="c", ok=True, final_answer=final,
                           trajectory=traj, recovered_from_fault=recovered,
                           fault_injected=fault_injected)


def test_lcs():
    assert _lcs_len(["a", "b", "c"], ["a", "b", "c"]) == 3
    assert _lcs_len(["a", "c"], ["a", "b", "c"]) == 2
    assert _lcs_len([], ["a"]) == 0


def test_trajectory_alignment():
    golden = [{"tool": "calculator"}, {"tool": "text_transform"},
              {"tool": "data_calc"}]
    ev = TrajectoryAlignment()
    good = make_outcome(calls=[("calculator", {}), ("text_transform", {}),
                               ("data_calc", {})])
    assert ev.evaluate(make_case(golden), good).passed
    reversed_ = make_outcome(calls=[("data_calc", {}), ("text_transform", {}),
                                    ("calculator", {})])
    res = ev.evaluate(make_case(golden), reversed_)
    assert not res.passed  # ordering matters at sequence length 3
    empty = make_outcome(calls=[])
    assert ev.evaluate(make_case(), empty).passed  # no golden -> n/a pass


def test_tool_efficiency():
    ev = ToolEfficiency()
    golden = [{"tool": "calculator"}]
    clean = make_outcome(calls=[("calculator", {"e": "1"})])
    assert ev.evaluate(make_case(golden), clean).score == 1.0
    wasteful = make_outcome(calls=[("calculator", {"e": "1"}),
                                   ("text_stats", {"t": "x"}),
                                   ("summarize", {"t": "x"})])
    assert ev.evaluate(make_case(golden), wasteful).score < 0.6
    # fault-aware: retry after injected fault is necessary, not waste
    faulted = make_outcome(calls=[("calculator", {"e": "1"}),
                                  ("calculator", {"e": "1"})],
                           recovered=True, fault_injected=True)
    res = ev.evaluate(make_case(golden, faults=[{"tool": "calculator"}]), faulted)
    assert res.score == 1.0


def test_loop_detection():
    ev = LoopDetection()
    assert ev.evaluate(make_case(), make_outcome()).passed
    assert not ev.evaluate(make_case(), make_outcome(loop=True)).passed
    assert not ev.evaluate(make_case(), make_outcome(termination="step_limit")).passed


def test_termination_quality():
    ev = TerminationQuality()
    assert ev.evaluate(make_case(max_steps=5), make_outcome(steps=4)).passed
    assert not ev.evaluate(make_case(max_steps=2), make_outcome(steps=4)).passed
    assert not ev.evaluate(make_case(), make_outcome(termination="timeout")).passed


def test_recovery_behavior():
    ev = RecoveryBehavior()
    assert ev.evaluate(make_case(), make_outcome()).passed  # n/a
    c = make_case(faults=[{"tool": "calculator", "occurrence": 1, "kind": "infra"}])
    assert ev.evaluate(c, make_outcome(recovered=True)).passed
    assert not ev.evaluate(c, make_outcome(recovered=False, fault_injected=True)).passed


def test_planning_quality():
    ev = PlanningQuality()
    c = make_case(required=["calculator", "knowledge_search"])
    good = make_outcome(plan=["Use calculator", "Use knowledge_search"])
    assert ev.evaluate(c, good).passed
    partial = make_outcome(plan=["Use calculator"])
    assert not ev.evaluate(c, partial).passed
    # no plan + no calls -> n/a pass
    assert ev.evaluate(make_case(required=[]), make_outcome(plan=[])).passed
