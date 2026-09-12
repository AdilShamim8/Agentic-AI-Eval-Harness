"""Repo-wide secret scanner — CI gate (--strict exits 1 on findings)."""
from __future__ import annotations

import argparse
import os
import re
import sys

PATTERNS = [
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("generic_assignment", re.compile(
        r"(?i)\b(api[_-]?key|secret|password|token)\b\s*[:=]\s*['\"][^'\"$\s]{12,}['\"]"
        r"(?!\s*#?\s*(example|placeholder|redacted|\$\{))")),
]

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "release",
             "release_validation"}
SKIP_FILES = {
    "scan_secrets.py",
    ".env.example",
    # intentional fake fixtures exercising the redaction engine:
    "test_security_basics.py",
}
ALLOWED_MARKERS = ("EXAMPLE", "REDACTED", "PLACEHOLDER", "<your", "${", "xxxxx",
                   "fixture")


def scan(root: str) -> list[tuple[str, int, str, str]]:
    findings: list[tuple[str, int, str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname in SKIP_FILES or not fname.endswith(
                    (".py", ".md", ".yaml", ".yml", ".json", ".jsonl", ".toml",
                     ".txt", ".example", ".mmd", ".cfg")):
                continue
            path = os.path.join(dirpath, fname)
            try:
                text = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for kind, pattern in PATTERNS:
                for m in pattern.finditer(text):
                    frag = m.group(0)
                    if any(marker in frag.upper() for marker in ALLOWED_MARKERS):
                        continue
                    line = text.count("\n", 0, m.start()) + 1
                    findings.append((path, line, kind, frag[:40]))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any finding is present")
    args = ap.parse_args()
    findings = scan(args.root)
    if findings:
        print(f"SECRET SCAN: {len(findings)} finding(s)")
        for path, line, kind, frag in findings[:30]:
            print(f"  {path}:{line} [{kind}] {frag}")
        return 1 if args.strict else 0
    print("SECRET SCAN: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
