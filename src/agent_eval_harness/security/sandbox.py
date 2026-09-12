"""Runtime sandbox guards.

v0.1 boundary (documented in THREAT-MODEL.md): built-in tools are offline by
construction; the network guard blocks ANY socket creation during a run;
subprocess is not imported by any harness module (statically verified by
tests/security/test_static_imports.py). Arbitrary user-supplied agent code
runs in-process and is therefore OUTSIDE the sandbox boundary — documented.
"""
from __future__ import annotations

import socket
from contextlib import contextmanager

from agent_eval_harness.core.errors import SecurityViolation


class NetworkGuard:
    """Blocks socket creation while active; records attempts."""

    def __init__(self) -> None:
        self.attempts: list[str] = []
        self._orig_socket: type | None = None

    def _blocked(self, *args, **kwargs):  # pragma: no cover - only on violation
        peer = repr(args[:1]) if args else "?"
        self.attempts.append(f"socket({peer})")
        raise SecurityViolation(
            "network access is disabled inside the evaluation sandbox")

    def __enter__(self) -> "NetworkGuard":
        self._orig_socket = socket.socket
        socket.socket = self._blocked  # type: ignore[assignment]
        return self

    def __exit__(self, *exc) -> None:
        if self._orig_socket is not None:
            socket.socket = self._orig_socket  # type: ignore[assignment]


@contextmanager
def network_sandbox():
    guard = NetworkGuard()
    guard.__enter__()
    try:
        yield guard
    finally:
        guard.__exit__(None, None, None)
