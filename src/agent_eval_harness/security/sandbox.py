"""Runtime sandbox guards.

Boundary contract (v0.2, see THREAT-MODEL.md):
- The network guard blocks ANY new socket creation while active. It is
  installed for the whole run by the benchmark runner.
- The runner lifts the block ONLY for the evaluator phase (`guard.allowed()`)
  — trusted harness code — so a live LLM judge can perform its AUTHORIZED
  HTTP evaluation while arbitrary agent code stays blocked at every other
  point in the run. The lift is explicit, narrow, and per-phase.
- Built-in tools are offline by construction; subprocess is not imported by
  any harness module (statically verified by tests/security tests).
- Arbitrary user-supplied agent code runs in-process and is therefore OUTSIDE
  an operating-system boundary — documented: the guard is a best-effort
  in-process control (it cannot constrain ctypes/os-level tricks), not OS
  isolation.
"""

from __future__ import annotations

import socket
from contextlib import contextmanager
from typing import Iterator

from agent_eval_harness.core.errors import SecurityViolation


class NetworkGuard:
    """Blocks new socket creation while active; records attempts."""

    def __init__(self) -> None:
        self.attempts: list[str] = []
        self._orig_socket: type | None = None

    def _blocked(self, *args, **kwargs):  # pragma: no cover - only on violation
        if kwargs.get("fileno") is not None and self._orig_socket is not None:
            # Wrapping an EXISTING fd (http.server accept() does exactly this)
            # creates no new connection — allow the wrap so servers accepting
            # traffic keep working during a guarded run. Creating a connection
            # (no fileno) stays blocked. In-process code could wrap an fd it
            # already owns anyway; this is documented as best-effort.
            return self._orig_socket(*args, **kwargs)
        peer = repr(args[:1]) if args else "?"
        self.attempts.append(f"socket({peer})")
        raise SecurityViolation("network access is disabled inside the evaluation sandbox")

    def __enter__(self) -> "NetworkGuard":
        if self._orig_socket is None:
            self._orig_socket = socket.socket
        socket.socket = self._blocked  # type: ignore[assignment,misc]
        return self

    def __exit__(self, *exc) -> None:
        if self._orig_socket is not None:
            socket.socket = self._orig_socket  # type: ignore[assignment,misc]
        self._orig_socket = None

    @contextmanager
    def allowed(self) -> Iterator[None]:
        """Temporarily lift the network block — for TRUSTED harness code only.

        The benchmark runner uses this for the evaluator phase so a live
        LLM judge can reach its operator-configured endpoint (authorized
        HTTP evaluation) while arbitrary agent code remains blocked at every
        other point in the run. Restores the blocked state afterwards.
        """
        prev = socket.socket
        if self._orig_socket is not None:
            socket.socket = self._orig_socket  # type: ignore[assignment,misc]
        try:
            yield
        finally:
            socket.socket = prev  # type: ignore[assignment,misc]


@contextmanager
def network_sandbox():
    guard = NetworkGuard()
    guard.__enter__()
    try:
        yield guard
    finally:
        guard.__exit__(None, None, None)
