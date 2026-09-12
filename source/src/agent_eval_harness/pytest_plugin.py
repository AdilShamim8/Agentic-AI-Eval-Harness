"""Pytest integration: run golden benchmark cases as pytest tests.

Usage in your own test suite:

    # conftest.py
    pytest_plugins = ["agent_eval_harness.pytest_plugin"]

    # test_agents.py
    def test_react_smoke(eval_case):
        assert eval_case("react_basic", limit=5)
"""
from __future__ import annotations

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "agent_eval: golden benchmark cases run through the evaluation harness")
    config.addinivalue_line(
        "markers",
        "benchmark: alias of agent_eval (smoke subset for CI)")


@pytest.fixture
def eval_case():
    """Returns a helper: run a benchmark (optionally limited) and return the
    pass rate; asserts the CI gate when `gate=True`."""

    def _run(benchmark: str, limit: int | None = None, gate: bool = False,
             skill: float = 0.85, seed: int = 20260912):
        from agent_eval_harness.registry.registry import load_benchmark
        from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig

        bm = load_benchmark(benchmark)
        runner = BenchmarkRunner(bm, RunConfig(benchmark=benchmark, skill=skill,
                                               seed=seed, limit=limit))
        record = runner.run()
        if gate:
            failed = [g for g, s in record.metrics["threshold_gates"].items()
                      if not s.get("passed")]
            assert not failed, f"threshold gates failed: {failed}"
        return record.pass_rate

    return _run
