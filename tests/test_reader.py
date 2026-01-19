"""Tests for iRacing reader."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from irswitch.iracing.reader import IRacingReader
from irswitch.models import DrivingMode


@pytest.fixture
def reader() -> IRacingReader:
    """Create iRacing reader for testing."""
    return IRacingReader(poll_hz=5)


@pytest.mark.asyncio
async def test_read_mode_connected_race(reader: IRacingReader) -> None:
    """Test reading RACE mode when connected."""
    mock_sdk = MagicMock()
    mock_sdk.is_initialized = True
    mock_sdk.__getitem__ = MagicMock(side_effect=lambda key: {"IsOnTrack": True}.get(key, None))

    reader._sdk = mock_sdk

    mode = await reader.read_mode()
    assert mode == DrivingMode.RACE


@pytest.mark.asyncio
async def test_read_mode_connected_replay(reader: IRacingReader) -> None:
    """Test reading REPLAY mode when connected."""
    mock_sdk = MagicMock()
    mock_sdk.is_initialized = True
    mock_sdk.__getitem__ = MagicMock(side_effect=lambda key: {"IsReplay": True}.get(key, None))

    reader._sdk = mock_sdk

    mode = await reader.read_mode()
    assert mode == DrivingMode.REPLAY


@pytest.mark.asyncio
async def test_read_mode_connected_garage(reader: IRacingReader) -> None:
    """Test reading GARAGE mode when connected."""
    mock_sdk = MagicMock()
    mock_sdk.is_initialized = True
    mock_sdk.__getitem__ = MagicMock(
        side_effect=lambda key: {"PlayerCarInGarage": True}.get(key, None)
    )

    reader._sdk = mock_sdk

    mode = await reader.read_mode()
    assert mode == DrivingMode.GARAGE


@pytest.mark.asyncio
async def test_read_mode_connected_idle(reader: IRacingReader) -> None:
    """Test reading IDLE mode when connected."""
    mock_sdk = MagicMock()
    mock_sdk.is_initialized = True
    mock_sdk.__getitem__ = MagicMock(side_effect=lambda key: None)

    reader._sdk = mock_sdk

    mode = await reader.read_mode()
    assert mode == DrivingMode.IDLE


@pytest.mark.asyncio
async def test_read_mode_disconnected(reader: IRacingReader) -> None:
    """Test reading mode when iRacing is disconnected."""
    mock_sdk = MagicMock()
    mock_sdk.is_initialized = False

    reader._sdk = mock_sdk

    mode = await reader.read_mode()
    assert mode is None


@pytest.mark.asyncio
async def test_read_mode_missing_variables(reader: IRacingReader) -> None:
    """Test handling of missing variables."""
    mock_sdk = MagicMock()
    mock_sdk.is_initialized = True
    mock_sdk.__getitem__ = MagicMock(side_effect=KeyError("Variable not found"))

    reader._sdk = mock_sdk

    # Should handle missing variables gracefully
    mode = await reader.read_mode()
    # Should return IDLE or None depending on implementation
    assert mode is not None  # extract_mode handles missing vars as IDLE


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
