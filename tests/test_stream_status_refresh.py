"""Tests for OBS streaming-edge YouTube status refresh helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from irswitch.obs.stream_status_refresh import (
    POST_STOP_STATUS_REFRESH_DELAY_S,
    classify_streaming_edge,
    refresh_stream_status,
    schedule_post_stop_status_refresh,
)


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        (None, False, None),
        (None, True, "obs_stream_started"),
        (False, True, "obs_stream_started"),
        (True, False, "obs_stream_stopped"),
        (True, True, None),
        (False, False, None),
    ],
)
def test_classify_streaming_edge(
    previous: bool | None, current: bool, expected: str | None
) -> None:
    assert classify_streaming_edge(previous, current) == expected


@pytest.mark.asyncio
async def test_refresh_stream_status_logs_event() -> None:
    obs = MagicMock()
    obs.refresh_stream_info = AsyncMock(return_value=("Title", "Desc"))
    obs.get_cached_stream_info_full.return_value = {
        "status": "live",
        "privacy_status": "public",
    }
    event_log = MagicMock()
    event_log.add_event = AsyncMock()

    title, desc = await refresh_stream_status(obs, event_log, "obs_stream_started")
    assert title == "Title"
    assert desc == "Desc"
    obs.refresh_stream_info.assert_awaited_once_with("obs_stream_started", force=True)
    event_log.add_event.assert_awaited()
    args = event_log.add_event.await_args
    assert args.args[0] == "stream_status_refreshed"
    assert args.args[2]["stream_status"] == "live"


@pytest.mark.asyncio
async def test_refresh_stream_status_swallows_errors() -> None:
    obs = MagicMock()
    obs.refresh_stream_info = AsyncMock(side_effect=RuntimeError("quota"))
    title, desc = await refresh_stream_status(obs, None, "obs_stream_stopped")
    assert title is None and desc is None


@pytest.mark.asyncio
async def test_schedule_post_stop_status_refresh_runs_after_delay() -> None:
    obs = MagicMock()
    obs.refresh_stream_info = AsyncMock(return_value=("T", None))
    obs.get_cached_stream_info_full.return_value = {"status": "complete"}
    event_log = MagicMock()
    event_log.add_event = AsyncMock()
    done = AsyncMock()

    tasks: dict[str, asyncio.Task] = {}

    def spawn(name: str, coro: object) -> asyncio.Task:
        task = asyncio.create_task(coro)  # type: ignore[arg-type]
        tasks[name] = task
        return task

    schedule_post_stop_status_refresh(
        obs_client=obs,
        event_log=event_log,
        spawn=spawn,
        delay_s=0.05,
        on_done=done,
    )
    assert "youtube_post_stop_status_refresh" in tasks
    await tasks["youtube_post_stop_status_refresh"]
    obs.refresh_stream_info.assert_awaited_once_with("obs_stream_stopped_delayed", force=True)
    done.assert_awaited_once()
    assert POST_STOP_STATUS_REFRESH_DELAY_S == 45.0
