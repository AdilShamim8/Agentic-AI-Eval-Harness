"""Framework adapters: LangGraph, OpenAI Agents SDK, CrewAI.

All are import-guarded and raise InfraError with install hints when the target
framework is absent. Unit tests exercise them with duck-typed stubs; real
framework integration measurements are reported as "Not measured yet" until
exercised against the actual frameworks.
"""
from agent_eval_harness.agents.adapters.crewai_adapter import CrewAIAdapter
from agent_eval_harness.agents.adapters.langgraph_adapter import LangGraphAdapter
from agent_eval_harness.agents.adapters.openai_agents_adapter import OpenAIAgentsAdapter

__all__ = ["LangGraphAdapter", "OpenAIAgentsAdapter", "CrewAIAdapter"]
