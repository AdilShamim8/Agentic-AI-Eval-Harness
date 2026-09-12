"""Pytest-marker smoke suite — the CI evaluation gate (runs in ~2s)."""
import pytest


@pytest.mark.agent_eval
@pytest.mark.parametrize("benchmark,skill", [
    ("react_basic", 0.85),
    ("plan_execute_basic", 0.85),
    ("supervisor_basic", 0.85),
    ("swarm_basic", 0.85),
    ("map_reduce_basic", 0.85),
])
def test_benchmark_smoke(eval_case, benchmark, skill):
    """Smoke: 8 cases per pattern must clear a low floor. Full-suite
    threshold gates are asserted in the CI eval-gate job (all 56 cases)."""
    rate = eval_case(benchmark, limit=8, skill=skill)
    assert rate >= 0.5, f"{benchmark} smoke pass rate {rate:.2f} < 0.50"


@pytest.mark.agent_eval
def test_react_threshold_gate_smoke(eval_case):
    """react_basic's first 8 cases clear its own threshold gates."""
    assert eval_case("react_basic", limit=8, gate=True) >= 0.7


@pytest.mark.agent_eval
def test_failure_recovery_smoke(eval_case):
    """Fault-injection subset must retain >= 50% pass with full harness."""
    rate = eval_case("failure_recovery", gate=True)
    assert rate >= 0.5
