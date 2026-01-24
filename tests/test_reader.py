"""Tests for iRacing reader."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from irswitch.iracing.reader import IRacingReader
from irswitch.models import DrivingMode


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
    mock_sdk.__getitem__ = MagicMock(
        side_effect=lambda key: {"var1": 1, "var2": 2}.get(key, None)
    )
    reader._sdk = mock_sdk

    result = reader.read_vars(["var1", "var2", "var3"])
    assert result["var1"] == 1
    assert result["var2"] == 2
    assert result["var3"] is None  # Missing variable returns None
