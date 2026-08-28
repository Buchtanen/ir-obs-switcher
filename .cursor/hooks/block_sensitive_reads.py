#!/usr/bin/env python3
"""
Cursor hook: beforeReadFile

Goal: avoid leaking sensitive files into the model context.
Behavior:
- Deny reading common secret/config files (fail-safe for this repo).
- Allow everything else.

IMPORTANT: Keep this script stdlib-only and always print valid JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _allow() -> dict:
    return {"permission": "allow"}


def _deny(message: str) -> dict:
    return {"permission": "deny", "user_message": message}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # If input is malformed, don't block development.
        # Note: if the hook itself fails to execute, Cursor will block (fail-closed),
        # so we keep this path permissive.
        print(json.dumps(_allow()))
        return

    raw_path = (payload or {}).get("file_path") or ""
    path = Path(str(raw_path))
    normalized = str(path).replace("\\", "/").lower()

    # Repo-specific: user config contains credentials (OBS websocket password, OAuth, etc).
    deny_exact = {
        "config/config.ini",
        "dist/config/config.ini",
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
    }
    if any(normalized.endswith(suffix) for suffix in deny_exact):
        print(
            json.dumps(
                _deny(
                    "Blocked reading a potentially sensitive config/env file "
                    f"(`{path.name}`). If you really need it, paste only the minimal "
                    "non-secret snippet manually."
                )
            )
        )
        return

    # Generic secrets & private keys.
    deny_substrings = [
        "/.ssh/",
        "id_rsa",
        "id_ed25519",
        ".pem",
        ".p12",
        ".pfx",
        ".key",
        "credentials.json",
        "token",
        "secrets",
        "private_key",
    ]
    if any(s in normalized for s in deny_substrings):
        print(
            json.dumps(
                _deny(
                    "Blocked reading a file that looks like it may contain secrets/keys. "
                    "If you need to share something, redact it first."
                )
            )
        )
        return

    print(json.dumps(_allow()))


if __name__ == "__main__":
    main()
