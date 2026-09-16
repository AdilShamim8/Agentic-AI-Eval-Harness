"""Bridge module used by e2e pytest-integration test."""
import tempfile

from agent_eval_harness.registry.registry import load_benchmark
from agent_eval_harness.runner.runner import BenchmarkRunner, RunConfig


def run_bridge() -> float:
    bm = load_benchmark("react_basic")
    with tempfile.TemporaryDirectory(prefix="bridge_runs_") as tmpdir:
        runner = BenchmarkRunner(bm, RunConfig(benchmark="react_basic", skill=0.85,
                                               seed=20260912, limit=5, out_dir=tmpdir))
        return runner.run().pass_rate
