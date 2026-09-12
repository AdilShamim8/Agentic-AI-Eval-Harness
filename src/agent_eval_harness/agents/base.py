"""Agent adapter protocol + shared pattern-agent machinery.

The unit under test is ALWAYS an AgentAdapter. Built-in pattern agents consume
a ModelBackend (scripted deterministic, or any live LLM implementation of the
same protocol). Framework adapters (LangGraph / OpenAI Agents SDK / CrewAI)
translate foreign runtimes into this protocol.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from agent_eval_harness.agents.model import (
    Action,
    FinalAnswer,
    Handoff,
    Malformed,
    ModelState,
    ModelBackend,
    Plan,
    Think,
    ToolCallDecision,
    estimate_tokens,
)
from agent_eval_harness.agents.tools import ToolResult
from agent_eval_harness.core.errors import (
    AgentError,
    FailureClass,
    HarnessError,
    LoopDetected,
    classify_exception,
)
from agent_eval_harness.core.schemas import (
    AgentRunOutcome,
    StepRecord,
    TestCase,
    ToolCallRecord,
    Trajectory,
)

LOOP_THRESHOLD = 3  # identical calls before we declare a loop


@runtime_checkable
class EventSink(Protocol):
    def emit(self, kind: str, payload: dict[str, Any], phase: str = "", case_id: str = "") -> None: ...


@runtime_checkable
class ToolGatewayProtocol(Protocol):
    def call(self, name: str, args: dict[str, Any]) -> ToolResult: ...
    def remaining_tool_budget(self) -> int: ...
    def case_id(self) -> str: ...
    def stats(self) -> dict[str, Any]: ...


@dataclass
class RunContext:
    """Everything an agent may touch inside the harness. Capabilities are
    mediated by the gateway (permissions/limits/retries) and observed by the
    event sink. No direct tool access, no wall-clock in decisions."""

    case: TestCase
    model: ModelBackend
    gateway: ToolGatewayProtocol
    events: EventSink
    limits: Any = None
    ablation: Any = None

    @property
    def task(self) -> str:
        return self.case.task

    @property
    def context(self) -> dict[str, Any]:
        return self.case.context


@runtime_checkable
class AgentAdapter(Protocol):
    id: str
    pattern: str

    def describe(self) -> str: ...
    def run(self, ctx: RunContext) -> AgentRunOutcome: ...


class BasePatternAgent:
    """Shared control loop for the built-in pattern agents.

    Subclasses implement `run()` by: deriving the task understanding from the
    model, building a ModelState, then driving `_act_loop` (possibly wrapped in
    pattern-specific structure: plans, handoffs, map/reduce phases).
    """

    pattern = "custom"

    def __init__(self, agent_id: str, model: ModelBackend):
        self.id = agent_id
        self.model = model

    def describe(self) -> str:
        return f"{type(self).__name__}(model={getattr(self.model, 'version', '?')})"

    # ------------------------------------------------------------------
    def run(self, ctx: RunContext) -> AgentRunOutcome:  # pragma: no cover - abstract
        raise NotImplementedError

    # -- shared loop ----------------------------------------------------
    def _act_loop(
        self,
        ctx: RunContext,
        state: ModelState,
        traj: Trajectory,
        *,
        phase_label: str = "act",
        on_handoff: Any = None,
        max_steps: int = 12,
        final_retries: int = 2,
    ) -> tuple[str, str]:
        """Run decisions until FinalAnswer / limits. Returns (termination, answer)."""
        tokens_in = tokens_out = 0
        verification_on = getattr(ctx.ablation, "verification", True) if ctx.ablation else True
        loop_seen: dict[str, int] = {}

        while state.step_index < max_steps:
            decision = ctx.model.decide(state)
            tokens_out += estimate_tokens(type(decision).__name__ + str(getattr(decision, "content", "") or ""))
            tokens_in += estimate_tokens(state.task)

            if isinstance(decision, Think):
                self._step(traj, state, "think", decision.content[:200])
                if "assuming" in decision.content.lower():
                    state.scratchpad["assumption_stated"] = True
                state.step_index += 1
                continue

            if isinstance(decision, Plan):  # plan mid-flight (replan)
                traj.plan.extend(decision.steps)
                for s in decision.steps:
                    self._step(traj, state, "plan", s[:200])
                state.step_index += 1
                continue

            if isinstance(decision, Handoff) and on_handoff is not None:
                termination, answer = on_handoff(decision, state, traj)
                if termination:
                    return termination, answer
                state.step_index += 1
                continue

            if isinstance(decision, Malformed):
                self._step(traj, state, "error", f"malformed decision: {decision.raw[:120]}")
                if verification_on and final_retries > 0:
                    final_retries -= 1
                    state.step_index += 1
                    continue  # ask the model to re-emit cleanly
                return "error", decision.raw  # unverified passthrough

            if isinstance(decision, FinalAnswer):
                text = decision.text.strip()
                if verification_on and (not text or len(text) > 4000):
                    if final_retries > 0:
                        final_retries -= 1
                        state.step_index += 1
                        continue
                    return "error", text or "(empty answer)"
                self._step(traj, state, "final", f"final answer: {text[:200]}")
                return "answer", text

            if isinstance(decision, ToolCallDecision):
                if ctx.gateway.remaining_tool_budget() <= 0:
                    traj.termination = "tool_limit"
                    return "tool_limit", ""
                self._step(traj, state, "act", f"call {decision.name}({json.dumps(decision.args, sort_keys=True)[:160]})",
                           phase_label)
                res = ctx.gateway.call(decision.name, dict(decision.args))
                traj.tool_calls.append(
                    ToolCallRecord(
                        name=decision.name,
                        arguments=decision.args,
                        ok=res.ok,
                        value=res.value,
                        error=res.error,
                        latency_ms=res.latency_ms if hasattr(res, "latency_ms") else 0.0,
                        attempt=ctx.gateway.stats().get("attempts", 1) if res.ok else 1,
                    )
                )
                obs = ctx.gateway.observation(decision.name, res)
                state.history.append(obs)
                tokens_in += estimate_tokens(json.dumps(obs, sort_keys=True, default=str))
                self._step(traj, state, "observe",
                           f"{decision.name} -> {'ok' if res.ok else 'error: ' + res.error[:120]}",
                           phase_label)

                canon = json.dumps({"name": decision.name, "arguments": decision.args},
                                   sort_keys=True, separators=(",", ":"))
                if canon in loop_seen:
                    loop_seen[canon] += 1
                    if loop_seen[canon] >= LOOP_THRESHOLD:
                        traj.loop_detected = True
                        raise LoopDetected(
                            f"identical call repeated {loop_seen[canon]}x: {decision.name}")
                else:
                    loop_seen[canon] = 1

                # agent-level recovery from tool error results
                if not res.ok:
                    self._maybe_retry_action(ctx, state, decision, res.error)
                else:
                    traj.redundant_calls += sum(
                        1 for c in traj.tool_calls[:-1]
                        if c.name == decision.name and c.arguments == decision.args
                    )
                state.step_index += 1
                continue

            raise AgentError(f"unknown decision type: {type(decision).__name__}")

        traj.termination = "step_limit"
        return "step_limit", ""

    # ------------------------------------------------------------------
    def _maybe_retry_action(self, ctx: RunContext, state: ModelState,
                            decision: ToolCallDecision, error: str = "") -> None:
        """Recovery from a failed tool call.

        Validation/denial errors are deterministic: re-issuing the identical
        call cannot succeed, so we ask the model to re-plan the original
        action instead. Transient errors (tool errors, surfaced infra faults)
        are retried when the model's recovery policy fires.
        """
        validation_like = error.startswith((
            "invalid arguments", "unknown tool", "unknown argument",
            "permission denied", "argument '", "tool-call budget",
        ))
        if validation_like:
            unemit = getattr(ctx.model, "retry_last_action", None)
            if unemit is not None:
                unemit()
            return
        retry = getattr(self.model, "policy_retry", None)
        if retry is not None and retry():
            action = Action("tool", decision.name, dict(decision.args))
            state.pending.append(action)
            unemit = getattr(self.model, "retry_action", None)
            if unemit is not None:
                unemit(action)

    def _step(self, traj: Trajectory, state: ModelState, phase: str, summary: str,
              label: str = "act") -> None:
        idx = traj.step_count()
        traj.steps.append(
            StepRecord(index=idx, phase=phase, summary=summary[:240],
                       tool_call=None, agent=label if label != "act" else self.id)
        )

    # ------------------------------------------------------------------
    def _finish(
        self,
        ctx: RunContext,
        traj: Trajectory,
        termination: str,
        answer: str,
        error: str = "",
        failure_class: FailureClass = FailureClass.NONE,
    ) -> AgentRunOutcome:
        traj.termination = termination
        stats = ctx.gateway.stats()
        ok = termination == "answer" and not error
        return AgentRunOutcome(
            case_id=ctx.case.id,
            ok=ok,
            final_answer=answer,
            trajectory=traj,
            failure_class=failure_class if not ok else FailureClass.NONE,
            error=error,
            latency_ms=0.0,  # set by the runner (wall clock around run())
            tokens_in_est=stats.get("tokens_in_est", 0),
            tokens_out_est=stats.get("tokens_out_est", 0),
            security_flags=list(stats.get("security_flags", [])),
            retried_calls=stats.get("retried_calls", 0),
            recovered_from_fault=stats.get("recovered_from_fault", False),
            fault_injected=stats.get("fault_injected", False),
        )

    def _guard(self, ctx: RunContext, traj: Trajectory, exc: BaseException) -> AgentRunOutcome:
        fc = classify_exception(exc)
        traj.termination = "error"
        return self._finish(ctx, traj, "error", "", error=str(exc), failure_class=fc)
