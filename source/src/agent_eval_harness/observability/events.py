"""Structured observability events (JSONL, redacted at export).

Event lifecycle mirrors the platform's core flow:
benchmark -> case -> agent step -> tool call -> evaluator -> metric -> report.
Events are span-like (name, ts, ids, payload) so an OTLP exporter can be added
later without schema changes.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from agent_eval_harness.security.redaction import redact_payload


@dataclass
class Event:
    ts: float
    kind: str
    phase: str
    case_id: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": round(self.ts, 3),
            "kind": self.kind,
            "phase": self.phase,
            "case_id": self.case_id,
            "payload": self.payload,
        }


class EventRecorder:
    """Run-scoped, in-memory event stream with redacted JSONL export."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.events: list[Event] = []
        self._redaction_count = 0

    def emit(self, kind: str, payload: dict[str, Any], phase: str = "",
             case_id: str = "") -> None:
        self.events.append(Event(ts=time.time(), kind=kind, phase=phase,
                                 case_id=case_id, payload=dict(payload)))

    # -- queries -------------------------------------------------------------
    def by_kind(self, kind: str) -> list[Event]:
        return [e for e in self.events if e.kind == kind]

    def for_case(self, case_id: str) -> list[Event]:
        return [e for e in self.events if e.case_id == case_id]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.events:
            out[e.kind] = out.get(e.kind, 0) + 1
        return out

    # -- export ----------------------------------------------------------------
    def export_jsonl(self, path: str) -> dict[str, Any]:
        """Write redacted JSONL. Returns {events, redactions, path}."""
        lines = 0
        with open(path, "w", encoding="utf-8") as fh:
            for e in self.events:
                clean, n = redact_payload(e.to_dict())
                self._redaction_count += n
                fh.write(json.dumps(clean, sort_keys=True, default=str) + "\n")
                lines += 1
        return {"events": lines, "redactions": self._redaction_count, "path": path}
