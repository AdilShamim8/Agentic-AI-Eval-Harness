"""Execution controls: limits, permission policy, ablation profiles."""
from __future__ import annotations

from dataclasses import dataclass, field

from agent_eval_harness.core.errors import InfraError


@dataclass
class ExecutionLimits:
    max_steps: int = 12
    max_tool_calls: int = 16
    per_tool_timeout_ms: int = 1000
    total_timeout_ms: int = 15000
    max_retries_per_call: int = 2
    max_output_chars: int = 10_000
    max_state_bytes: int = 100_000
    max_args_chars: int = 4_000

    @classmethod
    def from_dict(cls, d: dict | None) -> "ExecutionLimits":
        if not d:
            return cls()
        valid = {f for f in cls.__dataclass_fields__}
        unknown = set(d) - valid
        if unknown:
            raise InfraError(f"unknown execution setting(s): {sorted(unknown)}")
        return cls(**{k: v for k, v in d.items() if k in valid})


@dataclass
class PermissionPolicy:
    allowed_tools: set[str] | None = None  # None = every registry tool
    denied_tools: set[str] = field(default_factory=set)
    forbidden_arg_keys: set[str] = field(default_factory=lambda: {
        "cmd", "command", "shell", "eval", "exec", "subprocess", "os", "code",
    })
    max_denials_before_violation: int = 3

    @classmethod
    def from_dict(cls, d: dict | None) -> "PermissionPolicy":
        if not d:
            return cls()
        allowed = d.get("allowed_tools")
        return cls(
            allowed_tools=set(allowed) if allowed is not None else None,
            denied_tools=set(d.get("denied_tools", [])),
            forbidden_arg_keys=set(d.get("forbidden_arg_keys", cls.forbidden_arg_keys
                                         if isinstance(cls.forbidden_arg_keys, set) else set())),
        )

    def check_tool(self, name: str) -> str:
        """Return denial reason ('' = allowed)."""
        if name in self.denied_tools:
            return f"tool '{name}' is denied by benchmark policy"
        if self.allowed_tools is not None and name not in self.allowed_tools:
            return f"tool '{name}' is not in the benchmark allowlist"
        return ""


@dataclass
class AblationProfile:
    """Which harness capabilities are active. The ablation experiment matrix
    toggles exactly these four flags."""
    name: str = "full"
    verification: bool = True
    retry: bool = True
    tool_validation: bool = True
    context_optimization: bool = True


ABLATION_PROFILES: dict[str, AblationProfile] = {
    "full": AblationProfile("full"),
    "no_verification": AblationProfile("no_verification", verification=False),
    "no_retry": AblationProfile("no_retry", retry=False),
    "no_tool_validation": AblationProfile("no_tool_validation", tool_validation=False),
    "no_context_optimization": AblationProfile(
        "no_context_optimization", context_optimization=False),
}


def get_ablation(name: str) -> AblationProfile:
    if name not in ABLATION_PROFILES:
        raise InfraError(
            f"unknown ablation profile '{name}' (available: {sorted(ABLATION_PROFILES)})")
    return ABLATION_PROFILES[name]
