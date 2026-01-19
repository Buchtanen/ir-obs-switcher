"""OBS websocket client wrapper."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from obsws_python import ReqClient

logger = logging.getLogger(__name__)



class ObsClient:
    """Async wrapper for OBS WebSocket client with retry logic."""

    def __init__(self, ws_url: str, password: str) -> None:
        """
        Initialize OBS client.

        Args:
            ws_url: WebSocket URL (e.g., "ws://127.0.0.1:4455")
            password: OBS WebSocket password
        """
        self.ws_url = ws_url
        self.password = password
        self._client: Optional[ReqClient] = None
        self._connected = False

    async def connect(self, max_retries: int = 5, initial_backoff: float = 1.0) -> None:
        """
        Connect to OBS WebSocket with retry and exponential backoff.

        Args:
            max_retries: Maximum number of connection attempts
            initial_backoff: Initial backoff delay in seconds
        """
        if self._connected:
            return

        # Parse URL to extract host and port
        url = self.ws_url.replace("ws://", "").replace("wss://", "")
        if ":" in url:
            host, port_str = url.split(":", 1)
            port = int(port_str)
        else:
            host = url
            port = 4455  # Default OBS WebSocket port

        backoff = initial_backoff
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                # obsws-python ReqClient is synchronous, run in thread
                def _connect() -> ReqClient:
                    return ReqClient(host=host, port=port, password=self.password)

                self._client = await asyncio.to_thread(_connect)
                self._connected = True
                logger.info(f"Connected to OBS at {host}:{port}")
                return

            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Failed to connect to OBS (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2  # Exponential backoff
                else:
                    logger.error(f"Failed to connect to OBS after {max_retries} attempts: {e}")

        raise ConnectionError(f"Could not connect to OBS: {last_error}") from last_error

    async def disconnect(self) -> None:
        """Disconnect from OBS WebSocket gracefully."""
        if self._client is not None:
            try:
                # ReqClient cleanup if needed
                self._client = None
                self._connected = False
                logger.info("Disconnected from OBS")
            except Exception as e:
                logger.warning(f"Error during OBS disconnect: {e}")

    def is_connected(self) -> bool:
        """Check if client is connected to OBS."""
        return self._connected and self._client is not None

    async def get_current_scene(self) -> Optional[str]:
        """
        Get current scene name from OBS.

        Returns:
            Scene name or None if not connected or error occurs
        """
        if not self.is_connected() or self._client is None:
            return None

        try:
            def _get_scene() -> Optional[str]:
                response = self._client.get_current_program_scene()
                if not response:
                    return None
                
                # Response is a dataclass with attributes like current_program_scene_name or scene_name
                if hasattr(response, 'current_program_scene_name'):
                    return response.current_program_scene_name
                elif hasattr(response, 'scene_name'):
                    return response.scene_name
                # Fallback for older versions that might use datain dict
                elif hasattr(response, 'datain') and isinstance(response.datain, dict):
                    return response.datain.get("currentProgramSceneName")
                
                return None

            scene = await asyncio.to_thread(_get_scene)
            return scene

        except Exception as e:
            logger.warning(f"Failed to get current scene: {e}")
            self._connected = False
            return None

    async def get_scene_list(self) -> list[str]:
        """
        Get list of all available scene names from OBS.

        Returns:
            List of scene names, empty list if not connected or error occurs
        """
        if not self.is_connected() or self._client is None:
            return []

        try:
            def _get_scenes() -> list[str]:
                response = self._client.get_scene_list()
                if not response:
                    return []
                
                # Response is a dataclass, try to get scenes list
                if hasattr(response, 'scenes'):
                    scenes = response.scenes
                    if isinstance(scenes, list):
                        # Extract scene names from scene objects
                        scene_names = []
                        for scene in scenes:
                            if hasattr(scene, 'scene_name'):
                                scene_names.append(scene.scene_name)
                            elif isinstance(scene, dict):
                                scene_names.append(scene.get("sceneName", ""))
                        return [name for name in scene_names if name]
                
                # Fallback for older versions
                if hasattr(response, 'datain') and isinstance(response.datain, dict):
                    scenes = response.datain.get("scenes", [])
                    if isinstance(scenes, list):
                        return [s.get("sceneName", "") if isinstance(s, dict) else str(s) for s in scenes if s]
                
                return []

            scenes = await asyncio.to_thread(_get_scenes)
            return scenes

        except Exception as e:
            logger.warning(f"Failed to get scene list: {e}")
            return []

    async def set_scene(self, name: str) -> bool:
        """
        Switch to specified scene in OBS (idempotent).

        Args:
            name: Scene name to switch to

        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected() or self._client is None:
            logger.warning("Cannot set scene: not connected to OBS")
            return False

        try:
            # Check current scene first (idempotent)
            current = await self.get_current_scene()
            if current == name:
                return True  # Already on target scene

            def _set_scene() -> bool:
                response = self._client.set_current_program_scene(name)
                return response is not None

            success = await asyncio.to_thread(_set_scene)
            if success:
                logger.debug(f"Switched OBS scene to: {name}")
            else:
                logger.warning(f"Failed to switch OBS scene to: {name}")
            return success

        except Exception as e:
            logger.warning(f"Error setting scene '{name}': {e}")
            self._connected = False
            return False

    async def get_current_profile(self) -> Optional[str]:
        """
        Get current OBS profile name.

        Returns:
            Profile name or None if not connected or error occurs
        """
        if not self.is_connected() or self._client is None:
            return None

        try:
            def _get_profile() -> Optional[str]:
                # OBS WebSocket v5: get_current_profile() returns current profile name
                # Try the method - it may be named differently in obsws-python
                try:
                    if hasattr(self._client, 'get_current_profile'):
                        response = self._client.get_current_profile()
                    elif hasattr(self._client, 'get_profile'):
                        response = self._client.get_profile()
                    else:
                        # Fallback: try to call it directly (might raise AttributeError)
                        response = self._client.get_current_profile()
                except AttributeError:
                    logger.warning("get_current_profile method not available in obsws-python")
                    return None
                
                if not response:
                    return None
                
                # Response is a dataclass with profile_name attribute
                if hasattr(response, 'profile_name'):
                    return response.profile_name
                elif hasattr(response, 'currentProfileName'):
                    return response.currentProfileName
                elif hasattr(response, 'profileName'):
                    return response.profileName
                # Fallback for older versions that might use datain dict
                elif hasattr(response, 'datain') and isinstance(response.datain, dict):
                    return response.datain.get("currentProfileName") or response.datain.get("profileName")
                
                return None

            profile = await asyncio.to_thread(_get_profile)
            return profile

        except Exception as e:
            logger.warning(f"Failed to get current profile: {e}")
            return None

    async def get_stream_status(self) -> tuple[bool, Optional[int]]:
        """
        Get streaming status from OBS.

        Returns:
            Tuple of (is_streaming: bool, stream_duration_ms: Optional[int])
            Returns (False, None) if not connected or error occurs
        """
        if not self.is_connected() or self._client is None:
            return (False, None)

        try:
            def _get_stream_status() -> tuple[bool, Optional[int]]:
                # Try different methods to get stream status
                response = None
                
                # Try get_stream_status() first (OBS WebSocket v5)
                try:
                    if hasattr(self._client, 'get_stream_status'):
                        response = self._client.get_stream_status()
                except Exception:
                    pass
                
                # Fallback to get_output_status() if available
                if response is None:
                    try:
                        if hasattr(self._client, 'get_output_status'):
                            response = self._client.get_output_status()
                    except Exception:
                        pass
                
                if response is None:
                    return (False, None)
                
                # Extract streaming state and duration
                is_streaming = False
                duration_ms: Optional[int] = None
                
                # Try different response formats
                if hasattr(response, 'output_active'):
                    is_streaming = bool(response.output_active)
                elif hasattr(response, 'streaming'):
                    is_streaming = bool(response.streaming)
                elif hasattr(response, 'outputActive'):
                    is_streaming = bool(response.outputActive)
                
                # Try to get duration
                if is_streaming:
                    # Try different attribute names for duration
                    if hasattr(response, 'output_duration'):
                        duration_sec = response.output_duration
                        if duration_sec:
                            duration_ms = int(duration_sec * 1000)
                    elif hasattr(response, 'outputDuration'):
                        duration_sec = response.outputDuration
                        if duration_sec:
                            duration_ms = int(duration_sec * 1000)
                    elif hasattr(response, 'duration'):
                        duration_sec = response.duration
                        if duration_sec:
                            duration_ms = int(duration_sec * 1000)
                
                # Fallback to datain dict format
                if hasattr(response, 'datain') and isinstance(response.datain, dict):
                    data = response.datain
                    is_streaming = bool(data.get("outputActive", False) or data.get("streaming", False))
                    if is_streaming:
                        duration_sec = data.get("outputDuration") or data.get("duration")
                        if duration_sec:
                            duration_ms = int(float(duration_sec) * 1000)
                
                return (is_streaming, duration_ms)

            return await asyncio.to_thread(_get_stream_status)

        except Exception as e:
            logger.debug(f"Failed to get stream status: {e}")
            return (False, None)
