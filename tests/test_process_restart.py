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


def test_build_restart_command_console_scripts_exe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """pip Windows shim: argv[0] is irswitchd.exe, executable is python.exe."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    shim = tmp_path / "irswitchd.exe"
    shim.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "argv", [str(shim), "--config", "old.ini"])

    cmd = build_restart_command(config_path=str(tmp_path / "config.ini"))
    assert cmd == [str(shim.resolve()), "--config", str(tmp_path / "config.ini")]
    assert not cmd[0].lower().endswith("python.exe")


def test_build_restart_command_console_scripts_bare_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """argv[0] may omit .exe; still re-exec the real shim PE."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    bare = tmp_path / "irswitchd"
    shim = tmp_path / "irswitchd.exe"
    shim.write_bytes(b"MZ")  # exists as file; content irrelevant for builder
    monkeypatch.setattr(sys, "argv", [str(bare), "--config", "old.ini"])

    cmd = build_restart_command(config_path=str(tmp_path / "config.ini"))
    assert cmd == [str(shim.resolve()), "--config", str(tmp_path / "config.ini")]
    assert cmd[0].endswith("irswitchd.exe")


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
    env = popen.call_args.kwargs.get("env") or {}
    assert env.get("IRSWITCH_RESTARTING") == "1"


def test_spawn_detached_restart_uses_python_sleep_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POSIX may delay via sleep+execv; Windows spawns the real command immediately."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", sys.executable)
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", "cfg.ini"])

    with patch("irswitch.util.process_restart.subprocess.Popen") as popen:
        popen.return_value = MagicMock()
        spawn_detached_restart(config_path="cfg.ini", backoff_seconds=2.5)

    args = popen.call_args.args[0]
    if sys.platform == "win32":
        assert args[0] == sys.executable
        assert "--config" in args
        assert "cfg.ini" in args
        assert "-c" not in args
    else:
        assert args[0] == sys.executable
        assert args[1] == "-c"
        assert "time.sleep" in args[2]
        assert "os.execv" in args[2]
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
