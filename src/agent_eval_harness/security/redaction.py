"""Secret redaction — applied at every export boundary (events, reports)."""
from __future__ import annotations

import re
from typing import Any

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer", re.compile(r"\b[Bb]earer\s+[A-Za-z0-9._\-]{16,}\b")),
    ("secret_assignment", re.compile(
        r"(?i)\b(api[_-]?key|apikey|secret|password|passwd|token|access[_-]?key)\b"
        r'["\']?\s*[:=]\s*["\']?([A-Za-z0-9_\-./+=]{12,})["\']?')),
    ("private_env", re.compile(
        r"(?i)\b[A-Z0-9_]{4,}(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*=\s*\S{8,}")),
]


def scrub_text(text: str) -> tuple[str, int]:
    """Replace secret-like substrings. Returns (clean_text, redaction_count)."""
    if not isinstance(text, str):
        return ("" if text is None else str(text)), 0
    count = 0
    for kind, pattern in PATTERNS:
        def _sub(m: re.Match[str], _kind: str = kind) -> str:
            return f"[REDACTED:{_kind}]"

        new = pattern.sub(_sub, text)
        count += len(pattern.findall(text))
        text = new
    return text, count


def redact_payload(obj: Any) -> tuple[Any, int]:
    """Recursively redact strings inside dicts/lists/tuples."""
    total = 0
    if isinstance(obj, str):
        clean, total = scrub_text(obj)
        return clean, total
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            ck, n1 = scrub_text(str(k)) if isinstance(k, str) else (k, 0)
            cv, n2 = redact_payload(v)
            total += n1 + n2
            out[ck] = cv
        return out, total
    if isinstance(obj, (list, tuple, set, frozenset)):
        items = []
        for v in obj:
            cv, n = redact_payload(v)
            total += n
            items.append(cv)
        if isinstance(obj, list):
            return items, total
        if isinstance(obj, tuple):
            return tuple(items), total
        if isinstance(obj, set):
            return set(items), total
        return frozenset(items), total
    return obj, 0
