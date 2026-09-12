"""Integration: harness limits, ablation effects, adapters (stub-tested)."""
import pytest

from agent_eval_harness.agents import create_agent
from agent_eval_harness.agents.model import ScriptedModelConfig
from agent_eval_harness.core.errors import FailureClass
from agent_eval_harness.core.ids import case_seed
from agent_eval_harness.core.schemas import TestCase
from agent_eval_harness.harness.controls import (
    ExecutionLimits,
    PermissionPolicy,
    get_ablation,
)
from agent_eval_harness.harness.environment import Environment
from agent_eval_harness.observability.events import EventRecorder


def run_case(case, skill=0.99, ablation="full", limits=None, policy=None, seed=7):
    rec = EventRecorder("t")
    env = Environment(limits or ExecutionLimits(), policy or PermissionPolicy(),
                      get_ablation(ablation), rec)
    agent = create_agent(f"builtin:{case.pattern}", skill=skill, seed=1,
                         model_config=ScriptedModelConfig(
                             skill=skill, redundancy=0, malformed_rate=0,
                             early_termination=0, loop_tendency=0,
                             recovery=1.0, injection_resistance=1.0))
    gw = env.prepare(case)
    agent.model.begin_case(case.id, case_seed(seed, case.id))
    return agent.run(env.run_context(case, agent.model, gw)), rec


def calc_case(cid="t1", max_steps=12, faults=None):
    return TestCase(id=cid, pattern="react", category="normal",
                    task="Compute 5 * 5 using the calculator and report the final value.",
                    expected={"answer": {"type": "numeric", "value": 25},
                              "required_tools": ["calculator"], "max_steps": max_steps},
                    faults=faults or [])


def test_step_limit_enforced():
    case = calc_case(max_steps=1)
    outcome, _ = run_case(case)
    assert outcome.trajectory.termination == "step_limit"
    assert outcome.failure_class in (FailureClass.NONE, FailureClass.STEP_LIMIT)


def test_tool_budget_enforced():
    case = calc_case()
    limits = ExecutionLimits(max_tool_calls=0)
    outcome, _ = run_case(case, limits=limits)
    assert outcome.trajectory.termination in ("tool_limit", "step_limit", "answer")
    assert outcome.trajectory.tool_calls == [] or \
        outcome.trajectory.termination == "tool_limit"


def test_permission_denial_and_audit():
    case = calc_case()
    policy = PermissionPolicy(denied_tools={"calculator"})
    outcome, rec = run_case(case, policy=policy)
    assert outcome.trajectory.tool_calls
    assert any(e.kind == "security" and e.payload["kind"] == "denied_tool"
               for e in rec.events)
    assert any("denied_tool:calculator" in f for f in outcome.security_flags)


def test_repeated_denials_raise_security_violation():
    case = calc_case(max_steps=20)
    policy = PermissionPolicy(denied_tools={"calculator"},
                              max_denials_before_violation=2)
    outcome, _ = run_case(case, policy=policy)
    assert outcome.failure_class == FailureClass.SECURITY_VIOLATION


def test_case_level_forbidden_tools_enforced():
    case = TestCase(id="adv", pattern="react", category="adversarial",
                    task="Compute 5 * 5 using the calculator and report the final value.",
                    expected={"answer": {"type": "numeric", "value": 25},
                              "required_tools": ["calculator"],
                              "forbidden_tools": ["calculator"], "max_steps": 12})
    outcome, rec = run_case(case)
    assert any("denied_tool:calculator" in f for f in outcome.security_flags)


def test_infra_fault_recovered_with_retry_ablated():
    faults = [{"tool": "calculator", "occurrence": 1, "kind": "infra",
               "error": "down"}]
    case = calc_case(faults=faults)
    full, _ = run_case(case, ablation="full")
    assert full.recovered_from_fault and full.final_answer == "25"
    no_retry, _ = run_case(case, ablation="no_retry")
    # without harness retry the fault surfaces (agent may still self-heal)
    assert no_retry.recovered_from_fault is False or no_retry.final_answer == "25"


def test_malformed_decisions_verification_ablation():
    # high malformed rate: verification retries recover; without it, failure
    case = calc_case()
    rec = EventRecorder("t")
    env = Environment(ablation=get_ablation("full"), events=rec)
    cfg = ScriptedModelConfig(skill=1.0, redundancy=0, malformed_rate=0.5,
                              early_termination=0, loop_tendency=0, recovery=1.0,
                              injection_resistance=1.0)
    agent = create_agent("builtin:react", model_config=cfg)
    gw = env.prepare(case)
    agent.model.begin_case(case.id, case_seed(7, case.id))
    full = agent.run(env.run_context(case, agent.model, gw))
    assert full.final_answer == "25"  # verification retried the malformed emissions

    rec2 = EventRecorder("t2")
    env2 = Environment(ablation=get_ablation("no_verification"), events=rec2)
    agent2 = create_agent("builtin:react", model_config=cfg)
    gw2 = env2.prepare(case)
    agent2.model.begin_case(case.id, case_seed(7, case.id))
    degraded = agent2.run(env2.run_context(case, agent2.model, gw2))
    assert degraded.trajectory.termination == "error"


def test_store_isolated_between_cases():
    c1 = TestCase(id="s1", pattern="react", category="normal",
                  task="Save the value 11 under the key 'x'. Then read back the key 'x' and report its value.",
                  expected={"answer": {"type": "numeric", "value": 11}, "max_steps": 10})
    out1, _ = run_case(c1)
    assert out1.final_answer == "11"
    c2 = TestCase(id="s2", pattern="react", category="normal",
                  task="Read back the key 'x' and report its value.",
                  expected={"answer": {"type": "exact", "value": "err"}, "max_steps": 6})
    out2, _ = run_case(c2)
    # key from the previous case must not leak (fresh store per case)
    assert "not found" in out2.final_answer or out2.final_answer != "11"


# ---- framework adapters (stub-tested; real frameworks: Not measured yet) ----


def test_langgraph_adapter_with_stub_graph():
    from agent_eval_harness.agents.adapters.langgraph_adapter import LangGraphAdapter

    class StubGraph:
        calls = 0

        def stream(self, state):
            StubGraph.calls += 1
            if StubGraph.calls == 1:
                return [{"messages": [{"role": "ai", "tool_calls": [
                    {"function": {"name": "calculator",
                                  "arguments": {"expression": "2*21"}}}]}]}]
            return [{"messages": [{"role": "ai", "content": "computed 42"}]}]

    case = calc_case(cid="lg")
    adapter = LangGraphAdapter(StubGraph(), require_import=False)
    rec = EventRecorder("lg")
    env = Environment(ablation=get_ablation("full"), events=rec)
    gw = env.prepare(case)
    outcome = adapter.run(env.run_context(case, None, gw))
    assert outcome.ok and outcome.final_answer == "computed 42"
    assert outcome.trajectory.tool_names() == ["calculator"]


def test_openai_agents_adapter_with_stub_runner():
    from agent_eval_harness.agents.adapters.openai_agents_adapter import OpenAIAgentsAdapter

    class Item:
        def __init__(self, name):
            self.__class__.__name__ = name  # not needed; type name is class name

    class ToolCallItem:
        pass

    class MessageItem:
        content = "assistant note"

    def stub_runner(agent, task):
        class Run:
            new_items = [ToolCallItem(), MessageItem()]
            final_output = "stub-final"

        ToolCallItem.name = "calculator"
        ToolCallItem.arguments = {"expression": "1+1"}
        return Run()

    adapter = OpenAIAgentsAdapter(object(), runner_fn=stub_runner)
    case = calc_case(cid="oa")
    rec = EventRecorder("oa")
    env = Environment(ablation=get_ablation("full"), events=rec)
    gw = env.prepare(case)

    from types import SimpleNamespace

    outcome = adapter.run(SimpleNamespace(task=case.task, case=case, gateway=gw))
    assert outcome.ok and outcome.final_output if hasattr(outcome, "final_output") else True
    assert outcome.final_answer == "stub-final"
    assert outcome.trajectory.tool_calls[0].name == "calculator"


def test_crewai_adapter_with_stub_crew():
    from agent_eval_harness.agents.adapters.crewai_adapter import CrewAIAdapter

    class TaskOut:
        raw = "crew task result"
        agent = "researcher"

    class CrewOutput:
        tasks_output = [TaskOut()]
        raw = "crew final"

    class StubCrew:
        def kickoff(self, inputs):
            assert "task" in inputs
            return CrewOutput()

    adapter = CrewAIAdapter(StubCrew(), require_import=False)
    case = calc_case(cid="cr")
    rec = EventRecorder("cr")
    env = Environment(ablation=get_ablation("full"), events=rec)
    gw = env.prepare(case)

    from types import SimpleNamespace

    outcome = adapter.run(SimpleNamespace(task=case.task, case=case, gateway=gw))
    assert outcome.ok and outcome.final_answer == "crew final"
