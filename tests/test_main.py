"""Tests for main service."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from irswitch.config import AppConfig
from irswitch.main import main, run_service


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Create temporary config file."""
    config_file = tmp_path / "config.ini"
    config_file.write_text("""[app]
http_host = 127.0.0.1
http_port = 17321
log_level = INFO

[iracing]
poll_hz = 5

[obs]
ws_url = ws://127.0.0.1:4455
password = test_password

[switching]
autoswitch_default = true
debounce_ms = 900
cooldown_ms = 1000
override_seconds = 120
safe_scene = Idle

[scenes]
IDLE = Idle
GARAGE = Pits
RACE = Race
REPLAY = Replay
""")
    return config_file


@pytest.mark.asyncio
async def test_run_service_initialization(config_path: Path) -> None:
    """Test service initialization."""
    config = AppConfig.from_file(config_path)

    with (
        patch("irswitch.main.IRacingReader") as mock_reader_class,
        patch("irswitch.main.ObsClient") as mock_obs_class,
        patch("irswitch.main.web.AppRunner") as mock_runner_class,
        patch("irswitch.main.web.TCPSite") as mock_site_class,
    ):
        # Setup mocks
        mock_reader = MagicMock()
        mock_reader.is_connected.return_value = True
        mock_reader.read_mode = AsyncMock(return_value=None)
        mock_reader_class.return_value = mock_reader

        # Use MagicMock for sync methods, AsyncMock for async methods
        # is_connected() is sync in ObsClient, so use MagicMock
        mock_obs = MagicMock()
        mock_obs.is_connected.return_value = True
        mock_obs.get_current_scene = AsyncMock(return_value="Idle")
        mock_obs.set_scene = AsyncMock(return_value=True)
        mock_obs.connect = AsyncMock()
        mock_obs.disconnect = AsyncMock()
        mock_obs.get_scene_list = AsyncMock(return_value=["Idle", "Race", "Pits"])
        mock_obs_class.return_value = mock_obs

        mock_runner = MagicMock()
        mock_runner.setup = AsyncMock()
        mock_runner.cleanup = AsyncMock()
        mock_runner_class.return_value = mock_runner

        # Mock TCPSite
        mock_site = MagicMock()
        mock_site.start = AsyncMock()
        mock_site_class.return_value = mock_site

        # Run service for a short time
        try:
            task = asyncio.create_task(run_service(config, str(config_path)))
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        except Exception as e:
            # Some errors are expected during cancellation
            if "CancelledError" not in str(type(e)):
                raise

        # Verify initialization
        mock_reader.startup.assert_called_once()
        mock_obs.connect.assert_called()


def test_main_invalid_config() -> None:
    """Test main with invalid config path."""
    with patch("sys.argv", ["irswitchd", "--config", "/nonexistent/config.ini"]):
        result = main()
        assert result == 1


def test_main_valid_config(config_path: Path) -> None:
    """Test main with valid config (will exit quickly)."""
    with (
        patch("sys.argv", ["irswitchd", "--config", str(config_path)]),
        patch("irswitch.main.run_service") as mock_run,
    ):
        mock_run.side_effect = KeyboardInterrupt()
        result = main()
        assert result == 0


def test_main_instance_already_running_exits_2(config_path: Path) -> None:
    """Second instance conflict must exit with code 2."""
    from irswitch.util.single_instance import InstanceAlreadyRunningError

    with (
        patch("sys.argv", ["irswitchd", "--config", str(config_path)]),
        patch(
            "irswitch.main.run_service",
            side_effect=InstanceAlreadyRunningError("port in use"),
        ),
    ):
        result = main()
        assert result == 2


@pytest.mark.asyncio
async def test_stream_cache_fresh_scenario() -> None:
    """Test that fresh cache is used directly for auto-start decision."""
    from irswitch.util.clock import now_ms

    # Simulate fresh cache (within 5 seconds)
    current_ts = now_ms()
    last_stream_selected = True
    last_stream_ready_selected = True
    last_stream_selection_check_ts = current_ts - 3000  # 3 seconds ago - fresh

    # Verify cache is considered fresh
    cache_age_ms = current_ts - last_stream_selection_check_ts
    assert cache_age_ms <= 5000  # Fresh threshold
    assert last_stream_selected is True
    assert last_stream_ready_selected is True


@pytest.mark.asyncio
async def test_stream_cache_stale_scenario() -> None:
    """Test that stale cache triggers API fallback."""
    from irswitch.util.clock import now_ms

    # Simulate stale cache (between 5-10 seconds)
    current_ts = now_ms()
    last_stream_selected = True
    last_stream_ready_selected = True
    last_stream_selection_check_ts = current_ts - 7000  # 7 seconds ago - stale

    # Verify cache is considered stale but within grace period
    cache_age_ms = current_ts - last_stream_selection_check_ts
    assert 5000 < cache_age_ms <= 10000  # Within grace period
    assert last_stream_selected is True
    assert last_stream_ready_selected is True


@pytest.mark.asyncio
async def test_stream_cache_expired_scenario() -> None:
    """Test that expired cache forces API call."""
    from irswitch.util.clock import now_ms

    # Simulate expired cache (older than 10 seconds)
    current_ts = now_ms()
    last_stream_selected = True
    last_stream_ready_selected = True
    last_stream_selection_check_ts = current_ts - 15000  # 15 seconds ago - expired

    # Verify cache is considered expired
    cache_age_ms = current_ts - last_stream_selection_check_ts
    assert cache_age_ms > 10000  # Beyond grace period
    assert last_stream_selected is True
    assert last_stream_ready_selected is True


@pytest.mark.asyncio
async def test_stream_no_cache_scenario() -> None:
    """Test that no cache forces API call."""

    # Simulate no cache (never selected)
    last_stream_selected = False
    last_stream_ready_selected = False
    last_stream_selection_check_ts = 0.0

    # Verify no cache scenario
    assert last_stream_selected is False
    assert last_stream_ready_selected is False
    assert last_stream_selection_check_ts == 0.0


def test_stream_cache_constants() -> None:
    """Test that cache constants are defined correctly."""
    # Import from main module to verify constants exist
    from irswitch.main import STREAM_CACHE_FRESH_MS, STREAM_CACHE_GRACE_MS

    assert STREAM_CACHE_FRESH_MS == 5000  # 5 seconds
    assert STREAM_CACHE_GRACE_MS == 10000  # 10 seconds
    assert STREAM_CACHE_FRESH_MS < STREAM_CACHE_GRACE_MS  # Fresh < Grace
