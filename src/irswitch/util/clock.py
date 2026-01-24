"""Clock abstraction using monotonic time."""

from __future__ import annotations

import time


def now_ms() -> int:
    """
    Return current monotonic time in milliseconds.

    Uses time.monotonic() to ensure time always increases and is not
    affected by system clock adjustments. Suitable for cooldown and
    debounce logic.
    """
    return int(time.monotonic() * 1000)
