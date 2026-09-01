#!/usr/bin/env python3
"""Guard: pyproject.toml and .release-please-manifest.json stay in lockstep.

Release Please treats .release-please-manifest.json as the last released version.
If pyproject.toml (or a git tag) moves without the manifest, the next Release PR
never opens.

Exit codes:
  0  lockstep (and, when asked, no unexpected pyproject bump)
  1  drift or unexpected version bump
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path


class ReleasePleaseLockError(Exception):
    """pyproject.toml and the Release Please manifest are not in lockstep."""


def pyproject_version(raw: bytes | str) -> str:
    data = tomllib.loads(raw if isinstance(raw, str) else raw.decode())
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version.strip():
        raise ReleasePleaseLockError("pyproject.toml is missing [project].version")
    return version.strip()


def manifest_version(raw: bytes | str) -> str:
    data = json.loads(raw if isinstance(raw, str) else raw.decode())
    version = data.get(".")
    if not isinstance(version, str) or not version.strip():
        raise ReleasePleaseLockError('.release-please-manifest.json is missing "." version')
    return version.strip()


def read_lockstep(root: Path) -> tuple[str, str]:
    py = pyproject_version((root / "pyproject.toml").read_bytes())
    mf = manifest_version((root / ".release-please-manifest.json").read_bytes())
    return py, mf


def check_lockstep(root: Path) -> tuple[str, str]:
    py, mf = read_lockstep(root)
    if py != mf:
        raise ReleasePleaseLockError(
            f"pyproject.toml version {py} != .release-please-manifest.json '.' {mf}. "
            "Bump both together in a Release PR, or open a semver:none PR that sets "
            "the manifest to the last released version (pyproject/tag) without "
            "changing pyproject."
        )
    return py, mf


def git_show(root: Path, sha: str, relpath: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{sha}:{relpath}"],
        cwd=root,
        stderr=subprocess.STDOUT,
    )


def check_no_pyproject_bump(root: Path, base_sha: str) -> None:
    head = pyproject_version((root / "pyproject.toml").read_bytes())
    try:
        base = pyproject_version(git_show(root, base_sha, "pyproject.toml"))
    except subprocess.CalledProcessError as exc:
        raise ReleasePleaseLockError(
            f"cannot read pyproject.toml at base {base_sha}: {exc}"
        ) from exc
    if head != base:
        raise ReleasePleaseLockError(
            f"Do not bump project.version in a normal PR ({base} -> {head}). "
            "Release Please bumps pyproject.toml and .release-please-manifest.json "
            "together. To unstick Release Please, change only the manifest so it "
            "matches pyproject/tag (semver:none)."
        )


def labels_from_github_event(event_path: Path) -> list[str]:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    pr = event.get("pull_request") or {}
    return [str(item.get("name") or "") for item in (pr.get("labels") or [])]


def base_sha_from_github_event(event_path: Path) -> str:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    pr = event.get("pull_request") or {}
    sha = (pr.get("base") or {}).get("sha")
    if not isinstance(sha, str) or not sha:
        raise ReleasePleaseLockError("GitHub event is missing pull_request.base.sha")
    return sha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--base-sha", help="Fail if [project].version changed vs this git SHA")
    parser.add_argument(
        "--allow-pyproject-bump",
        action="store_true",
        help="Skip the pyproject bump check (Release PRs with autorelease: pending)",
    )
    parser.add_argument(
        "--github-event",
        type=Path,
        help="PR event JSON; sets base SHA and allow-pyproject-bump from labels",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()

    allow_bump = bool(args.allow_pyproject_bump)
    base_sha = args.base_sha
    if args.github_event is not None:
        labels = labels_from_github_event(args.github_event)
        allow_bump = allow_bump or ("autorelease: pending" in labels)
        if base_sha is None:
            base_sha = base_sha_from_github_event(args.github_event)

    try:
        py, mf = check_lockstep(root)
        print(f"lockstep ok: pyproject={py} manifest={mf}")
        if base_sha and not allow_bump:
            check_no_pyproject_bump(root, base_sha)
            print(f"pyproject version unchanged vs {base_sha[:12]}")
    except ReleasePleaseLockError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
