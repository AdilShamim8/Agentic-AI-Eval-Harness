"""Execution environment — assembles the harness around one case.

The Environment is the composition root the runner uses per case:
fresh store, fresh gateway, model begin_case, RunContext wiring. Total
wall-clock budget is enforced cooperatively between agent steps.
"""
from __future__ import annotations

import time
from typing import Any

from agent_eval_harness.agents.base import RunContext
from agent_eval_harness.agents.tools import reset_case_store
from agent_eval_harness.core.errors import TimeoutExceeded
from agent_eval_harness.core.schemas import TestCase
from agent_eval_harness.harness.controls import (
    AblationProfile,
    ExecutionLimits,
    PermissionPolicy,
)
from agent_eval_harness.harness.gateway import ToolGateway
from agent_eval_harness.observability.events import EventRecorder


class Environment:
    def __init__(
        self,
        limits: ExecutionLimits | None = None,
        policy: PermissionPolicy | None = None,
        ablation: AblationProfile | None = None,
        events: EventRecorder | None = None,
    ):
        self.limits = limits or ExecutionLimits()
        self.policy = policy or PermissionPolicy()
        self.ablation = ablation or AblationProfile()
        self.events = events

    def prepare(self, case: TestCase) -> ToolGateway:
        """Reset per-case state and build the gateway."""
        reset_case_store()
        self._t0 = time.perf_counter()
        return ToolGateway(case, self.limits, self.policy, self.ablation, self.events)

    def run_context(self, case: TestCase, model: Any, gateway: ToolGateway) -> RunContext:
        return RunContext(case=case, model=model, gateway=gateway,
                          events=self.events, limits=self.limits,
                          ablation=self.ablation)

    def check_total_timeout(self) -> None:
        elapsed_ms = (time.perf_counter() - self._t0) * 1000
        if elapsed_ms > self.limits.total_timeout_ms:
            raise TimeoutExceeded(
                f"case exceeded total timeout "
                f"({elapsed_ms:.0f}ms > {self.limits.total_timeout_ms}ms)")
