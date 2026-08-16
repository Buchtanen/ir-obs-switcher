"""Tests for detached process restart helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from irswitch.util.process_restart import build_restart_command, spawn_detached_restart


def test_build_restart_command_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Python\python.exe")
    monkeypatch.setattr(sys, "argv", [r"C:\proj\src\irswitch\main.py", "--config", "old.ini"])

    cmd = build_restart_command(config_path=Path("config/config.ini"))
    assert cmd == [
        r"C:\Python\python.exe",
        r"C:\proj\src\irswitch\main.py",
        "--config",
        str(Path("config/config.ini")),
    ]


def test_build_restart_command_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\dist\irswitchd.exe")
    monkeypatch.setattr(sys, "argv", [r"C:\dist\irswitchd.exe", "--config", "old.ini"])

    cmd = build_restart_command(config_path=r"C:\dist\config\config.ini")
    assert cmd == [r"C:\dist\irswitchd.exe", "--config", r"C:\dist\config\config.ini"]


def test_build_restart_command_requires_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", sys.executable)
    monkeypatch.setattr(sys, "argv", ["main.py"])

    with pytest.raises(ValueError, match="--config"):
        build_restart_command()


def test_spawn_detached_restart_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", sys.executable)
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", "cfg.ini"])

    with patch("irswitch.util.process_restart.subprocess.Popen") as popen:
        popen.return_value = MagicMock()
        spawn_detached_restart(config_path="cfg.ini", backoff_seconds=0)

    popen.assert_called_once()
    args = popen.call_args.args[0]
    assert "--config" in args
    assert "cfg.ini" in args


def test_spawn_detached_restart_propagates_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", sys.executable)
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", "cfg.ini"])

    with patch(
        "irswitch.util.process_restart.subprocess.Popen",
        side_effect=OSError("spawn failed"),
    ):
        with pytest.raises(OSError, match="spawn failed"):
            spawn_detached_restart(config_path="cfg.ini", backoff_seconds=0)
