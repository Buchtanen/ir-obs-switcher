"""Status glue must use the same OBS timeline as chapter generation."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from irswitch.logic.stream_chapters import StreamChaptersSettings
from irswitch.models import DrivingMode, SwitchState
from irswitch.obs.client import ObsClient
from irswitch.server import api
from irswitch.server.metrics import reset_metrics


@pytest.mark.asyncio
async def test_status_chapters_follow_output_duration_and_shared_epoch() -> None:
    api.reset_state()
    reset_metrics()
    api.get_stream_chapter_tracker().apply_settings(StreamChaptersSettings(enabled=True))
    obs = AsyncMock(spec=ObsClient)
    obs.stream_status_known = True
    obs.get_cached_broadcast_id = MagicMock(return_value="first")
    obs.get_current_profile = AsyncMock(return_value=None)
    obs.is_stream_selected = AsyncMock(return_value=(True, False))
    obs.get_cached_stream_info = MagicMock(return_value=(None, None, False, False))
    obs.get_cached_stream_info_full = MagicMock(return_value=None)
    api.set_obs_client(obs)
    state = SwitchState(
        True, True, True, None, None, DrivingMode.RACE, "Race", "Race", None, "test"
    )

    async def sample(now, active, duration, session, broadcast_id="first", connected=True):
        obs.get_stream_status = AsyncMock(return_value=(active, duration))
        obs.get_cached_broadcast_id.return_value = broadcast_id
        with patch("time.monotonic", return_value=now):
            return await api._get_status_dict(
                replace(state, session_type=session, connected_obs=connected)
            )

    try:
        await sample(100, True, 600_000, "Practice")
        first = await sample(110, True, 610_000, "Qualify")
        assert first["stream_duration_current_session_seconds"] == 610
        assert first["stream_chapters"][-1]["offset_seconds"] == 610
        await sample(111, False, None, "Qualify")
        resumed = await sample(112, True, 500, "Race")
        assert resumed["stream_duration_current_session_seconds"] == 610.5
        advanced = await sample(122, True, 10_500, "Race")
        assert [c["offset_seconds"] for c in advanced["stream_chapters"]] == [0, 610, 620]
        # Transport loss must not confirm a stop or reset the logical broadcast.
        await sample(125, False, None, "Race", connected=False)
        recovered = await sample(135, True, 23_500, "Race")
        assert len(recovered["stream_chapters"]) == 3
        assert recovered["stream_duration_current_session_seconds"] == 633.5
        new = await sample(140, True, 2000, "Practice", broadcast_id="second")
        assert new["stream_duration_current_session_seconds"] == 2
        assert [(c["title"], c["offset_seconds"]) for c in new["stream_chapters"]] == [
            ("Stream start", 0)
        ]
    finally:
        api.reset_state()
        reset_metrics()
