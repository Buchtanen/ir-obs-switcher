#!/usr/bin/env python3
"""
Cursor hook: beforeShellExecution

Goal:
- Deny obviously destructive commands.
- Ask confirmation for "risky but sometimes needed" commands (installs, git push, etc).
- Allow common read-only / quality gate commands.

IMPORTANT: stdlib-only; always print valid JSON.
"""

from __future__ import annotations

import json
import re
import sys


def _resp(
    permission: str, user_message: str | None = None, agent_message: str | None = None
) -> dict:
    out: dict = {"continue": True, "permission": permission}
    if user_message:
        out["user_message"] = user_message
    if agent_message:
        out["agent_message"] = agent_message
    return out


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print(json.dumps(_resp("allow")))
        return

    command = str((payload or {}).get("command") or "")
    cmd = command.strip()
    low = cmd.lower()

    if not cmd:
        print(json.dumps(_resp("allow")))
        return

    # Hard-deny: destructive / irreversible.
    deny_patterns = [
        r"\bgit\s+push\b.*\s--force\b",
        r"\bgit\s+reset\b.*\s--hard\b",
        r"\bgit\s+clean\b.*\s-[^\n]*f",
        r"\brm\s+-rf\b",
        r"\brmdir\b.*\s/s\b",
        r"\b(del|erase)\b.*\s/s\b",
        r"\bformat\b\s+[a-z]:",
        r"\bshutdown\b",
        r"\breboot\b",
    ]
    if any(re.search(p, low) for p in deny_patterns):
        print(
            json.dumps(
                _resp(
                    "deny",
                    user_message="Blocked a destructive shell command (unsafe).",
                    agent_message=f"Command blocked by policy: `{cmd}`",
                )
            )
        )
        return

    # Ask: repo/network/tooling changes.
    ask_patterns = [
        r"\bgit\s+push\b",
        r"\bgit\s+commit\b",
        r"\bpip\s+install\b",
        r"\bpython\s+-m\s+pip\s+install\b",
        r"\buv\s+pip\s+install\b",
        r"\bpoetry\s+add\b",
        r"\bnpm\s+install\b",
        r"\byarn\s+add\b",
        r"\bpnpm\s+add\b",
    ]
    if any(re.search(p, low) for p in ask_patterns):
        print(
            json.dumps(
                _resp(
                    "ask",
                    user_message="Shell command may modify repo/deps. Approve to continue.",
                    agent_message=f"Please approve running: `{cmd}`",
                )
            )
        )
        return

    # Allow: common quality gates / read-only.
    allow_patterns = [
        r"\bgit\s+(status|diff|log|show)\b",
        r"\bpython\s+-m\s+(pytest|ruff|black|mypy)\b",
        r"\bpytest\b",
        r"\bruff\b",
        r"\bblack\b",
        r"\bmypy\b",
    ]
    if any(re.search(p, low) for p in allow_patterns):
        print(json.dumps(_resp("allow")))
        return

    # Default: allow (avoid annoying prompts for harmless commands).
    print(json.dumps(_resp("allow")))


if __name__ == "__main__":
    main()
