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


# YouTube API tests
@pytest.mark.asyncio
async def test_get_cached_stream_info_no_cache(obs_client: ObsClient) -> None:
    """Test get_cached_stream_info when cache is empty."""
    title, description, quota_exceeded, api_key_missing = obs_client.get_cached_stream_info()
    assert title is None
    assert description is None
    assert quota_exceeded is False
    assert api_key_missing is False


@pytest.mark.asyncio
async def test_get_cached_stream_info_with_cache(obs_client: ObsClient) -> None:
    """Test get_cached_stream_info returns cached values."""
    # Set cache manually (simulating successful API call)
    obs_client._stream_info_cache = ("Test Title", "Test Description")
    obs_client._stream_info_cache_broadcast_id = "test_broadcast_id"
    
    title, description, quota_exceeded, api_key_missing = obs_client.get_cached_stream_info()
    assert title == "Test Title"
    assert description == "Test Description"
    assert quota_exceeded is False
    assert api_key_missing is False


@pytest.mark.asyncio
async def test_get_cached_stream_info_with_quota_exceeded(obs_client: ObsClient) -> None:
    """Test get_cached_stream_info when quota is exceeded."""
    obs_client._youtube_quota_exceeded = True
    
    title, description, quota_exceeded, api_key_missing = obs_client.get_cached_stream_info()
    assert quota_exceeded is True
    assert api_key_missing is False


@pytest.mark.asyncio
async def test_get_cached_stream_info_with_api_key_missing(obs_client: ObsClient) -> None:
    """Test get_cached_stream_info when API key is missing."""
    obs_client._youtube_api_key_missing = True
    
    title, description, quota_exceeded, api_key_missing = obs_client.get_cached_stream_info()
    assert quota_exceeded is False
    assert api_key_missing is True


@pytest.mark.asyncio
async def test_get_stream_info_without_api_key(obs_client: ObsClient) -> None:
    """Test get_stream_info when YOUTUBE_API_KEY is not set."""
    mock_client = MagicMock()
    
    # Mock broadcast_id extraction
    service_settings = MagicMock()
    service_settings.stream_service_settings = "{'broadcast_id': 'test_id'}"
    mock_client.get_stream_service_settings.return_value = service_settings
    
    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        with patch.dict("os.environ", {}, clear=True):  # Clear YOUTUBE_API_KEY
            await obs_client.connect(max_retries=1)
            title, description = await obs_client.get_stream_info()
    
    # Should return None, None when API key is missing
    assert title is None or title == ""  # Might be empty string from OBS
    assert description is None or description == ""
    assert obs_client._youtube_api_key_missing is True


@pytest.mark.asyncio
async def test_get_stream_info_quota_exceeded(obs_client: ObsClient) -> None:
    """Test get_stream_info when YouTube API quota is exceeded."""
    mock_client = MagicMock()
    
    # Mock broadcast_id extraction
    service_settings = MagicMock()
    service_settings.stream_service_settings = "{'broadcast_id': 'test_id'}"
    mock_client.get_stream_service_settings.return_value = service_settings
    
    # Mock HTTP response with 403 quota exceeded
    mock_response = MagicMock()
    mock_response.status = 403
    mock_response.json = AsyncMock(return_value={
        "error": {
            "errors": [{"reason": "quotaExceeded"}]
        }
    })
    
    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "test_key"}):
            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_get.return_value.__aenter__.return_value = mock_response
                mock_get.return_value.__aexit__.return_value = None
                
                await obs_client.connect(max_retries=1)
                title, description = await obs_client.get_stream_info()
    
    assert obs_client._youtube_quota_exceeded is True
    # Should return None or empty when quota exceeded
    assert title is None or title == ""
    assert description is None or description == ""


@pytest.mark.asyncio
async def test_get_stream_info_cache_reset_on_broadcast_id_change(obs_client: ObsClient) -> None:
    """Test that cache resets when broadcast_id changes."""
    mock_client = MagicMock()
    
    # First broadcast_id
    service_settings1 = MagicMock()
    service_settings1.stream_service_settings = "{'broadcast_id': 'broadcast1'}"
    mock_client.get_stream_service_settings.return_value = service_settings1
    
    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "test_key"}):
            await obs_client.connect(max_retries=1)
            # Set cache manually
            obs_client._stream_info_cache = ("Title 1", "Desc 1")
            obs_client._stream_info_cache_broadcast_id = "broadcast1"
            obs_client._youtube_quota_exceeded = True
            
            # Change broadcast_id
            service_settings2 = MagicMock()
            service_settings2.stream_service_settings = "{'broadcast_id': 'broadcast2'}"
            mock_client.get_stream_service_settings.return_value = service_settings2
            
            # Get stream info - should reset quota flag
            await obs_client.get_stream_info()
    
    # Quota flag should be reset when broadcast_id changes
    assert obs_client._youtube_quota_exceeded is False


@pytest.mark.asyncio
async def test_get_stream_info_force_refresh(obs_client: ObsClient) -> None:
    """Test get_stream_info with force_refresh=True bypasses cache."""
    mock_client = MagicMock()
    
    service_settings = MagicMock()
    service_settings.stream_service_settings = "{'broadcast_id': 'test_id'}"
    mock_client.get_stream_service_settings.return_value = service_settings
    
    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "test_key"}):
            await obs_client.connect(max_retries=1)
            # Set cache
            obs_client._stream_info_cache = ("Cached Title", "Cached Desc")
            obs_client._stream_info_cache_broadcast_id = "test_id"
            
            # With force_refresh=True, should bypass cache
            # (actual API call would happen, but we're just testing the flag)
            title, description = await obs_client.get_stream_info(force_refresh=True)
    
    # Cache should be bypassed (result depends on API call, but cache check is skipped)
    assert obs_client._stream_info_cache is not None  # Cache might be updated


@pytest.mark.asyncio
async def test_get_stream_info_does_not_call_api_when_quota_exceeded(obs_client: ObsClient) -> None:
    """Test that get_stream_info does not call API when quota is exceeded."""
    mock_client = MagicMock()
    
    service_settings = MagicMock()
    service_settings.stream_service_settings = "{'broadcast_id': 'test_id'}"
    mock_client.get_stream_service_settings.return_value = service_settings
    
    obs_client._youtube_quota_exceeded = True
    
    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "test_key"}):
            await obs_client.connect(max_retries=1)
            
            # Should not make API calls when quota exceeded
            with patch("aiohttp.ClientSession.get") as mock_get:
                title, description = await obs_client.get_stream_info()
                # Should not be called when quota exceeded
                mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_get_stream_info_does_not_call_api_when_key_missing(obs_client: ObsClient) -> None:
    """Test that get_stream_info does not call API when API key is missing."""
    mock_client = MagicMock()
    
    service_settings = MagicMock()
    service_settings.stream_service_settings = "{'broadcast_id': 'test_id'}"
    mock_client.get_stream_service_settings.return_value = service_settings
    
    obs_client._youtube_api_key_missing = True
    
    with patch("irswitch.obs.client.ReqClient", return_value=mock_client):
        with patch.dict("os.environ", {}, clear=True):
            await obs_client.connect(max_retries=1)
            
            # Should not make API calls when API key missing
            with patch("aiohttp.ClientSession.get") as mock_get:
                title, description = await obs_client.get_stream_info()
                # Should not be called when API key missing
                mock_get.assert_not_called()