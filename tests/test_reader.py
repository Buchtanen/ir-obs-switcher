"""Tests for iRacing reader."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from irswitch.iracing.reader import IRacingReader


@pytest.fixture
def reader() -> IRacingReader:
    """Create iRacing reader for testing."""
    return IRacingReader(poll_hz=5, quit_stall_seconds=0.4)


@pytest.mark.asyncio
async def test_read_mode_disconnected(reader: IRacingReader) -> None:
    """Test reading mode when iRacing is disconnected."""
    mock_sdk = MagicMock()
    mock_sdk.is_initialized = False
    mock_sdk.is_connected = False

    reader._sdk = mock_sdk

    mode = await reader.read_mode()
    assert mode is None


def test_is_connected(reader: IRacingReader) -> None:
    """Test connection status check."""
    mock_sdk = MagicMock()
    mock_sdk.is_initialized = True
    reader._sdk = mock_sdk

    assert reader.is_connected() is True

    mock_sdk.is_initialized = False
    assert reader.is_connected() is False


def test_read_vars(reader: IRacingReader) -> None:
    """Test reading variables."""
    mock_sdk = MagicMock()
    mock_sdk.__getitem__ = MagicMock(side_effect=lambda key: {"var1": 1, "var2": 2}.get(key, None))
    reader._sdk = mock_sdk

    result = reader.read_vars(["var1", "var2", "var3"])
    assert result["var1"] == 1
    assert result["var2"] == 2
    assert result["var3"] is None  # Missing variable returns None


@pytest.mark.asyncio
async def test_read_session_info_requests_session_info_yaml(reader: IRacingReader) -> None:
    """Live session type lives in YAML SessionInfo, not a SessionType telemetry var."""
    from irswitch.iracing.reader import SESSION_INFO_VARS

    assert "SessionInfo" in SESSION_INFO_VARS
    assert "SessionNum" in SESSION_INFO_VARS

    mock_sdk = MagicMock()
    mock_sdk.is_initialized = True
    mock_sdk.is_connected = True
    reader._sdk = mock_sdk
    captured: list[list[str]] = []

    def fake_read_vars(names):
        captured.append(list(names))
        return dict.fromkeys(names)

    reader.read_vars = fake_read_vars  # type: ignore[method-assign]
    await reader.read_session_info()
    assert captured
    assert "SessionInfo" in captured[0]
    assert "SessionNum" in captured[0]


def test_session_sdk_payload_prefers_telemetry_cache(reader: IRacingReader) -> None:
    reader._last_telemetry_data = {
        "SessionNum": 0,
        "SessionInfo": {"Sessions": [{"SessionType": "Practice"}]},
    }
    payload = reader.session_sdk_payload()
    assert payload["SessionNum"] == 0
    assert payload["SessionInfo"]["Sessions"][0]["SessionType"] == "Practice"


def test_session_sdk_payload_empty_without_session_keys(reader: IRacingReader) -> None:
    reader._last_telemetry_data = {"Lap": 3}
    assert reader.session_sdk_payload() == {}


def test_session_sdk_payload_empty_with_session_num_only(reader: IRacingReader) -> None:
    """SessionNum without YAML is not identity — would otherwise skip read_session_info."""
    reader._last_telemetry_data = {"SessionNum": 1, "WeekendInfo": {"EventType": "Race"}}
    assert reader.session_sdk_payload() == {}
