"""Capture the running code's identity once, independently of the operator cwd."""

from __future__ import annotations

import json
import re
import shutil
import subprocess  # nosec B404 - bounded local Git metadata read, no shell
import sys
from pathlib import Path
from typing import Any


def resolve_build_identity() -> dict[str, Any]:
    unknown = {"commit": None, "shortCommit": None, "dirty": None, "source": "unknown"}
    try:
        if getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None):
            # An EXE must never borrow identity from an adjacent checkout/sidecar.
            bundle = getattr(sys, "_MEIPASS", None)
            if not bundle:
                return unknown
            path = Path(bundle) / "build-identity.json"
            if path.stat().st_size > 4096:
                return unknown
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            commit, dirty = data.get("commit"), data.get("dirty")
            source = "embedded"
        else:
            root = Path(__file__).resolve().parents[2]
            if not (root / ".git").exists():
                return unknown
            executable = shutil.which("git")
            if executable is None:
                return unknown

            def git(*args: str) -> str:
                return subprocess.run(  # nosec B603 - fixed Git subcommands, no user input
                    [executable, "-C", str(root), *args],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=2,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                ).stdout.strip()

            commit = git("rev-parse", "HEAD")
            dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
            source = "source"
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            return unknown
        if not isinstance(dirty, bool):
            return unknown
        return {"commit": commit, "shortCommit": commit[:7], "dirty": dirty, "source": source}
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        return unknown


# Startup snapshot: subsequent branch switches cannot relabel loaded code.
BUILD_IDENTITY = resolve_build_identity()
