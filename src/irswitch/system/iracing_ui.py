"""Read-only launcher presence for operator UI, never an SDK/session signal."""

from __future__ import annotations

import time


def detect_iracing_ui() -> bool | None:
    """Return true for the exact launcher name, false for absence, None if unknown.

    Call off the event loop. Enumerate names only; expose no process inventory.
    Missing optional psutil, unreadable names or failed scans are not absence.
    """
    try:
        import psutil

        deadline = time.monotonic() + 1.0
        incomplete = False
        for process in psutil.process_iter(["name"], ad_value=None):
            if time.monotonic() > deadline:
                return None
            name = process.info.get("name")
            if not isinstance(name, str) or not name:
                incomplete = True
            elif name.casefold() == "iracingui.exe":
                return True
        return None if incomplete else False
    except Exception:
        # Presence is optional; OS/dependency failures cannot take down the status API.
        return None
