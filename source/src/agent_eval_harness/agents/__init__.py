"""Agent construction: built-in pattern agents + custom Python agent loading."""
from __future__ import annotations

import importlib.util
from typing import Any

from agent_eval_harness.agents.base import AgentAdapter, RunContext
from agent_eval_harness.agents.map_reduce import MapReduceAgent
from agent_eval_harness.agents.model import (
    MODEL_BACKEND_VERSION,
    ModelBackend,
    ScriptedModel,
    ScriptedModelConfig,
)
from agent_eval_harness.agents.plan_execute import PlanExecuteAgent
from agent_eval_harness.agents.react import ReActAgent
from agent_eval_harness.agents.supervisor import SupervisorAgent
from agent_eval_harness.agents.swarm import SwarmAgent
from agent_eval_harness.core.errors import InfraError

PATTERN_AGENTS = {
    "react": ReActAgent,
    "plan_execute": PlanExecuteAgent,
    "supervisor": SupervisorAgent,
    "swarm": SwarmAgent,
    "map_reduce": MapReduceAgent,
}


def create_agent(
    spec: str,
    *,
    skill: float = 0.85,
    model_config: ScriptedModelConfig | None = None,
    seed: int = 0,
) -> AgentAdapter:
    """Build an agent from a spec.

    Supported:
      builtin:<pattern>            e.g. builtin:react (5 patterns)
      /path/to/module.py:attr      custom Python agent (must satisfy AgentAdapter)
    """
    if spec.startswith("builtin:"):
        pattern = spec.split(":", 1)[1]
        if pattern not in PATTERN_AGENTS:
            raise InfraError(
                f"unknown pattern '{pattern}' (available: {sorted(PATTERN_AGENTS)})")
        cfg = model_config or ScriptedModelConfig(skill=skill, seed=seed)
        model: ModelBackend = ScriptedModel(cfg)
        agent = PATTERN_AGENTS[pattern](f"builtin_{pattern}", model)
        return agent

    if spec.endswith(".py") or (":" in spec and spec.split(":")[0].endswith(".py")):
        return _load_custom_agent(spec)

    raise InfraError(
        f"unrecognized agent spec '{spec}' "
        "(use builtin:<pattern> or /path/to/agent.py:attr)")


def _load_custom_agent(spec: str) -> AgentAdapter:
    path, _, attr = spec.partition(":")
    attr = attr or "agent"
    try:
        mod_name = "aeh_custom_agent_" + path.replace("/", "_").replace(".", "_")
        loader = importlib.util.spec_from_file_location(mod_name, path)
        if loader is None or loader.loader is None:
            raise InfraError(f"cannot load module from '{path}'")
        module = importlib.util.module_from_spec(loader.loader and loader or None)
        loader.loader.exec_module(module)
    except FileNotFoundError as exc:
        raise InfraError(f"agent module not found: {path}") from exc
    except Exception as exc:  # noqa: BLE001 - surfaced as infra error with cause
        raise InfraError(f"failed to import agent module '{path}': {exc}") from exc
    obj = getattr(module, attr, None)
    if obj is None or not _is_adapter(obj):
        raise InfraError(
            f"module '{path}' attribute '{attr}' does not satisfy AgentAdapter protocol")
    return obj


def _is_adapter(obj: Any) -> bool:
    return (
        hasattr(obj, "id")
        and hasattr(obj, "pattern")
        and hasattr(obj, "run")
        and hasattr(obj, "describe")
    )


__all__ = [
    "create_agent",
    "PATTERN_AGENTS",
    "AgentAdapter",
    "RunContext",
    "ScriptedModel",
    "ScriptedModelConfig",
    "MODEL_BACKEND_VERSION",
]
