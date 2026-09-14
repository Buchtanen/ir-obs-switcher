"""Helpers for refreshing YouTube stream/video status on OBS stream edges."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from irswitch.obs.client import ObsClient
    from irswitch.server.event_log import EventLog

logger = logging.getLogger(__name__)

# After OBS stops, YouTube often stays ``live`` briefly; re-check once.
POST_STOP_STATUS_REFRESH_DELAY_S = 45.0
STREAM_EDGE_CONFIRM_POLLS = 3
STREAM_EDGE_CONFIRM_S = 5.0
STREAM_EPOCH_DURATION_DROP_MS = 1000


class StreamEdgeDebouncer:
    """Confirm OBS start/stop only after matching polls or a hold, not a 2 s flap."""

    def __init__(self) -> None:
        self.last_confirmed: bool | None = None
        self.last_duration_ms: int | None = None
        self.pending: bool | None = None
        self.pending_count = 0
        self.pending_since = 0.0

    def reset(self) -> None:
        self.last_confirmed = None
        self.last_duration_ms = None
        self.pending = None
        self.pending_count = 0
        self.pending_since = 0.0

    def observe(
        self,
        current: bool,
        *,
        known: bool,
        duration_ms: int | None,
        now: float,
    ) -> str | None:
        if not known:
            return None
        if (
            current
            and duration_ms is not None
            and self.last_duration_ms is not None
            and duration_ms + STREAM_EPOCH_DURATION_DROP_MS < self.last_duration_ms
        ):
            self.last_confirmed = True
            self.last_duration_ms = duration_ms
            self.pending = None
            self.pending_count = 0
            return "obs_stream_started"
        if self.last_confirmed is current:
            if duration_ms is not None:
                self.last_duration_ms = duration_ms
            self.pending = None
            self.pending_count = 0
            return None
        if self.pending is not current:
            self.pending = current
            self.pending_since = now
            self.pending_count = 1
            return None
        self.pending_count += 1
        held_s = now - self.pending_since
        if self.pending_count >= STREAM_EDGE_CONFIRM_POLLS or held_s >= STREAM_EDGE_CONFIRM_S:
            previous = self.last_confirmed
            self.last_confirmed = current
            if duration_ms is not None:
                self.last_duration_ms = duration_ms
            elif not current:
                self.last_duration_ms = None
            self.pending = None
            self.pending_count = 0
            return classify_streaming_edge(previous, current)
        return None


def classify_streaming_edge(previous: bool | None, current: bool) -> str | None:
    """
    Classify OBS streaming transitions.

    ``previous is None`` means first sample: treat True as start (mid-stream
    attach), False as no-op (idle boot).
    """
    if previous is None:
        return "obs_stream_started" if current else None
    if current and not previous:
        return "obs_stream_started"
    if not current and previous:
        return "obs_stream_stopped"
    return None


async def refresh_stream_status(
    obs_client: ObsClient,
    event_log: EventLog | None,
    reason: str,
) -> tuple[str | None, str | None]:
    """Force-refresh YouTube stream info; never raise to caller."""
    try:
        title, description = await obs_client.refresh_stream_info(reason, force=True)
        if event_log is not None:
            cached = obs_client.get_cached_stream_info_full() or {}
            await event_log.add_event(
                "stream_status_refreshed",
                f"YouTube stream status refreshed ({reason})",
                {
                    "reason": reason,
                    "stream_title": title,
                    "stream_status": cached.get("status"),
                    "privacy_status": cached.get("privacy_status"),
                },
            )
        return title, description
    except Exception as e:
        logger.warning("Failed refreshing stream status (%s): %s", reason, e)
        return None, None


def schedule_post_stop_status_refresh(
    *,
    obs_client: ObsClient,
    event_log: EventLog | None,
    spawn: Callable[[str, Coroutine[Any, Any, None]], Any],
    delay_s: float = POST_STOP_STATUS_REFRESH_DELAY_S,
    on_done: Callable[[], Coroutine[Any, Any, None]] | None = None,
) -> None:
    """
    Schedule a single delayed refresh after stream stop.

    ``spawn(name, coro)`` should cancel any prior task with the same name
    (``TaskRegistry.spawn(..., replace=True)``).
    """

    async def _delayed() -> None:
        try:
            await asyncio.sleep(delay_s)
            await refresh_stream_status(obs_client, event_log, "obs_stream_stopped_delayed")
            if on_done is not None:
                await on_done()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Post-stop stream status refresh failed")

    spawn("youtube_post_stop_status_refresh", _delayed())
