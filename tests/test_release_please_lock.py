"""Lockstep between pyproject.toml and .release-please-manifest.json."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_release_please_lock.py"


def _load_lock():
    spec = importlib.util.spec_from_file_location("check_release_please_lock", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lock = _load_lock()


def _write_pair(root: Path, py_ver: str, mf_ver: str) -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "irswitch"\nversion = "{py_ver}"\n',
        encoding="utf-8",
    )
    (root / ".release-please-manifest.json").write_text(
        json.dumps({".": mf_ver}) + "\n",
        encoding="utf-8",
    )


def test_checkout_pyproject_matches_manifest() -> None:
    py, mf = lock.check_lockstep(ROOT)
    assert py == mf
    assert py  # non-empty


def test_lockstep_mismatch_raises(tmp_path: Path) -> None:
    _write_pair(tmp_path, "1.3.0", "1.1.0")
    with pytest.raises(lock.ReleasePleaseLockError, match="1.3.0"):
        lock.check_lockstep(tmp_path)


def test_script_exits_nonzero_on_drift(tmp_path: Path) -> None:
    _write_pair(tmp_path, "1.3.0", "1.1.0")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "1.3.0" in proc.stderr
    assert "1.1.0" in proc.stderr


def test_script_ok_on_checkout() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(ROOT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "lockstep ok" in proc.stdout


def test_github_event_allows_release_pr_bump(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"sha": "deadbeef"},
                    "labels": [{"name": "autorelease: pending"}],
                }
            }
        ),
        encoding="utf-8",
    )
    labels = lock.labels_from_github_event(event)
    assert "autorelease: pending" in labels
    assert lock.base_sha_from_github_event(event) == "deadbeef"

    _write_pair(tmp_path, "1.4.0", "1.4.0")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--github-event", str(event)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "lockstep ok" in proc.stdout


def test_no_pyproject_bump_vs_git_base(tmp_path: Path) -> None:
    subprocess.check_call(["git", "init"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.name", "test"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path)
    _write_pair(tmp_path, "1.2.0", "1.2.0")
    subprocess.check_call(
        ["git", "add", "pyproject.toml", ".release-please-manifest.json"], cwd=tmp_path
    )
    subprocess.check_call(["git", "commit", "-m", "base"], cwd=tmp_path)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()

    lock.check_no_pyproject_bump(tmp_path, base)

    _write_pair(tmp_path, "1.3.0", "1.3.0")
    with pytest.raises(lock.ReleasePleaseLockError, match="1.2.0 -> 1.3.0"):
        lock.check_no_pyproject_bump(tmp_path, base)

    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"sha": base},
                    "labels": [{"name": "semver:none"}],
                }
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--github-event", str(event)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1, proc.stdout
    assert "Do not bump project.version" in proc.stderr

    _write_pair(tmp_path, "1.2.0", "1.2.0")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--github-event", str(event)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "unchanged" in proc.stdout


def test_pr_policy_and_release_please_invoke_lock_script() -> None:
    pr_policy = (ROOT / ".github" / "workflows" / "pr-policy.yml").read_text(encoding="utf-8")
    rp = (ROOT / ".github" / "workflows" / "release-please.yml").read_text(encoding="utf-8")
    assert "scripts/check_release_please_lock.py" in pr_policy
    assert "scripts/check_release_please_lock.py" in rp
