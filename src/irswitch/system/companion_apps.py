"""Read-only presence hints for the operator, never simulator readiness signals."""

from __future__ import annotations

import time

# Exact main executables: background services/crash handlers are deliberately absent.
COMPANION_APPS = (
    ("dre", "DRE", "dre.exe"),
    ("maira", "MAIRA", "marvinsairarefactored.exe"),
    ("simhub", "SimHub", "simhubwpf.exe"),
    ("cammus", "Cammus", "cammus.exe"),
    ("trading_paints", "Trading Paints", "trading paints.exe"),
    ("virtual_desktop", "Virtual Desktop Streamer", "virtualdesktop.streamer.exe"),
)


def detect_companion_apps() -> dict[str, bool | None]:
    """Scan once off-loop; retain positives but never infer absence from failure.

    The budget is cooperative between process items, not an OS-call timeout.
    No PID, path, command line or unrelated process data leaves this module.
    """
    names = {key: name for key, _label, name in COMPANION_APPS}
    names["iracing_ui"] = "iracingui.exe"
    result: dict[str, bool | None] = dict.fromkeys(names)
    try:
        import psutil

        deadline = time.monotonic() + 1.0
        incomplete = False
        for process in psutil.process_iter(["name"], ad_value=None):
            if time.monotonic() > deadline:
                return result
            name = process.info.get("name")
            if not isinstance(name, str) or not name:
                incomplete = True
                continue
            for key, expected in names.items():
                if name.casefold() == expected:
                    result[key] = True
        if not incomplete:
            result = {key: value is True for key, value in result.items()}
    except Exception:
        # Optional OS/dependency failure must not break admin status or control loops.
        pass
    return result
