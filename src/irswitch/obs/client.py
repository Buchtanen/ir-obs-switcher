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
                profile_name = None
                
                # Method 1: Try GetProfileList first (most reliable - returns currentProfileName)
                try:
                    if hasattr(self._client, 'get_profile_list'):
                        response = self._client.get_profile_list()
                        logger.debug(f"GetProfileList response: {type(response)}, {response}")
                        
                        # Try to extract currentProfileName from response
                        if response:
                            # Try attribute access
                            if hasattr(response, 'currentProfileName'):
                                profile_name = str(response.currentProfileName)
                            elif hasattr(response, 'current_profile_name'):
                                profile_name = str(response.current_profile_name)
                            elif hasattr(response, 'current_profile'):
                                profile_name = str(response.current_profile)
                            
                            # Try datain dict format
                            if not profile_name and hasattr(response, 'datain') and isinstance(response.datain, dict):
                                data = response.datain
                                profile_name = (
                                    data.get("currentProfileName") or
                                    data.get("current_profile_name") or
                                    data.get("currentProfile") or
                                    data.get("current_profile")
                                )
                                if profile_name:
                                    profile_name = str(profile_name)
                            
                            # Try if response is a dict directly
                            if not profile_name and isinstance(response, dict):
                                profile_name = (
                                    response.get("currentProfileName") or
                                    response.get("current_profile_name") or
                                    response.get("currentProfile") or
                                    response.get("current_profile")
                                )
                                if profile_name:
                                    profile_name = str(profile_name)
                            
                            if profile_name:
                                logger.info(f"Found OBS profile name via GetProfileList: {profile_name}")
                                return profile_name
                except Exception as e:
                    logger.debug(f"GetProfileList failed: {e}")
                
                # Method 2: Try GetCurrentProfile (direct request)
                try:
                    if hasattr(self._client, 'req'):
                        response = self._client.req('GetCurrentProfile')
                        logger.debug(f"Direct req('GetCurrentProfile') response: {type(response)}, {response}")
                    elif hasattr(self._client, 'call'):
                        response = self._client.call('GetCurrentProfile')
                        logger.debug(f"Direct call('GetCurrentProfile') response: {type(response)}, {response}")
                    else:
                        response = None
                    
                    if response:
                        # Try different attribute names
                        attr_names = [
                            'profile_name',
                            'currentProfileName',
                            'profileName',
                            'current_profile_name',
                            'current_profile',
                            'name',
                            'profile',
                        ]
                        
                        for attr_name in attr_names:
                            if hasattr(response, attr_name):
                                value = getattr(response, attr_name)
                                if value:
                                    profile_name = str(value)
                                    break
                        
                        # Try datain dict format
                        if not profile_name and hasattr(response, 'datain') and isinstance(response.datain, dict):
                            data = response.datain
                            profile_name = (
                                data.get("currentProfileName") or
                                data.get("profileName") or
                                data.get("current_profile_name") or
                                data.get("profile_name") or
                                data.get("name")
                            )
                            if profile_name:
                                profile_name = str(profile_name)
                        
                        # Try if response is a dict directly
                        if not profile_name and isinstance(response, dict):
                            profile_name = (
                                response.get("currentProfileName") or
                                response.get("profileName") or
                                response.get("current_profile_name") or
                                response.get("profile_name") or
                                response.get("name")
                            )
                            if profile_name:
                                profile_name = str(profile_name)
                        
                        if profile_name:
                            logger.info(f"Found OBS profile name via GetCurrentProfile: {profile_name}")
                            return profile_name
                except Exception as e:
                    logger.debug(f"GetCurrentProfile request failed: {e}")
                
                # Method 3: Try method calls
                methods_to_try = [
                    'get_current_profile',
                    'get_profile',
                    'get_current_profile_name',
                    'get_profile_name',
                ]
                
                for method_name in methods_to_try:
                    try:
                        if hasattr(self._client, method_name):
                            method = getattr(self._client, method_name)
                            response = method()
                            logger.debug(f"Method {method_name} response: {type(response)}, {response}")
                            if response:
                                # Try to extract profile name
                                if hasattr(response, 'profile_name'):
                                    profile_name = str(response.profile_name)
                                elif hasattr(response, 'currentProfileName'):
                                    profile_name = str(response.currentProfileName)
                                elif hasattr(response, 'name'):
                                    profile_name = str(response.name)
                                
                                if profile_name:
                                    logger.info(f"Found OBS profile name via {method_name}: {profile_name}")
                                    return profile_name
                    except Exception as e:
                        logger.debug(f"Method {method_name} failed: {e}")
                        continue
                
                # If all methods failed, log detailed error
                logger.warning(
                    "Could not extract OBS profile name. "
                    "Tried GetProfileList, GetCurrentProfile, and method calls. "
                    "OBS profile may not be available via WebSocket API or obsws-python version may not support it."
                )
                return None

            profile = await asyncio.to_thread(_get_profile)
            return profile

        except Exception as e:
            logger.warning(f"Failed to get current profile: {e}", exc_info=True)
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

    async def is_broadcast_ready(self) -> bool:
        """
        Check if broadcast is ready (configured but not streaming).

        Returns:
            True if broadcast is ready, False otherwise
        """
        if not self.is_connected() or self._client is None:
            return False

        try:
            def _check_ready() -> bool:
                # Check output status
                output_status = None
                try:
                    if hasattr(self._client, 'get_output_status'):
                        output_status = self._client.get_output_status()
                except Exception:
                    pass

                if output_status is None:
                    return False

                # Check if output is active or reconnecting
                output_active = False
                output_reconnecting = False
                
                if hasattr(output_status, 'output_active'):
                    output_active = bool(output_status.output_active)
                elif hasattr(output_status, 'outputActive'):
                    output_active = bool(output_status.outputActive)
                elif hasattr(output_status, 'datain') and isinstance(output_status.datain, dict):
                    output_active = bool(output_status.datain.get("outputActive", False))
                    output_reconnecting = bool(output_status.datain.get("outputReconnecting", False))

                if hasattr(output_status, 'output_reconnecting'):
                    output_reconnecting = bool(output_status.output_reconnecting)
                elif hasattr(output_status, 'outputReconnecting'):
                    output_reconnecting = bool(output_status.outputReconnecting)

                # If output is active or reconnecting, broadcast is not ready
                if output_active or output_reconnecting:
                    return False

                # Check if stream service is configured
                service_settings = None
                try:
                    if hasattr(self._client, 'get_stream_service_settings'):
                        service_settings = self._client.get_stream_service_settings()
                    elif hasattr(self._client, 'get_stream_service'):
                        service_settings = self._client.get_stream_service()
                except Exception:
                    pass

                if service_settings is None:
                    return False

                # Check if service type is set (configured)
                service_type = None
                if hasattr(service_settings, 'stream_service_type'):
                    service_type = service_settings.stream_service_type
                elif hasattr(service_settings, 'streamServiceType'):
                    service_type = service_settings.streamServiceType
                elif hasattr(service_settings, 'datain') and isinstance(service_settings.datain, dict):
                    service_type = service_settings.datain.get("streamServiceType")

                # Broadcast is ready if service is configured and not streaming
                return service_type is not None and service_type != ""

            return await asyncio.to_thread(_check_ready)

        except Exception as e:
            logger.debug(f"Failed to check broadcast ready status: {e}")
            return False

    async def start_stream(self) -> bool:
        """
        Start streaming in OBS.

        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected() or self._client is None:
            logger.warning("Cannot start stream: not connected to OBS")
            return False

        try:
            def _start() -> bool:
                try:
                    if hasattr(self._client, 'start_stream'):
                        response = self._client.start_stream()
                    else:
                        # Fallback: try direct call
                        response = self._client.start_stream()
                    return response is not None
                except Exception as e:
                    error_str = str(e).lower()
                    # If stream is already running, that's okay
                    if "already" in error_str or "running" in error_str:
                        logger.debug("Stream already running")
                        return True
                    raise

            success = await asyncio.to_thread(_start)
            if success:
                logger.info("Stream started successfully")
            else:
                logger.warning("Failed to start stream")
            return success

        except Exception as e:
            error_str = str(e).lower()
            # If stream is already running, that's okay
            if "already" in error_str or "running" in error_str:
                logger.debug("Stream already running")
                return True
            logger.warning(f"Error starting stream: {e}")
            return False

    async def stop_stream(self) -> bool:
        """
        Stop streaming in OBS.

        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected() or self._client is None:
            logger.warning("Cannot stop stream: not connected to OBS")
            return False

        try:
            def _stop() -> bool:
                try:
                    if hasattr(self._client, 'stop_stream'):
                        response = self._client.stop_stream()
                    else:
                        # Fallback: try direct call
                        response = self._client.stop_stream()
                    return response is not None
                except Exception as e:
                    error_str = str(e).lower()
                    # If stream is not running, that's okay
                    if "not running" in error_str or "not active" in error_str or "not streaming" in error_str:
                        logger.debug("Stream not running")
                        return True
                    raise

            success = await asyncio.to_thread(_stop)
            if success:
                logger.info("Stream stopped successfully")
            else:
                logger.warning("Failed to stop stream")
            return success

        except Exception as e:
            error_str = str(e).lower()
            # If stream is not running, that's okay
            if "not running" in error_str or "not active" in error_str or "not streaming" in error_str:
                logger.debug("Stream not running")
                return True
            logger.warning(f"Error stopping stream: {e}")
            return False