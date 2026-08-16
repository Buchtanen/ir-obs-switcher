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

# Short delay so the parent can release http_port before the child binds.
DEFAULT_PORT_BACKOFF_SECONDS = 1.5


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
    Dev / console_scripts: ``python <script> --config <path>``
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

    return [sys.executable, script, "--config", cfg]


def spawn_detached_restart(
    *,
    config_path: str | Path,
    cwd: str | Path | None = None,
    backoff_seconds: float = DEFAULT_PORT_BACKOFF_SECONDS,
) -> None:
    """
    Spawn a detached successor process with the same exe/argv style and --config.

    On Windows, optionally delays start (``backoff_seconds``) so the parent can
    release ``http_port`` before the child listens.

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


def _spawn_windows(
    command: list[str],
    *,
    cwd: str | None,
    backoff_seconds: float,
) -> None:
    """Detached Windows spawn; optional ``timeout`` delay before re-exec."""
    creationflags = (
        subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NO_WINDOW
    )
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    delay = max(0, int(round(backoff_seconds)))
    if delay > 0:
        # Parent still holds the port; delay child start until after shutdown.
        quoted = subprocess.list2cmdline(command)
        shell_cmd = f"timeout /t {delay} /nobreak >nul & {quoted}"
        popen_args: list[str] = ["cmd.exe", "/c", shell_cmd]
    else:
        popen_args = command

    subprocess.Popen(  # noqa: S603 — intentional re-exec of our own process
        popen_args,
        cwd=cwd,
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
    """Detached POSIX spawn (tests / non-Windows); optional sleep then exec."""
    delay = max(0.0, float(backoff_seconds))
    if delay > 0:
        # Small launcher: sleep then exec — avoids holding the parent on sleep.
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
        env=os.environ.copy(),
    )
