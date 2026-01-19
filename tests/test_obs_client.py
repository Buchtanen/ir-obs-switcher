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
    mock_response.current_program_scene_name = "TestScene"
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
    mock_response.current_program_scene_name = "OldScene"
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
    mock_response.current_program_scene_name = "CurrentScene"
    mock_client.get_current_program_scene.return_value = mock_response

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        result = await obs_client.set_scene("CurrentScene")

    assert result is True
    # get_current_scene is called to check current scene, but set_scene should not be called
    # because current scene matches target
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
    mock_response.current_program_scene_name = "OldScene"
    mock_client.get_current_program_scene.return_value = mock_response
    mock_client.set_current_program_scene.side_effect = Exception("Network error")

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        result = await obs_client.set_scene("NewScene")

    assert result is False
    assert obs_client.is_connected() is False


@pytest.mark.asyncio
async def test_get_stream_status_streaming(obs_client: ObsClient) -> None:
    """Test getting stream status when streaming."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.output_active = True
    mock_response.output_duration = 123.45
    mock_client.get_stream_status.return_value = mock_response

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        is_streaming, duration_ms = await obs_client.get_stream_status()

    assert is_streaming is True
    assert duration_ms == 123450


@pytest.mark.asyncio
async def test_get_stream_status_not_streaming(obs_client: ObsClient) -> None:
    """Test getting stream status when not streaming."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.output_active = False
    mock_client.get_stream_status.return_value = mock_response

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        is_streaming, duration_ms = await obs_client.get_stream_status()

    assert is_streaming is False
    assert duration_ms is None


@pytest.mark.asyncio
async def test_get_stream_status_not_connected(obs_client: ObsClient) -> None:
    """Test getting stream status when not connected."""
    is_streaming, duration_ms = await obs_client.get_stream_status()
    assert is_streaming is False
    assert duration_ms is None


@pytest.mark.asyncio
async def test_is_broadcast_ready_ready(obs_client: ObsClient) -> None:
    """Test checking broadcast ready status when ready."""
    mock_client = MagicMock()
    
    # Mock output status - not active, not reconnecting
    output_status = MagicMock()
    output_status.output_active = False
    output_status.output_reconnecting = False
    mock_client.get_output_status.return_value = output_status
    
    # Mock service settings - configured
    service_settings = MagicMock()
    service_settings.stream_service_type = "rtmp_common"
    mock_client.get_stream_service_settings.return_value = service_settings

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        is_ready = await obs_client.is_broadcast_ready()

    assert is_ready is True


@pytest.mark.asyncio
async def test_is_broadcast_ready_streaming(obs_client: ObsClient) -> None:
    """Test checking broadcast ready when already streaming."""
    mock_client = MagicMock()
    
    output_status = MagicMock()
    output_status.output_active = True  # Already streaming
    output_status.output_reconnecting = False
    mock_client.get_output_status.return_value = output_status

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        is_ready = await obs_client.is_broadcast_ready()

    assert is_ready is False


@pytest.mark.asyncio
async def test_is_broadcast_ready_not_configured(obs_client: ObsClient) -> None:
    """Test checking broadcast ready when service not configured."""
    mock_client = MagicMock()
    
    output_status = MagicMock()
    output_status.output_active = False
    output_status.output_reconnecting = False
    mock_client.get_output_status.return_value = output_status
    
    service_settings = MagicMock()
    service_settings.stream_service_type = None  # Not configured
    mock_client.get_stream_service_settings.return_value = service_settings

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        is_ready = await obs_client.is_broadcast_ready()

    assert is_ready is False


@pytest.mark.asyncio
async def test_is_broadcast_ready_not_connected(obs_client: ObsClient) -> None:
    """Test checking broadcast ready when not connected."""
    is_ready = await obs_client.is_broadcast_ready()
    assert is_ready is False


@pytest.mark.asyncio
async def test_start_stream_success(obs_client: ObsClient) -> None:
    """Test starting stream successfully."""
    mock_client = MagicMock()
    mock_client.start_stream.return_value = MagicMock()

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        result = await obs_client.start_stream()

    assert result is True
    mock_client.start_stream.assert_called_once()


@pytest.mark.asyncio
async def test_start_stream_already_running(obs_client: ObsClient) -> None:
    """Test starting stream when already running."""
    mock_client = MagicMock()
    mock_client.start_stream.side_effect = Exception("Stream already running")

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        result = await obs_client.start_stream()

    assert result is True  # Should return True even if already running


@pytest.mark.asyncio
async def test_start_stream_error(obs_client: ObsClient) -> None:
    """Test starting stream with error."""
    mock_client = MagicMock()
    mock_client.start_stream.side_effect = Exception("Network error")

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        result = await obs_client.start_stream()

    assert result is False


@pytest.mark.asyncio
async def test_start_stream_not_connected(obs_client: ObsClient) -> None:
    """Test starting stream when not connected."""
    result = await obs_client.start_stream()
    assert result is False


@pytest.mark.asyncio
async def test_stop_stream_success(obs_client: ObsClient) -> None:
    """Test stopping stream successfully."""
    mock_client = MagicMock()
    mock_client.stop_stream.return_value = MagicMock()

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        result = await obs_client.stop_stream()

    assert result is True
    mock_client.stop_stream.assert_called_once()


@pytest.mark.asyncio
async def test_stop_stream_not_running(obs_client: ObsClient) -> None:
    """Test stopping stream when not running."""
    mock_client = MagicMock()
    mock_client.stop_stream.side_effect = Exception("Stream not running")

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        result = await obs_client.stop_stream()

    assert result is True  # Should return True even if not running


@pytest.mark.asyncio
async def test_stop_stream_error(obs_client: ObsClient) -> None:
    """Test stopping stream with error."""
    mock_client = MagicMock()
    mock_client.stop_stream.side_effect = Exception("Network error")

    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        await obs_client.connect(max_retries=1)
        result = await obs_client.stop_stream()

    assert result is False


@pytest.mark.asyncio
async def test_stop_stream_not_connected(obs_client: ObsClient) -> None:
    """Test stopping stream when not connected."""
    result = await obs_client.stop_stream()
    assert result is False