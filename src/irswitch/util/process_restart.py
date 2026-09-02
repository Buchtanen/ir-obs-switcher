"""Detached process respawn helpers (Windows-first).

Used by POST /restart to spawn a successor process before graceful shutdown.
Spawn must succeed (Popen) before the parent shuts down; on failure the parent
keeps running (fail-closed).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Child sees this and may retry single-instance briefly while the parent exits.
# Primary handoff mechanism on Windows (sleep+execv launchers are fragile with
# console_scripts .exe shims + CREATE_NO_WINDOW).
RESTART_ENV_FLAG = "IRSWITCH_RESTARTING"

# Kept for API compatibility / optional posix delayed exec; Windows ignores delay
# and relies on IRSWITCH_RESTARTING port retry instead.
DEFAULT_PORT_BACKOFF_SECONDS = 0.0


def _extract_config_from_argv(argv: list[str]) -> str | None:
    """Return --config value from argv, if present."""
    for i, arg in enumerate(argv):
        if arg == "--config" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--config="):
            return arg.split("=", 1)[1]
    return None


def build_restart_command(*, config_path: str | Path | None = None) -> list[str]:
    """
    Build argv to respawn the current process with --config.

    Frozen (PyInstaller): ``irswitchd.exe --config <path>``
    pip console_scripts shim: ``irswitchd.exe --config <path>`` (do **not**
    pass the ``.exe`` as a script to ``python.exe`` — that fails on Windows)
    Dev module run: ``python -m irswitch.main --config <path>`` / ``python script.py``
    """
    cfg: str | None
    if config_path is not None:
        cfg = str(Path(config_path))
    else:
        cfg = _extract_config_from_argv(sys.argv)

    if not cfg:
        raise ValueError("Cannot build restart command: --config path is unknown")

    if getattr(sys, "frozen", False):
        return [sys.executable, "--config", cfg]

    script = sys.argv[0] if sys.argv else ""
    if not script:
        raise ValueError("Cannot build restart command: sys.argv[0] is empty")

    script_path = Path(script)
    # setuptools/pip Windows console_scripts launcher:
    # argv[0] is often ``...\Scripts\irswitchd`` (no suffix) or ``...\irswitchd.exe``.
    # Never pass that path as a script to python.exe — it is a PE shim, not .py.
    exe_candidate = (
        script_path if script_path.suffix.lower() == ".exe" else script_path.with_suffix(".exe")
    )
    if exe_candidate.is_file():
        return [str(exe_candidate.resolve()), "--config", cfg]

    return [sys.executable, script, "--config", cfg]


def spawn_detached_restart(
    *,
    config_path: str | Path,
    cwd: str | Path | None = None,
    backoff_seconds: float = DEFAULT_PORT_BACKOFF_SECONDS,
) -> None:
    """
    Spawn a detached successor process with the same exe/argv style and --config.

    Sets ``IRSWITCH_RESTARTING=1`` so the child can retry claiming ``http_port``
    while the parent shuts down.

    Raises OSError / ValueError on spawn failure. Does not wait for the child
    to become healthy — only that the OS accepted the new process.
    """
    command = build_restart_command(config_path=config_path)
    work_dir = str(cwd) if cwd is not None else None

    logger.info(
        "Spawning detached restart process: command=%s cwd=%s backoff=%.2fs",
        command,
        work_dir,
        backoff_seconds,
    )

    if sys.platform == "win32":
        _spawn_windows(command, cwd=work_dir, backoff_seconds=backoff_seconds)
    else:
        _spawn_posix(command, cwd=work_dir, backoff_seconds=backoff_seconds)


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env[RESTART_ENV_FLAG] = "1"
    # Broken SSLKEYLOGFILE (inaccessible Volume GUID) crashes ssl on Python 3.14+.
    keylog = env.get("SSLKEYLOGFILE")
    if keylog:
        parent = os.path.dirname(keylog)
        if not parent or not os.path.isdir(parent):
            env.pop("SSLKEYLOGFILE", None)
    return env


def _spawn_windows(
    command: list[str],
    *,
    cwd: str | None,
    backoff_seconds: float,
) -> None:
    """Detached Windows spawn of the real command (handoff via port retry)."""
    del backoff_seconds  # handoff uses IRSWITCH_RESTARTING retry, not sleep launcher
    create_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", None)
    detached = getattr(subprocess, "DETACHED_PROCESS", None)
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", None)
    startupinfo_factory = getattr(subprocess, "STARTUPINFO", None)
    use_show_window = getattr(subprocess, "STARTF_USESHOWWINDOW", None)
    hide_window = getattr(subprocess, "SW_HIDE", None)
    if (
        create_group is None
        or detached is None
        or no_window is None
        or startupinfo_factory is None
        or use_show_window is None
        or hide_window is None
    ):
        raise OSError("Windows detached-process APIs are unavailable")

    creationflags = int(create_group) | int(detached) | int(no_window)
    startupinfo = startupinfo_factory()
    startupinfo.dwFlags |= int(use_show_window)
    startupinfo.wShowWindow = int(hide_window)

    subprocess.Popen(  # noqa: S603 — intentional re-exec of our own process
        command,
        cwd=cwd,
        env=_child_env(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        startupinfo=startupinfo,
        close_fds=True,
    )


def _spawn_posix(
    command: list[str],
    *,
    cwd: str | None,
    backoff_seconds: float,
) -> None:
    """Detached POSIX spawn; optional sleep then exec, plus restart env flag."""
    delay = max(0.0, float(backoff_seconds))
    if delay > 0:
        launcher = (
            "import os, sys, time;" f"time.sleep({delay!r});" "os.execv(sys.argv[1], sys.argv[1:])"
        )
        popen_args = [sys.executable, "-c", launcher, *command]
    else:
        popen_args = command

    subprocess.Popen(  # noqa: S603
        popen_args,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env=_child_env(),
    )
