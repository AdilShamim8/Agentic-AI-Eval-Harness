"""Failure-injection tests: evaluator crashes, agent crashes, tool faults,
malformed outputs, loops — the harness must classify and survive all of them."""
import pytest

from agent_eval_harness.agents import create_agent
from agent_eval_harness.agents.model import ScriptedModelConfig
from agent_eval_harness.core.errors import FailureClass
from agent_eval_harness.core.ids import case_seed
from agent_eval_harness.core.schemas import TestCase
from agent_eval_harness.harness.controls import get_ablation
from agent_eval_harness.harness.environment import Environment
from agent_eval_harness.observability.events import EventRecorder
from agent_eval_harness.registry.registry import load_benchmark
from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig


def small_case(cid="f1", task="Compute 5 * 5 using the calculator and report the final value."):
    return TestCase(id=cid, pattern="react", category="normal", task=task,
                    expected={"answer": {"type": "numeric", "value": 25},
                              "required_tools": ["calculator"], "max_steps": 12})


def test_evaluator_crash_classified_and_survived(tmp_path):
    bm = load_benchmark("react_basic")
    runner = BenchmarkRunner(bm, RunConfig(benchmark="react_basic", skill=0.9,
                                           seed=5, limit=3,
                                           out_dir=str(tmp_path)))

    class ExplodingEvaluator:
        name, version = "exploding", "1.0"

        def evaluate(self, case, outcome):
            raise RuntimeError("judge backend exploded")

    runner.evaluators = [ExplodingEvaluator()] + runner.evaluators
    rec = runner.run()
    assert rec.metrics["cases"] == 3
    errored = [v for v in rec.verdicts if v.evaluator_errors == ["exploding"]]
    assert len(errored) == 3
    assert all(v.failure_class == FailureClass.EVALUATOR_ERROR for v in errored)
    assert all(not v.passed for v in errored)


def test_agent_crash_classified():
    case = small_case("crash")
    rec = EventRecorder("crash")
    env = Environment(ablation=get_ablation("full"), events=rec)

    class ExplodingAgent:
        id, pattern = "exploder", "react"

        def describe(self):
            return "exploding"

        def run(self, ctx):
            raise ValueError("agent code bug")

    gw = env.prepare(case)
    # direct raise surfaces as an exception...
    with pytest.raises(ValueError):
        ExplodingAgent().run(env.run_context(case, None, gw))
    # ...and the runner classifies it as AGENT_ERROR (never infra/evaluator):
    from agent_eval_harness.core.errors import classify_exception

    assert classify_exception(ValueError("x")) == FailureClass.AGENT_ERROR


def test_soft_tool_fault_surfaced_without_retry():
    case = small_case("soft", )
    case.faults = [{"tool": "calculator", "occurrence": 1, "kind": "soft",
                    "error": "tool flaky"}]
    rec = EventRecorder("soft")
    env = Environment(ablation=get_ablation("no_retry"), events=rec)
    agent = create_agent("builtin:react", skill=0.99, seed=1,
                         model_config=ScriptedModelConfig(
                             skill=0.99, redundancy=0, malformed_rate=0,
                             early_termination=0, loop_tendency=0, recovery=1.0))
    gw = env.prepare(case)
    agent.model.begin_case(case.id, case_seed(7, case.id))
    outcome = agent.run(env.run_context(case, agent.model, gw))
    # fault surfaced; agent self-recovery re-issued the call and succeeded
    assert outcome.fault_injected
    assert any(e.kind == "fault_injected" for e in rec.events)
    assert outcome.final_answer == "25"


def test_looping_model_hits_step_limit_with_loop_flag():
    case = small_case("loop")
    rec = EventRecorder("loop")
    env = Environment(ablation=get_ablation("full"), events=rec)
    cfg = ScriptedModelConfig(skill=1.0, redundancy=0, malformed_rate=0,
                              early_termination=0, loop_tendency=1.0,
                              recovery=0.0)
    agent = create_agent("builtin:react", model_config=cfg)
    gw = env.prepare(case)
    agent.model.begin_case(case.id, case_seed(7, case.id))
    outcome = agent.run(env.run_context(case, agent.model, gw))
    assert outcome.trajectory.loop_detected
    assert outcome.failure_class == FailureClass.LOOP_DETECTED


def test_infra_fault_without_retry_and_weak_agent_fails():
    case = small_case("infra")
    case.faults = [{"tool": "calculator", "occurrence": 1, "kind": "infra",
                    "error": "calc backend down"}]
    rec = EventRecorder("infra")
    env = Environment(ablation=get_ablation("no_retry"), events=rec)
    cfg = ScriptedModelConfig(skill=0.9, redundancy=0, malformed_rate=0,
                              early_termination=0, loop_tendency=0, recovery=0.0)
    agent = create_agent("builtin:react", model_config=cfg)
    gw = env.prepare(case)
    agent.model.begin_case(case.id, case_seed(7, case.id))
    outcome = agent.run(env.run_context(case, agent.model, gw))
    assert outcome.fault_injected and not outcome.recovered_from_fault
    assert outcome.final_answer != "25"


def test_malformed_final_answer_fails_checks():
    case = small_case("mal")
    rec = EventRecorder("mal")
    env = Environment(ablation=get_ablation("no_verification"), events=rec)
    cfg = ScriptedModelConfig(skill=1.0, redundancy=0, malformed_rate=1.0,
                              early_termination=0, loop_tendency=0, recovery=1.0)
    agent = create_agent("builtin:react", model_config=cfg)
    gw = env.prepare(case)
    agent.model.begin_case(case.id, case_seed(7, case.id))
    outcome = agent.run(env.run_context(case, agent.model, gw))
    assert outcome.trajectory.termination == "error"
