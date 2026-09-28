"""The EXE identity must not follow a different checkout or mutable sidecar."""

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from irswitch import build_identity as identity

SHA = "a" * 40


def test_frozen_identity_uses_embedded_manifest_only(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "build-identity.json").write_text(json.dumps({"commit": SHA, "dirty": False}))
    (tmp_path / "build-info.json").write_text(json.dumps({"commit": "b" * 40, "dirty": True}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("EXE must not run Git"))
    assert identity.resolve_build_identity() == {
        "commit": SHA,
        "shortCommit": SHA[:7],
        "dirty": False,
        "source": "embedded",
    }
    (bundle / "build-identity.json").unlink()
    assert identity.resolve_build_identity()["source"] == "unknown"


@pytest.mark.parametrize(
    "body",
    [
        "[]",
        "{",
        '{"commit":"not-a-sha","dirty":false}',
        json.dumps({"commit": SHA, "dirty": "false"}),
    ],
)
def test_invalid_embedded_identity_is_unknown(tmp_path, monkeypatch, body):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "build-identity.json").write_text(body)
    assert identity.resolve_build_identity()["commit"] is None


def test_source_metadata_is_package_relative_and_startup_snapshot_is_stable(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").write_text("worktree marker")
    monkeypatch.setattr(identity, "__file__", str(root / "src/irswitch/build_identity.py"))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    calls = []

    def run(args, **kwargs):
        assert args[1:3] == ["-C", str(root)]
        assert kwargs["timeout"] == 2
        calls.append(args)
        return SimpleNamespace(stdout=SHA if "rev-parse" in args else " M src/irswitch/main.py")

    monkeypatch.setattr(subprocess, "run", run)
    snapshot = dict(identity.BUILD_IDENTITY)
    resolved = identity.resolve_build_identity()
    assert resolved["commit"] == SHA and resolved["dirty"] is True
    assert len(calls) == 2
    # Explicit re-probes cannot change the module's captured running identity.
    assert identity.BUILD_IDENTITY == snapshot
