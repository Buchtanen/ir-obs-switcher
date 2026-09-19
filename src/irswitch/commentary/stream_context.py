"""OBS stream-start → commentary envelope. Fail-soft; no HUD cover."""

from __future__ import annotations

import logging
import time

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.overlay.http import get_overlay_runtime

logger = logging.getLogger(__name__)


def make_stream_start_envelope(now: float) -> EventEnvelope:
    return make_envelope(
        event_type="STREAM_START",
        phase="ENTER",
        mode="GENERIC",
        priority=35,
        monotonic_ms=int(now * 1000),
        dedupe_key="STREAM_START",
        correlation_id="stream_start",
    )


def notify_overlay_stream_started(now: float | None = None) -> None:
    """Rising OBS stream edge. No-op when overlay/commentary is down."""
    try:
        runtime = get_overlay_runtime()
        if runtime is None:
            return
        notify = getattr(runtime, "notify_obs_stream_started", None)
        if not callable(notify):
            return
        notify(now if now is not None else time.monotonic())
    except Exception:
        logger.warning("stream-start commentary bridge failed", exc_info=True)
