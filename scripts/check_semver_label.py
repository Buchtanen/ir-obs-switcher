#!/usr/bin/env python3
"""Enforce exactly one semver:* label on PRs to master.

The pull_request event payload is a snapshot. Agents open the PR and add the
label a moment later, so `opened` often sees zero labels. On opened/reopened
with no semver:* yet, refetch labels from the API until one appears or timeout.

Label remains authoritative — this script never applies labels.

Exit 0 on pass, 1 on policy failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

ALLOWED_SEMVER = frozenset({"semver:major", "semver:minor", "semver:patch", "semver:none"})
WAIT_ACTIONS = frozenset({"opened", "reopened"})
_FEAT = re.compile(r"^feat(\([^)]+\))?!?:", re.IGNORECASE)
_FIX = re.compile(r"^fix(\([^)]+\))?!?:", re.IGNORECASE)


class SemverLabelError(Exception):
    """PR does not satisfy the semver label policy."""


def semver_names(labels: list[str]) -> list[str]:
    return [name for name in labels if name.startswith("semver:")]


def should_wait_for_labels(action: str, labels: list[str]) -> bool:
    if action not in WAIT_ACTIONS:
        return False
    if "autorelease: pending" in labels:
        return False
    return not semver_names(labels)


def evaluate_semver_policy(labels: list[str], *, title: str, body: str) -> None:
    if "autorelease: pending" in labels:
        return

    found = semver_names(labels)
    unknown = [name for name in found if name not in ALLOWED_SEMVER]
    if unknown:
        allowed = ", ".join(sorted(ALLOWED_SEMVER))
        raise SemverLabelError(f"Unknown semver label(s): {', '.join(unknown)}. Allowed: {allowed}")

    if len(found) != 1:
        joined = ", ".join(found) or "none"
        raise SemverLabelError(
            f"PR must have exactly one semver label. Found: {len(found)} ({joined})."
        )

    semver = found[0]
    title = (title or "").strip()
    body = (body or "").strip()
    is_breaking = ("!:" in title) or ("BREAKING CHANGE:" in body)
    is_feat = bool(_FEAT.match(title))
    is_fix = bool(_FIX.match(title))

    if semver == "semver:major" and not is_breaking:
        raise SemverLabelError(
            "semver:major requires explicit breaking change marker: "
            "use '!: ' in title or add 'BREAKING CHANGE:' in PR body."
        )

    if semver == "semver:none" and (is_feat or is_fix or is_breaking):
        raise SemverLabelError(
            "semver:none conflicts with a feat/fix/breaking PR title/body. "
            "Use semver:patch/minor/major or adjust the PR title/body."
        )

    if semver == "semver:minor" and not is_feat and not is_breaking:
        print(
            "warning: semver:minor is set, but PR title doesn't look like 'feat:'. "
            "This is allowed, but consider aligning for better changelog.",
            file=sys.stderr,
        )
    if semver == "semver:patch" and not is_fix and not is_breaking:
        print(
            "warning: semver:patch is set, but PR title doesn't look like 'fix:'. "
            "This is allowed, but consider aligning for better changelog.",
            file=sys.stderr,
        )


def wait_for_semver_labels(
    fetch: Callable[[], list[str]],
    *,
    timeout_s: float = 60.0,
    interval_s: float = 3.0,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> list[str]:
    deadline = monotonic() + timeout_s
    while True:
        labels = fetch()
        if semver_names(labels) or "autorelease: pending" in labels:
            return labels
        if monotonic() >= deadline:
            return labels
        sleep(interval_s)


def labels_from_event_pr(pr: dict) -> list[str]:
    return [str(item.get("name") or "") for item in (pr.get("labels") or [])]


def fetch_issue_labels(
    owner: str,
    repo: str,
    number: int,
    *,
    token: str,
    api_url: str,
) -> list[str]:
    base = api_url.rstrip("/")
    url = f"{base}/repos/{owner}/{repo}/issues/{number}/labels"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "irswitch-semver-label",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SemverLabelError(
            f"cannot list labels for {owner}/{repo}#{number}: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SemverLabelError(
            f"cannot list labels for {owner}/{repo}#{number}: {exc.reason}"
        ) from exc
    if not isinstance(payload, list):
        raise SemverLabelError(f"unexpected labels payload for #{number}")
    return [str(item.get("name") or "") for item in payload]


def _split_repository(repository: str) -> tuple[str, str]:
    owner, _, repo = repository.partition("/")
    if not owner or not repo:
        raise SemverLabelError(f"invalid repository {repository!r}")
    return owner, repo


def run_from_event(
    event_path: Path,
    *,
    fetch_labels: Callable[[str, str, int], list[str]] | None = None,
    repository: str | None = None,
    timeout_s: float = 60.0,
    interval_s: float = 3.0,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    pr = event.get("pull_request") or {}
    action = str(event.get("action") or "")
    title = str(pr.get("title") or "")
    body = str(pr.get("body") or "")
    labels = labels_from_event_pr(pr)
    repo_full = (
        repository
        or os.environ.get("GITHUB_REPOSITORY")
        or str((event.get("repository") or {}).get("full_name") or "")
    )

    def _fetch() -> list[str]:
        if fetch_labels is None:
            return labels
        owner, repo = _split_repository(repo_full)
        number = int(pr.get("number") or 0)
        if number <= 0:
            raise SemverLabelError("GitHub event is missing pull_request.number")
        return fetch_labels(owner, repo, number)

    try:
        if should_wait_for_labels(action, labels) and fetch_labels is not None:
            print(
                f"opened/reopened with no semver:* yet; waiting up to {timeout_s:.0f}s",
                flush=True,
            )
            labels = wait_for_semver_labels(
                _fetch,
                timeout_s=timeout_s,
                interval_s=interval_s,
                sleep=sleep,
                monotonic=monotonic,
            )
        elif fetch_labels is not None:
            labels = _fetch()
        evaluate_semver_policy(labels, title=title, body=body)
    except SemverLabelError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    found = semver_names(labels)
    if "autorelease: pending" in labels:
        print("Release PR detected (autorelease: pending). Skipping semver label.")
    else:
        print(f"semver-label ok: {found[0]}")
    return 0


def _http_fetch(owner: str, repo: str, number: int) -> list[str]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token:
        raise SemverLabelError("GITHUB_TOKEN is required to refetch PR labels")
    api_url = os.environ.get("GITHUB_API_URL") or "https://api.github.com"
    return fetch_issue_labels(owner, repo, number, token=token, api_url=api_url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-event", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Use event payload only (tests / no network)",
    )
    args = parser.parse_args(argv)
    fetch: Callable[[str, str, int], list[str]] | None
    fetch = None if args.no_fetch else _http_fetch
    if fetch is not None and not (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")):
        fetch = None
    return run_from_event(
        args.github_event,
        fetch_labels=fetch,
        timeout_s=args.timeout,
        interval_s=args.interval,
    )


if __name__ == "__main__":
    raise SystemExit(main())
