"""ToolGateway — the harness's mediation layer between agents and tools.

Every tool call passes through: permission check -> argument guards ->
(ablatable) schema validation + repair -> (ablatable) retry with fault
injection -> handler execution under limits -> observation (optionally
context-optimized) -> events + stats.

This module is where "harness engineering" becomes concrete: retry, tool
validation, and context optimization are the capabilities the ablation study
attributes performance to.
"""
from __future__ import annotations

import json
import time
from typing import Any

from agent_eval_harness.agents import tools as toolmod
from agent_eval_harness.agents.model import estimate_tokens
from agent_eval_harness.core.errors import ToolInfraError
from agent_eval_harness.core.schemas import TestCase
from agent_eval_harness.harness.controls import (
    AblationProfile,
    ExecutionLimits,
    PermissionPolicy,
)
from agent_eval_harness.observability.events import EventRecorder
from agent_eval_harness.security.injection import screen_text


def _repair_args(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Deterministic repair of common arg mistakes (validation layer)."""
    args = dict(args)
    if name == "calculator" and "expression" in args:
        args["expression"] = " ".join(str(args["expression"]).split())
    if name in ("data_calc",) and isinstance(args.get("values"), str):
        raw = args["values"].strip("[] ")
        vals: list[float] = []
        for piece in raw.split(","):
            piece = piece.strip()
            if not piece:
                continue
            try:
                vals.append(float(piece) if "." in piece else int(piece))
            except ValueError:
                return args
        args["values"] = vals
    if name in ("summarize", "text_stats", "text_transform", "knowledge_search"):
        for key in ("text", "query"):
            if key in args and not isinstance(args[key], str):
                args[key] = str(args[key])
    if name == "summarize" and "max_sentences" in args and isinstance(
            args.get("max_sentences"), str):
        try:
            args["max_sentences"] = int(args["max_sentences"])
        except ValueError:
            pass
    return args


class ToolGateway:
    """Per-case gateway. Constructed by the environment for every case."""

    def __init__(
        self,
        case: TestCase,
        limits: ExecutionLimits,
        policy: PermissionPolicy,
        ablation: AblationProfile,
        events: EventRecorder,
    ):
        self._case = case
        self._limits = limits
        self._policy = policy
        self._ablation = ablation
        self._events = events
        self._calls = 0
        self._attempts = 0
        self._retried_calls = 0
        self._denials = 0
        self._per_tool: dict[str, int] = {}
        self._fault_counters: dict[str, int] = {}
        self.security_flags: list[str] = []
        self.fault_injected = False
        self.recovered_from_fault = False
        self._tokens_in = 0
        self._tokens_out = 0
        self._obs_seen: dict[str, str] = {}

    # ------------------------------------------------------------------ API
    def case_id(self) -> str:
        return self._case.id

    def remaining_tool_budget(self) -> int:
        return max(0, self._limits.max_tool_calls - self._calls)

    def stats(self) -> dict[str, Any]:
        return {
            "calls": self._calls,
            "attempts": self._attempts,
            "retried_calls": self._retried_calls,
            "per_tool": dict(self._per_tool),
            "security_flags": list(self.security_flags),
            "fault_injected": self.fault_injected,
            "recovered_from_fault": self.recovered_from_fault,
            "tokens_in_est": self._tokens_in,
            "tokens_out_est": self._tokens_out,
        }

    # ------------------------------------------------------------------ call
    def call(self, name: str, args: dict[str, Any]) -> toolmod.ToolResult:
        self._events.emit("tool_call", {"tool": name, "args": args},
                          phase="act", case_id=self._case.id)
        self._tokens_in += estimate_tokens(json.dumps(args, sort_keys=True, default=str))

        if self._calls >= self._limits.max_tool_calls:
            self._events.emit("tool_limit", {"calls": self._calls}, phase="act",
                              case_id=self._case.id)
            return toolmod.ToolResult(ok=False, error="tool-call budget exhausted")

        denial = self._policy.check_tool(name)
        if not denial and name in self._case.forbidden_tools:
            denial = (f"tool '{name}' is forbidden for this case "
                      f"(case-level policy)")
        if denial:
            self._denials += 1
            self.security_flags.append(f"denied_tool:{name}")
            self._events.emit("security", {"kind": "denied_tool", "tool": name,
                                           "detail": denial},
                              phase="act", case_id=self._case.id)
            if self._denials >= self._policy.max_denials_before_violation:
                from agent_eval_harness.core.errors import SecurityViolation

                raise SecurityViolation(
                    f"repeated policy denials ({self._denials}) on tool '{name}'")
            return toolmod.ToolResult(ok=False, error=f"permission denied: {denial}")

        spec = toolmod.TOOLS.get(name)
        if spec is None:
            return toolmod.ToolResult(ok=False,
                                      error=f"unknown tool '{name}'")

        # argument guards (always on — security, not ablatable)
        for key in args:
            if key in self._policy.forbidden_arg_keys:
                self.security_flags.append(f"forbidden_arg:{name}.{key}")
                self._events.emit("security",
                                  {"kind": "forbidden_arg", "tool": name, "arg": key},
                                  phase="act", case_id=self._case.id)
                return toolmod.ToolResult(
                    ok=False, error=f"argument '{key}' is forbidden by policy")
        for key, val in args.items():
            if isinstance(val, str) and len(val) > self._limits.max_args_chars:
                return toolmod.ToolResult(
                    ok=False, error=f"argument '{key}' exceeds length cap")

        # ablatable validation + repair
        if self._ablation.tool_validation:
            args = _repair_args(name, args)
            err = spec.validate_args(args)
            if err:
                return toolmod.ToolResult(ok=False, error=f"invalid arguments: {err}")

        self._calls += 1
        self._per_tool[name] = self._per_tool.get(name, 0) + 1
        self._attempts += 1

        # fault injection + retry loop
        attempt = 0
        while True:
            attempt += 1
            fault = self._match_fault(name)
            if fault is not None:
                self.fault_injected = True
                self._events.emit("fault_injected",
                                  {"tool": name, "kind": fault.get("kind"),
                                   "attempt": attempt},
                                  phase="act", case_id=self._case.id)
                if fault.get("kind") == "infra":
                    if self._ablation.retry and attempt <= self._limits.max_retries_per_call:
                        self._retried_calls += 1
                        self._events.emit("tool_retry", {"tool": name, "attempt": attempt},
                                          phase="act", case_id=self._case.id)
                        continue  # fault occurrence consumed -> retry succeeds
                    self._events.emit("infra_fault_surfaced", {"tool": name},
                                      phase="act", case_id=self._case.id)
                    return toolmod.ToolResult(
                        ok=False,
                        error=f"infrastructure error: {fault.get('error', 'tool unavailable')}")
                return toolmod.ToolResult(
                    ok=False, error=f"tool error: {fault.get('error', 'tool failed')}")

            t0 = time.perf_counter()
            try:
                value = spec.handler(args)
            except ToolInfraError:
                raise
            except Exception as exc:  # noqa: BLE001 - tools convert to results
                value = toolmod.ToolResult(ok=False, error=f"tool crashed: {exc}")
            latency_ms = (time.perf_counter() - t0) * 1000
            if latency_ms > self._limits.per_tool_timeout_ms:
                self.security_flags.append(f"tool_timeout:{name}")
                return toolmod.ToolResult(
                    ok=False,
                    error=f"tool '{name}' exceeded per-call timeout "
                          f"({latency_ms:.0f}ms > {self._limits.per_tool_timeout_ms}ms)")

            res = value if isinstance(value, toolmod.ToolResult) else toolmod.ToolResult(
                ok=True, value=value)
            if res.ok and self.fault_injected and name in {
                    f.get("tool") for f in self._case.faults}:
                self.recovered_from_fault = True
            # output size cap
            try:
                blob = json.dumps(res.value, default=str)
            except (TypeError, ValueError):
                blob = str(res.value)
            if len(blob) > self._limits.max_output_chars:
                res = toolmod.ToolResult(ok=False, error="tool output exceeded size cap")

            self._tokens_out += estimate_tokens(blob)
            self._events.emit("tool_result",
                              {"tool": name, "ok": res.ok,
                               "error": res.error[:200] if res.error else "",
                               "latency_ms": round(latency_ms, 3)},
                              phase="observe", case_id=self._case.id)
            # injection screening on tool outputs
            if res.ok:
                text = blob if isinstance(blob, str) else str(res.value)
                flags = screen_text(text[:5000])
                if flags:
                    for f in flags:
                        self.security_flags.append(f"injection_in_tool_output:{f}")
                    self._events.emit("security",
                                      {"kind": "injection_flagged", "tool": name,
                                       "patterns": flags},
                                      phase="observe", case_id=self._case.id)
            return res

    # ------------------------------------------------------------------ obs
    def observation(self, name: str, res: toolmod.ToolResult) -> dict[str, Any]:
        """Observation dict for the model's history, context-optimized if enabled."""
        obs = {"tool": name, "ok": res.ok, "value": res.value, "error": res.error}
        if not self._ablation.context_optimization:
            return obs
        # dedup identical successful observations
        canon = json.dumps({"tool": name, "value": res.value}, sort_keys=True,
                           default=str)
        if res.ok and canon in self._obs_seen:
            return {"tool": name, "ok": True,
                    "value": {"note": "(repeat observation; see earlier step)"}}
        if res.ok:
            self._obs_seen[canon] = "1"
        # trim long string payloads
        if isinstance(obs.get("value"), str) and len(obs["value"]) > 2000:
            obs["value"] = obs["value"][:2000] + "…[trimmed]"
        return obs

    # ------------------------------------------------------------------ util
    def _match_fault(self, name: str) -> dict[str, Any] | None:
        """Consume scheduled faults: {tool, occurrence, error, kind}."""
        count = self._fault_counters.get(name, 0) + 1
        self._fault_counters[name] = count
        for fault in self._case.faults:
            if fault.get("tool") == name and int(fault.get("occurrence", 1)) == count:
                return fault
        return None
