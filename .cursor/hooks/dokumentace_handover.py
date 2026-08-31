#!/usr/bin/env python3
"""
Cursor hook: stop (agent handover)

If src/irswitch (or tests/CI) changed in the worktree and the matching
docs/dokumentace page was not touched, nudge the agent once per fingerprint.

Never fail-closed. Stdlib-only. Always print valid JSON.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

DOMAIN_BY_PREFIX: tuple[tuple[str, str], ...] = (
    ("src/irswitch/iracing/", "docs/dokumentace/domeny/iracing.md"),
    ("src/irswitch/obs/", "docs/dokumentace/domeny/obs.md"),
    ("src/irswitch/logic/", "docs/dokumentace/domeny/logic.md"),
    ("src/irswitch/server/", "docs/dokumentace/domeny/server.md"),
    ("src/irswitch/overlay/", "docs/dokumentace/domeny/overlay.md"),
    ("src/irswitch/events/", "docs/dokumentace/domeny/events.md"),
    ("src/irswitch/commentary/", "docs/dokumentace/domeny/commentary.md"),
    ("src/irswitch/race/", "docs/dokumentace/domeny/race.md"),
    ("src/irswitch/sampling/", "docs/dokumentace/domeny/sampling.md"),
    ("src/irswitch/bio/", "docs/dokumentace/domeny/bio.md"),
    ("src/irswitch/system/", "docs/dokumentace/domeny/system.md"),
    ("src/irswitch/util/", "docs/dokumentace/domeny/util.md"),
    ("src/irswitch/web/", "docs/dokumentace/domeny/web.md"),
)

FILE_TO_DOC: dict[str, str] = {
    "src/irswitch/main.py": "docs/dokumentace/domeny/runtime.md",
    "src/irswitch/models.py": "docs/dokumentace/domeny/runtime.md",
    "src/irswitch/config.py": "docs/dokumentace/domeny/config.md",
    "src/irswitch/config_reload.py": "docs/dokumentace/domeny/config.md",
    "src/irswitch/i18n.py": "docs/dokumentace/domeny/i18n.md",
    "src/irswitch/oauth.py": "docs/dokumentace/domeny/oauth-youtube.md",
}


def _ok() -> dict:
    return {}


def _repo_root() -> Path | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return Path(out.strip())
    except Exception:
        return None


def _changed_files(root: Path) -> set[str]:
    names: set[str] = set()
    cmds = (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    for cmd in cmds:
        try:
            out = subprocess.check_output(cmd, cwd=root, stderr=subprocess.DEVNULL, text=True)
        except Exception:
            continue
        for line in out.splitlines():
            path = line.strip().replace("\\", "/")
            if path:
                names.add(path)
    return names


def _needed_docs(changed: set[str]) -> list[str]:
    needed: set[str] = set()
    for path in changed:
        if path in FILE_TO_DOC:
            needed.add(FILE_TO_DOC[path])
            continue
        for prefix, doc in DOMAIN_BY_PREFIX:
            if path.startswith(prefix):
                needed.add(doc)
                break
        else:
            if path.startswith("tests/") or path.startswith(".github/"):
                needed.add("docs/dokumentace/domeny/testy-ci.md")
    return sorted(needed)


def _nudge_once(root: Path, fingerprint: str) -> bool:
    stamp = root / ".git" / "cursor-dokumentace-nudge"
    try:
        if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == fingerprint:
            return False
        stamp.write_text(fingerprint + "\n", encoding="utf-8")
    except Exception:
        return True
    return True


def main() -> None:
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    root = _repo_root()
    if root is None:
        print(json.dumps(_ok()))
        return

    changed = _changed_files(root)
    if not changed:
        print(json.dumps(_ok()))
        return

    if any(p.startswith("docs/dokumentace/") for p in changed):
        print(json.dumps(_ok()))
        return

    missing = [doc for doc in _needed_docs(changed) if doc not in changed]
    if not missing:
        print(json.dumps(_ok()))
        return

    fingerprint = hashlib.sha256("\n".join(sorted(changed)).encode("utf-8")).hexdigest()
    if not _nudge_once(root, fingerprint):
        print(json.dumps(_ok()))
        return

    pages = ", ".join(f"`{p}`" for p in missing)
    msg = (
        "Handover: `src/`/`tests/`/`CI` se změnily, ale `docs/dokumentace/` v diffu chybí. "
        f"Doplň {pages} (nebo napiš `Docs: no change (reason …)` do PR). "
        "Mapa: `.cursor/rules/docs-map.mdc`. Skill: `dokumentace`."
    )
    print(json.dumps({"followup_message": msg}))


if __name__ == "__main__":
    main()
