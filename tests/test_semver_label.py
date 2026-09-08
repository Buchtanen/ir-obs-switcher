"""PR semver-label policy, including the open-then-label race wait."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_semver_label.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_semver_label", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sem = _load()


def test_release_pr_is_exempt() -> None:
    sem.evaluate_semver_policy(
        ["autorelease: pending"],
        title="chore(master): release 1.4.0",
        body="",
    )


def test_exactly_one_allowed_label_passes() -> None:
    sem.evaluate_semver_policy(["semver:none"], title="chore: docs", body="")
    sem.evaluate_semver_policy(["bug", "semver:patch"], title="fix: timeout", body="")
    sem.evaluate_semver_policy(["semver:minor"], title="feat: overlay", body="")
    sem.evaluate_semver_policy(
        ["semver:major"],
        title="feat!: drop TUI",
        body="",
    )


def test_zero_labels_fails() -> None:
    with pytest.raises(sem.SemverLabelError, match="exactly one semver label"):
        sem.evaluate_semver_policy([], title="chore: x", body="")


def test_two_semver_labels_fail() -> None:
    with pytest.raises(sem.SemverLabelError, match="exactly one"):
        sem.evaluate_semver_policy(
            ["semver:none", "semver:patch"],
            title="fix: x",
            body="",
        )


def test_unknown_semver_label_fails() -> None:
    with pytest.raises(sem.SemverLabelError, match="Unknown"):
        sem.evaluate_semver_policy(["semver:whatever"], title="chore: x", body="")


def test_major_without_breaking_marker_fails() -> None:
    with pytest.raises(sem.SemverLabelError, match="breaking"):
        sem.evaluate_semver_policy(["semver:major"], title="feat: x", body="")


def test_major_with_breaking_change_body_passes() -> None:
    sem.evaluate_semver_policy(
        ["semver:major"],
        title="feat: x",
        body="BREAKING CHANGE: no TUI",
    )


def test_none_conflicts_with_feat_title() -> None:
    with pytest.raises(sem.SemverLabelError, match="conflicts"):
        sem.evaluate_semver_policy(["semver:none"], title="feat: x", body="")


def test_none_conflicts_with_fix_title() -> None:
    with pytest.raises(sem.SemverLabelError, match="conflicts"):
        sem.evaluate_semver_policy(["semver:none"], title="fix(obs): x", body="")


def test_should_wait_only_on_open_without_semver() -> None:
    assert sem.should_wait_for_labels("opened", []) is True
    assert sem.should_wait_for_labels("reopened", ["bug"]) is True
    assert sem.should_wait_for_labels("opened", ["semver:none"]) is False
    assert sem.should_wait_for_labels("opened", ["autorelease: pending"]) is False
    assert sem.should_wait_for_labels("synchronize", []) is False
    assert sem.should_wait_for_labels("labeled", []) is False
    assert sem.should_wait_for_labels("unlabeled", ["bug"]) is False
    assert sem.should_wait_for_labels("edited", []) is False


def test_wait_returns_when_label_arrives() -> None:
    fetches = iter(
        [
            [],
            [],
            ["semver:none"],
        ]
    )
    clock = {"t": 0.0}

    def monotonic() -> float:
        return clock["t"]

    def sleep(seconds: float) -> None:
        clock["t"] += seconds

    labels = sem.wait_for_semver_labels(
        lambda: next(fetches),
        timeout_s=60.0,
        interval_s=3.0,
        sleep=sleep,
        monotonic=monotonic,
    )
    assert labels == ["semver:none"]
    assert clock["t"] == 6.0


def test_wait_stops_at_timeout_still_empty() -> None:
    clock = {"t": 0.0}

    def monotonic() -> float:
        return clock["t"]

    def sleep(seconds: float) -> None:
        clock["t"] += seconds

    labels = sem.wait_for_semver_labels(
        lambda: [],
        timeout_s=9.0,
        interval_s=3.0,
        sleep=sleep,
        monotonic=monotonic,
    )
    assert labels == []
    assert clock["t"] >= 9.0


def test_script_opened_event_waits_then_passes(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "action": "opened",
                "pull_request": {
                    "number": 286,
                    "title": "chore: pin flow defaults",
                    "body": "",
                    "labels": [],
                },
            }
        ),
        encoding="utf-8",
    )
    fetches = iter([[], ["semver:none"]])

    def fetch(_owner: str, _repo: str, _number: int) -> list[str]:
        return next(fetches)

    assert (
        sem.run_from_event(
            event,
            fetch_labels=fetch,
            repository="Buchtanen/ir-obs-switcher",
            timeout_s=60.0,
            interval_s=0.0,
            sleep=lambda _s: None,
            monotonic=lambda: 0.0,
        )
        == 0
    )


def test_script_exits_nonzero_without_label(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "action": "synchronize",
                "pull_request": {
                    "number": 1,
                    "title": "chore: x",
                    "body": "",
                    "labels": [],
                },
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--github-event",
            str(event),
            "--no-fetch",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "exactly one semver label" in proc.stderr
