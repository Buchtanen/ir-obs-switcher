"""Tests for OBS WebSocket client."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from irswitch.obs.client import ObsClient


@pytest.fixture
def obs_client() -> ObsClient:
    """Create OBS client instance for testing."""
    return ObsClient(ws_url="ws://127.0.0.1:4455", password="test_password")


@pytest.mark.asyncio
async def test_connect_success(obs_client: ObsClient) -> None:
    """Test successful connection to OBS."""
    mock_client = MagicMock()
    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)

    assert obs_client.is_connected() is True


@pytest.mark.asyncio
async def test_connect_retry_on_failure(obs_client: ObsClient) -> None:
    """Test connection retry with backoff."""
    mock_client = MagicMock()
    with patch("irswitch.obs.client.ReqClient", side_effect=[Exception("Connection failed"), mock_client]):
        await obs_client.connect(max_retries=2, initial_backoff=0.01)

    assert obs_client.is_connected() is True


@pytest.mark.asyncio
async def test_connect_max_retries_exceeded(obs_client: ObsClient) -> None:
    """Test connection failure after max retries."""
    with patch("irswitch.obs.client.ReqClient", side_effect=Exception("Connection failed")):
        with pytest.raises(ConnectionError):
            await obs_client.connect(max_retries=2, initial_backoff=0.01)


@pytest.mark.asyncio
async def test_disconnect(obs_client: ObsClient) -> None:
    """Test graceful disconnect."""
    mock_client = MagicMock()
    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        assert obs_client.is_connected() is True

        await obs_client.disconnect()
        assert obs_client.is_connected() is False


@pytest.mark.asyncio
async def test_get_current_scene_success(obs_client: ObsClient) -> None:
    """Test getting current scene."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.datain = {"currentProgramSceneName": "TestScene"}
    mock_client.get_current_program_scene.return_value = mock_response

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        scene = await obs_client.get_current_scene()

    assert scene == "TestScene"


@pytest.mark.asyncio
async def test_get_current_scene_not_connected(obs_client: ObsClient) -> None:
    """Test getting scene when not connected."""
    scene = await obs_client.get_current_scene()
    assert scene is None


@pytest.mark.asyncio
async def test_get_current_scene_error(obs_client: ObsClient) -> None:
    """Test error handling when getting scene."""
    mock_client = MagicMock()
    mock_client.get_current_program_scene.side_effect = Exception("Network error")

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        scene = await obs_client.get_current_scene()

    assert scene is None
    assert obs_client.is_connected() is False


@pytest.mark.asyncio
async def test_set_scene_success(obs_client: ObsClient) -> None:
    """Test successful scene switch."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.datain = {"currentProgramSceneName": "OldScene"}
    mock_client.get_current_program_scene.return_value = mock_response
    mock_client.set_current_program_scene.return_value = MagicMock()

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        result = await obs_client.set_scene("NewScene")

    assert result is True
    mock_client.set_current_program_scene.assert_called_once_with("NewScene")


@pytest.mark.asyncio
async def test_set_scene_idempotent(obs_client: ObsClient) -> None:
    """Test that setting scene to current scene is idempotent."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.datain = {"currentProgramSceneName": "CurrentScene"}
    mock_client.get_current_program_scene.return_value = mock_response

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        result = await obs_client.set_scene("CurrentScene")

    assert result is True
    mock_client.set_current_program_scene.assert_not_called()


@pytest.mark.asyncio
async def test_set_scene_not_connected(obs_client: ObsClient) -> None:
    """Test setting scene when not connected."""
    result = await obs_client.set_scene("TestScene")
    assert result is False


@pytest.mark.asyncio
async def test_set_scene_error(obs_client: ObsClient) -> None:
    """Test error handling when setting scene."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.datain = {"currentProgramSceneName": "OldScene"}
    mock_client.get_current_program_scene.return_value = mock_response
    mock_client.set_current_program_scene.side_effect = Exception("Network error")

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        result = await obs_client.set_scene("NewScene")

    assert result is False
    assert obs_client.is_connected() is False
