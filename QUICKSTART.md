# QUICKSTART — 10 minutes to trustworthy agent evaluation

## 1. Install and validate (1 min)

```bash
pip install -e .[dev]
make validate            # all benchmarks + datasets structurally valid
agent-eval list benchmarks
```

## 2. Run your first benchmark (2 min)

```bash
agent-eval run --benchmark react_basic
# → Run table + run record in evals/runs/<run_id>.json + event log .events.jsonl
```

The default agent is the built-in ReAct pattern on the deterministic scripted
backend — reproducible, free, offline. Pass rate, per-evaluator scores, Wilson
95% CI, trajectory/behavior metrics, and threshold gates all land in the run
record.

## 3. Read a report (2 min)

```bash
RUN_ID=$(ls -t evals/runs/*.json | head -1 | xargs basename | cut -d. -f1)
agent-eval report $RUN_ID --format md --out report.md
```

The report separates **TEST FAILURE / EVALUATOR ERROR / INFRASTRUCTURE
FAILURE**, shows per-category difficulty buckets, tool metrics, loop/recovery
rates, and ends with rule-based recommendations.

## 4. Compare versions and gate CI (3 min)

```bash
agent-eval run --benchmark react_basic --baseline main          # save baseline
agent-eval run --benchmark react_basic --skill 0.70             # a "new version"
NEW=$(ls -t evals/runs/*.json | head -1 | xargs basename | cut -d. -f1)
agent-eval regression $NEW --baseline main     # exit 1 → REGRESSION DETECTED
agent-eval compare <old> $NEW                 # per-case flips + McNemar p
```

Thresholds live in `configs/gates.yaml`. The GitHub Actions `eval-gate` job
runs exactly these commands and blocks merges on regressions.

## 5. Run benchmarks as pytest (1 min)

```bash
pytest -m agent_eval tests/e2e     # smoke subset
```

Or in your own test suite:

```python
# conftest.py
pytest_plugins = ["agent_eval_harness.pytest_plugin"]

def test_react(eval_case):
    assert eval_case("react_basic", limit=8, gate=True) >= 0.7
```

## 6. Plug in YOUR agent (1 min)

```python
# my_agent.py
from agent_eval_harness.agents.base import BasePatternAgent, RunContext
from agent_eval_harness.core.schemas import AgentRunOutcome

class MyAgent(BasePatternAgent):
    pattern = "react"
    def run(self, ctx: RunContext) -> AgentRunOutcome:
        ...  # use ctx.gateway.call(tool, args) for every tool interaction

agent = MyAgent("my_agent", my_model_backend)
```

```bash
agent-eval run --benchmark react_basic --agent ./my_agent.py:agent
```

Framework agents: see `src/agent_eval_harness/agents/adapters/` —
`LangGraphAdapter(graph)`, `OpenAIAgentsAdapter(sdk_agent)`,
`CrewAIAdapter(crew)`. Route tools through `ctx.gateway` to keep permissions,
limits, retries, and tracing active.

## 7. Go further

- Harness ablations: `make ablate` (which harness features actually help?)
- Judge calibration: `make calibrate` (Cohen's κ vs hand labels)
- Reproducibility: `make repro`
- Full experiment suite: `make experiments`
- Security: `make security` + read `docs/security/THREAT-MODEL.md`
