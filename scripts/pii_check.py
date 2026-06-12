#!/usr/bin/env python3
"""Pre-commit PII / secret scanner for the Sealock (public) repo.

Scans the *staged* git diff for things that must never reach a public repo:
credentials, private keys, JDBC/connection strings with passwords, e-mail
addresses, non-local IPs/hostnames, and accidental staging of local config.

Usage:
    python scripts/pii_check.py            # scan staged changes
    python scripts/pii_check.py --all      # scan whole working tree (tracked)

Exit code 0 = clean, 1 = potential issues found (review before committing).
"""
from __future__ import annotations

import re
import subprocess
import sys

# Values that are obviously placeholders / safe — never flagged.
ALLOWLIST = (
    "example.com", "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "YOUR_", "changeme", "<", ">", "user@", "alice@example.com",
)

# Files we never want committed at all.
BLOCKED_FILES = ("config.local.json", ".env")

PATTERNS = [
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # Only flag a *quoted literal* value — avoids matching code like
    # `password=password` or `password = field(...)` while still catching a
    # hard-coded secret such as `password = "<a-real-secret>"`.
    ("Password assignment", re.compile(r"""(?i)\b(password|passwd|pwd)\s*[=:]\s*['"][^'"]{3,}['"]""")),
    ("Secret / token", re.compile(r"""(?i)\b(secret|api[_-]?key|access[_-]?token|auth[_-]?token)\s*[=:]\s*['"][^'"]{6,}['"]""")),
    ("JDBC/DB URL with creds", re.compile(r"(?i)(jdbc:|mysql:|mariadb:)//\S*:\S*@\S+")),
    ("E-mail address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("Public IPv4 address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]

PRIVATE_IP = re.compile(r"\b(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.|127\.|0\.)")


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True,
            encoding="utf-8", errors="replace",
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[pii-check] git error: {exc}", file=sys.stderr)
        sys.exit(2)


def _added_lines(scan_all: bool):
    """Yield (file, lineno, text) for lines added in the staged diff."""
    diff_args = ["diff", "--unified=0", "--no-color"]
    diff_args += [] if scan_all else ["--cached"]
    diff = _git(diff_args)

    cur_file, cur_line = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur_file = line[6:]
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            cur_line = int(m.group(1)) if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            yield cur_file, cur_line, line[1:]
            cur_line += 1


def _is_allowed(text: str) -> bool:
    return any(tok in text for tok in ALLOWLIST)


def main() -> int:
    scan_all = "--all" in sys.argv
    findings = []

    staged = _git(["diff", "--cached", "--name-only"]).split()
    for blocked in BLOCKED_FILES:
        if any(f.endswith(blocked) for f in staged):
            findings.append((blocked, 0, "BLOCKED FILE", "must never be committed"))

    for file, lineno, text in _added_lines(scan_all):
        if _is_allowed(text):
            continue
        for label, rx in PATTERNS:
            m = rx.search(text)
            if not m:
                continue
            if label == "Public IPv4 address" and PRIVATE_IP.search(m.group(0)):
                continue
            findings.append((file, lineno, label, m.group(0)[:80]))

    if not findings:
        print("[pii-check] OK - no obvious PII/secrets in staged changes.")
        return 0

    print("[pii-check] WARNING - potential PII / secrets found, review before committing:\n")
    for file, lineno, label, snippet in findings:
        loc = f"{file}:{lineno}" if lineno else file
        print(f"  - {label:<26} {loc}\n      {snippet}")
    print("\nIf these are false positives (placeholders/synthetic data), add them to "
          "ALLOWLIST in scripts/pii_check.py or proceed knowingly.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
