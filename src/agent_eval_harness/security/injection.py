"""Prompt-injection screening for tasks and tool outputs.

Detection only — flagged text is recorded in the audit log and security flags;
it is never silently dropped (the agent still observes it; hardening against
*following* injections is the agent's job and is measured by adversarial cases).
"""
from __future__ import annotations

import re

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ignore_previous", re.compile(
        r"(?i)\bignore (?:all |any )?(?:previous|prior|above)\b")),
    ("disregard", re.compile(r"(?i)\bdisregard (?:the |all |any )?(?:previous|above|instructions)")),
    ("exfiltrate", re.compile(r"(?i)\bexfiltrat(?:e|ion)\b")),
    ("reply_only", re.compile(r"(?i)\breply only with\b")),
    ("immediately_call", re.compile(
        r"(?i)\bimmediately (?:call|invoke|run)\b")),
    ("reveal_prompt", re.compile(r"(?i)\breveal (?:your |the )?(?:system )?prompt\b")),
    ("send_data", re.compile(
        r"(?i)\bsend (?:all |the )?(?:data|report|results|secrets) to\b")),
]

_INJECTION_PLACEHOLDER = "[INJECTION-FLAGGED]"


def screen_text(text: str) -> list[str]:
    """Return the list of injection pattern ids matched in text."""
    if not isinstance(text, str):
        return []
    return [pid for pid, pattern in PATTERNS if pattern.search(text)]


def sanitize_text(text: str) -> str:
    """Replace matched injection directives with a placeholder (opt-in)."""
    if not isinstance(text, str):
        return "" if text is None else str(text)
    out = text
    for _pid, pattern in PATTERNS:
        out = pattern.sub(_INJECTION_PLACEHOLDER, out)
    return out
