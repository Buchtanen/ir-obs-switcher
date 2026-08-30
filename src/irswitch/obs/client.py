"""OBS websocket client wrapper."""

from __future__ import annotations

import ast
import asyncio
import logging
import re
import threading
from typing import Any

import aiohttp
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
        # obsws_python is untyped; keep client as Any for mypy sanity.
        self._client: Any = None
        self._connected = False
        # Cache for current scene (updated only when needed)
        self._current_scene_cache: str | None = None
        self._current_scene_cache_ts: float | None = None
        self._scene_cache_ttl_s = 0.5  # Cache scene for 500ms
        # Cache for current profile (updated only when needed)
        self._current_profile_cache: str | None = None
        self._current_profile_cache_ts: float | None = None
        self._profile_cache_ttl_s = 2.0  # Cache profile for 2 seconds
        # Cache for stream info - cached until stream selection changes
        self._stream_info_cache: dict[str, str | None] | tuple[str | None, str | None] | None = None
        self._stream_info_cache_broadcast_id: str | None = None
        self._youtube_quota_exceeded: bool = (
            False  # Track if quota exceeded to avoid repeated API calls
        )
        self._youtube_api_key_missing: bool = (
            False  # Track if API key is missing to avoid repeated warnings
        )
        # Reference to OAuth manager for YouTube API access
        self._oauth_manager: Any = None  # Set externally via set_oauth_manager()
        self._stream_info_refresh_lock = asyncio.Lock()
        self._volume_lock = threading.Lock()
        # Rate-limit final-fail connect ERROR logs while OBS stays down
        self._connect_fail_streak: int = 0

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
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                # obsws-python ReqClient is synchronous, run in thread with timeout
                def _connect() -> ReqClient:
                    return ReqClient(host=host, port=port, password=self.password)

                connect_timeout_s = 5.0
                try:
                    self._client = await asyncio.wait_for(
                        asyncio.to_thread(_connect), timeout=connect_timeout_s
                    )
                except TimeoutError as e:
                    raise ConnectionError(
                        f"OBS connect timed out after {connect_timeout_s:.0f}s"
                    ) from e
                self._connected = True
                # Clear caches on new connection (profile/scene may have changed)
                self._current_scene_cache = None
                self._current_scene_cache_ts = None
                self._current_profile_cache = None
                self._current_profile_cache_ts = None
                # Clear stream info cache on reconnect (stream selection may have changed)
                self._stream_info_cache = None
                self._stream_info_cache_broadcast_id = None
                # Reset flags on reconnect (quota might have reset)
                self._youtube_quota_exceeded = False
                self._youtube_api_key_missing = False
                self._connect_fail_streak = 0
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
                    msg = f"Failed to connect to OBS after {max_retries} attempts: {e}"
                    # First final-fail after success (or cold start) stays loud;
                    # subsequent exhausted-retry cycles while OBS is down are DEBUG.
                    if self._connect_fail_streak == 0:
                        logger.error(msg)
                    else:
                        logger.debug(msg)
                    self._connect_fail_streak += 1

        raise ConnectionError(f"Could not connect to OBS: {last_error}") from last_error

    async def disconnect(self) -> None:
        """Disconnect from OBS WebSocket gracefully."""
        if self._client is not None:
            try:
                # ReqClient cleanup if needed
                self._client = None
                self._connected = False
                # Clear caches on disconnect
                self._current_scene_cache = None
                self._current_scene_cache_ts = None
                self._current_profile_cache = None
                self._current_profile_cache_ts = None
                logger.info("Disconnected from OBS")
            except Exception as e:
                logger.warning(f"Error during OBS disconnect: {e}")

    def is_connected(self) -> bool:
        """Check if client is connected to OBS."""
        return self._connected and self._client is not None

    def get_input_volume_mul(self, name: str) -> float | None:
        """Read OBS input volume (linear). Fail-soft; callable from a worker thread."""
        if not name or not self.is_connected() or self._client is None:
            return None
        try:
            with self._volume_lock:
                response = self._client.get_input_volume(name)
            mul = getattr(response, "input_volume_mul", None)
            if mul is None and hasattr(response, "datain") and isinstance(response.datain, dict):
                mul = response.datain.get("inputVolumeMul")
            if mul is None:
                return None
            return float(mul)
        except Exception as e:
            logger.warning("OBS get_input_volume failed input=%s: %s", name, e)
            return None

    def set_input_volume_mul(self, name: str, mul: float) -> bool:
        """Set OBS input volume (linear). Fail-soft; callable from a worker thread."""
        if not name or not self.is_connected() or self._client is None:
            return False
        try:
            clamped = max(0.0, min(20.0, float(mul)))
            with self._volume_lock:
                self._client.set_input_volume(name, vol_mul=clamped)
            return True
        except Exception as e:
            logger.warning("OBS set_input_volume failed input=%s: %s", name, e)
            return False

    async def get_current_scene(self, use_cache: bool = True) -> str | None:
        """
        Get current scene name from OBS.

        Uses caching to reduce system load - checks max once per 500ms.

        Args:
            use_cache: If True, use cached value if available (default: True)

        Returns:
            Scene name or None if not connected or error occurs
        """
        if not self.is_connected() or self._client is None:
            self._current_scene_cache = None
            return None

        # Use cache if available and still valid
        if use_cache:
            import time

            now = time.monotonic()
            if (
                self._current_scene_cache is not None
                and self._current_scene_cache_ts is not None
                and now - self._current_scene_cache_ts < self._scene_cache_ttl_s
            ):
                return self._current_scene_cache

        try:

            def _get_scene() -> str | None:
                response = self._client.get_current_program_scene()
                if not response:
                    return None

                # Response is a dataclass with attributes like current_program_scene_name or scene_name
                if hasattr(response, "current_program_scene_name"):
                    return str(response.current_program_scene_name)
                elif hasattr(response, "scene_name"):
                    return str(response.scene_name)
                # Fallback for older versions that might use datain dict
                elif hasattr(response, "datain") and isinstance(response.datain, dict):
                    value = response.datain.get("currentProgramSceneName")
                    return str(value) if value else None

                return None

            scene = await asyncio.to_thread(_get_scene)

            # Update cache
            import time

            self._current_scene_cache = scene
            self._current_scene_cache_ts = time.monotonic()

            return scene

        except Exception as e:
            logger.warning(f"Failed to get current scene: {e}")
            self._connected = False
            self._current_scene_cache = None
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
                if hasattr(response, "scenes"):
                    scenes = response.scenes
                    if isinstance(scenes, list):
                        # Extract scene names from scene objects
                        scene_names = []
                        for scene in scenes:
                            if hasattr(scene, "scene_name"):
                                scene_names.append(scene.scene_name)
                            elif isinstance(scene, dict):
                                scene_names.append(scene.get("sceneName", ""))
                        return [name for name in scene_names if name]

                # Fallback for older versions
                if hasattr(response, "datain") and isinstance(response.datain, dict):
                    scenes = response.datain.get("scenes", [])
                    if isinstance(scenes, list):
                        return [
                            s.get("sceneName", "") if isinstance(s, dict) else str(s)
                            for s in scenes
                            if s
                        ]

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
            # Check current scene first (idempotent) - use cache for quick check
            current = await self.get_current_scene(use_cache=True)
            if current == name:
                return True  # Already on target scene

            def _set_scene() -> bool:
                response = self._client.set_current_program_scene(name)
                return response is not None

            success = await asyncio.to_thread(_set_scene)
            if success:
                logger.debug(f"Switched OBS scene to: {name}")
                # Update cache after successful switch
                import time

                self._current_scene_cache = name
                self._current_scene_cache_ts = time.monotonic()
            else:
                logger.warning(f"Failed to switch OBS scene to: {name}")
            return success

        except Exception as e:
            logger.warning(f"Error setting scene '{name}': {e}")
            self._connected = False
            self._current_scene_cache = None
            return False

    async def get_current_profile(self, use_cache: bool = True) -> str | None:
        """
        Get current OBS profile name.

        Uses caching to reduce system load - checks max once per 2 seconds.

        Args:
            use_cache: If True, use cached value if available (default: True)

        Returns:
            Profile name or None if not connected or error occurs
        """
        if not self.is_connected() or self._client is None:
            self._current_profile_cache = None
            return None

        # Use cache if available and still valid
        if use_cache:
            import time

            now = time.monotonic()
            if (
                self._current_profile_cache is not None
                and self._current_profile_cache_ts is not None
                and now - self._current_profile_cache_ts < self._profile_cache_ttl_s
            ):
                return self._current_profile_cache

        try:

            def _get_profile() -> str | None:
                profile_name = None

                # Method 1: Try GetProfileList first (most reliable - returns currentProfileName)
                try:
                    if hasattr(self._client, "get_profile_list"):
                        response = self._client.get_profile_list()
                        logger.debug(f"GetProfileList response: {type(response)}, {response}")

                        # Try to extract currentProfileName from response
                        if response:
                            # Try attribute access
                            if hasattr(response, "currentProfileName"):
                                profile_name = str(response.currentProfileName)
                            elif hasattr(response, "current_profile_name"):
                                profile_name = str(response.current_profile_name)
                            elif hasattr(response, "current_profile"):
                                profile_name = str(response.current_profile)

                            # Try datain dict format
                            if (
                                not profile_name
                                and hasattr(response, "datain")
                                and isinstance(response.datain, dict)
                            ):
                                data = response.datain
                                profile_name = (
                                    data.get("currentProfileName")
                                    or data.get("current_profile_name")
                                    or data.get("currentProfile")
                                    or data.get("current_profile")
                                )
                                if profile_name:
                                    profile_name = str(profile_name)

                            # Try if response is a dict directly
                            if not profile_name and isinstance(response, dict):
                                profile_name = (
                                    response.get("currentProfileName")
                                    or response.get("current_profile_name")
                                    or response.get("currentProfile")
                                    or response.get("current_profile")
                                )
                                if profile_name:
                                    profile_name = str(profile_name)

                            if profile_name:
                                logger.info(
                                    f"Found OBS profile name via GetProfileList: {profile_name}"
                                )
                                return profile_name
                except Exception as e:
                    logger.debug(f"GetProfileList failed: {e}")

                # Method 2: Try GetCurrentProfile (direct request)
                try:
                    if hasattr(self._client, "req"):
                        response = self._client.req("GetCurrentProfile")
                        logger.debug(
                            f"Direct req('GetCurrentProfile') response: {type(response)}, {response}"
                        )
                    elif hasattr(self._client, "call"):
                        response = self._client.call("GetCurrentProfile")
                        logger.debug(
                            f"Direct call('GetCurrentProfile') response: {type(response)}, {response}"
                        )
                    else:
                        response = None

                    if response:
                        # Try different attribute names
                        attr_names = [
                            "profile_name",
                            "currentProfileName",
                            "profileName",
                            "current_profile_name",
                            "current_profile",
                            "name",
                            "profile",
                        ]

                        for attr_name in attr_names:
                            if hasattr(response, attr_name):
                                value = getattr(response, attr_name)
                                if value:
                                    profile_name = str(value)
                                    break

                        # Try datain dict format
                        if (
                            not profile_name
                            and hasattr(response, "datain")
                            and isinstance(response.datain, dict)
                        ):
                            data = response.datain
                            profile_name = (
                                data.get("currentProfileName")
                                or data.get("profileName")
                                or data.get("current_profile_name")
                                or data.get("profile_name")
                                or data.get("name")
                            )
                            if profile_name:
                                profile_name = str(profile_name)

                        # Try if response is a dict directly
                        if not profile_name and isinstance(response, dict):
                            profile_name = (
                                response.get("currentProfileName")
                                or response.get("profileName")
                                or response.get("current_profile_name")
                                or response.get("profile_name")
                                or response.get("name")
                            )
                            if profile_name:
                                profile_name = str(profile_name)

                        if profile_name:
                            logger.info(
                                f"Found OBS profile name via GetCurrentProfile: {profile_name}"
                            )
                            return profile_name
                except Exception as e:
                    logger.debug(f"GetCurrentProfile request failed: {e}")

                # Method 3: Try method calls
                methods_to_try = [
                    "get_current_profile",
                    "get_profile",
                    "get_current_profile_name",
                    "get_profile_name",
                ]

                for method_name in methods_to_try:
                    try:
                        if hasattr(self._client, method_name):
                            method = getattr(self._client, method_name)
                            response = method()
                            logger.debug(
                                f"Method {method_name} response: {type(response)}, {response}"
                            )
                            if response:
                                # Try to extract profile name
                                if hasattr(response, "profile_name"):
                                    profile_name = str(response.profile_name)
                                elif hasattr(response, "currentProfileName"):
                                    profile_name = str(response.currentProfileName)
                                elif hasattr(response, "name"):
                                    profile_name = str(response.name)

                                if profile_name:
                                    logger.info(
                                        f"Found OBS profile name via {method_name}: {profile_name}"
                                    )
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

            # Update cache
            import time

            self._current_profile_cache = profile
            self._current_profile_cache_ts = time.monotonic()

            return profile

        except Exception as e:
            logger.warning(f"Failed to get current profile: {e}", exc_info=True)
            self._current_profile_cache = None
            return None

    async def get_stream_status(self) -> tuple[bool, int | None]:
        """
        Get streaming status from OBS.

        Returns:
            Tuple of (is_streaming: bool, stream_duration_ms: Optional[int])
            Returns (False, None) if not connected or error occurs
        """
        if not self.is_connected() or self._client is None:
            return (False, None)

        try:

            def _get_stream_status() -> tuple[bool, int | None]:
                # Try different methods to get stream status
                response = None

                # Try get_stream_status() first (OBS WebSocket v5)
                try:
                    if hasattr(self._client, "get_stream_status"):
                        response = self._client.get_stream_status()
                except Exception:
                    pass

                # Fallback to get_output_status() if available
                if response is None:
                    try:
                        if hasattr(self._client, "get_output_status"):
                            response = self._client.get_output_status()
                    except Exception:
                        pass

                if response is None:
                    return (False, None)

                # Extract streaming state and duration
                is_streaming = False
                duration_ms: int | None = None

                # Try different response formats
                if hasattr(response, "output_active"):
                    is_streaming = bool(response.output_active)
                elif hasattr(response, "streaming"):
                    is_streaming = bool(response.streaming)
                elif hasattr(response, "outputActive"):
                    is_streaming = bool(response.outputActive)

                # Try to get duration
                if is_streaming:
                    # Try different attribute names for duration
                    if hasattr(response, "output_duration"):
                        duration_sec = response.output_duration
                        if duration_sec:
                            duration_ms = int(duration_sec * 1000)
                    elif hasattr(response, "outputDuration"):
                        duration_sec = response.outputDuration
                        if duration_sec:
                            duration_ms = int(duration_sec * 1000)
                    elif hasattr(response, "duration"):
                        duration_sec = response.duration
                        if duration_sec:
                            duration_ms = int(duration_sec * 1000)

                # Fallback to datain dict format
                if hasattr(response, "datain") and isinstance(response.datain, dict):
                    data = response.datain
                    is_streaming = bool(
                        data.get("outputActive", False) or data.get("streaming", False)
                    )
                    if is_streaming:
                        duration_sec = data.get("outputDuration") or data.get("duration")
                        if duration_sec:
                            duration_ms = int(float(duration_sec) * 1000)

                return (is_streaming, duration_ms)

            return await asyncio.to_thread(_get_stream_status)

        except Exception as e:
            logger.debug(f"Failed to get stream status: {e}")
            return (False, None)

    @staticmethod
    def _extract_broadcast_id_from_settings_value(
        stream_settings: Any,
    ) -> str | None:
        """Extract broadcast_id from GetStreamServiceSettings payload (dict or str)."""
        if isinstance(stream_settings, dict):
            return stream_settings.get("broadcast_id") or stream_settings.get("broadcastId")
        if isinstance(stream_settings, str):
            try:
                stream_settings_dict = ast.literal_eval(stream_settings)
                if isinstance(stream_settings_dict, dict):
                    return stream_settings_dict.get("broadcast_id") or stream_settings_dict.get(
                        "broadcastId"
                    )
            except Exception:
                broadcast_match = re.search(
                    r"['\"]broadcast_id['\"]:\s*['\"]([^'\"]+)['\"]",
                    stream_settings,
                )
                if broadcast_match:
                    return broadcast_match.group(1)
        return None

    def _peek_broadcast_id_sync(self) -> str | None:
        """Sync peek of current broadcast_id from OBS GetStreamServiceSettings."""
        try:
            if self._client is None or not hasattr(self._client, "get_stream_service_settings"):
                return None
            service_settings = self._client.get_stream_service_settings()
            if not service_settings or not hasattr(service_settings, "stream_service_settings"):
                return None
            return self._extract_broadcast_id_from_settings_value(
                service_settings.stream_service_settings
            )
        except Exception:
            return None

    async def get_current_broadcast_id(self) -> str | None:
        """Cheap peek of current OBS broadcast_id (no YouTube API)."""
        if not self.is_connected() or self._client is None:
            return None
        try:
            return await asyncio.to_thread(self._peek_broadcast_id_sync)
        except Exception:
            return None

    async def get_stream_info(self, force_refresh: bool = False) -> tuple[str | None, str | None]:
        """
        Get current stream information from OBS and YouTube API.

        Uses cache to avoid excessive API calls. Only fetches when:
        - force_refresh=True
        - Cache is empty
        - Broadcast ID changed (stream selection changed)

        Tries multiple methods:
        1. OBS WebSocket API (GetStreamServiceSettings)
        2. YouTube Data API via OAuth (if broadcast_id and OAuth are available)

        Returns:
            Tuple of (title: Optional[str], description: Optional[str])
        """
        if not self.is_connected() or self._client is None:
            return (None, None)

        try:
            # Check cache first (unless force refresh or quota exceeded)
            if not force_refresh and not self._youtube_quota_exceeded:
                # Get current broadcast_id to check if stream selection changed
                try:
                    current_broadcast_id = await asyncio.to_thread(self._peek_broadcast_id_sync)

                    # If broadcast_id changed, reset quota flag (new stream might have different status)
                    if current_broadcast_id != self._stream_info_cache_broadcast_id:
                        self._youtube_quota_exceeded = False

                    # If cache exists and broadcast_id matches, return cached result
                    if (
                        self._stream_info_cache is not None
                        and current_broadcast_id == self._stream_info_cache_broadcast_id
                    ):
                        # Extract title and description from cache (can be dict or tuple)
                        if isinstance(self._stream_info_cache, dict):
                            return (
                                self._stream_info_cache.get("title"),
                                self._stream_info_cache.get("description"),
                            )
                        elif isinstance(self._stream_info_cache, tuple):
                            return (
                                (
                                    self._stream_info_cache[0]
                                    if len(self._stream_info_cache) > 0
                                    else None
                                ),
                                (
                                    self._stream_info_cache[1]
                                    if len(self._stream_info_cache) > 1
                                    else None
                                ),
                            )
                        else:
                            return (None, None)
                except Exception:
                    pass  # If cache check fails, continue with normal fetch

            async def _get_stream_info_async() -> tuple[str | None, str | None]:
                # Initialize result
                title_result: str | None = None
                description_result: str | None = None
                stream_status: str | None = None
                privacy_status: str | None = None
                scheduled_start_time: str | None = None

                # Run synchronous part in thread
                def _get_stream_info_sync() -> tuple[str | None, str | None, str | None]:

                    # Log all available methods on the client

                    # Try GetStreamServiceSettings - use get_stream_service_settings() directly
                    service_settings_full = None
                    try:
                        if hasattr(self._client, "get_stream_service_settings"):
                            service_settings_full = self._client.get_stream_service_settings()
                    except Exception:
                        pass

                    # Try call() method with GetStreamServiceSettings
                    try:
                        if hasattr(self._client, "call"):
                            self._client.call("GetStreamServiceSettings")
                    except Exception:
                        pass

                    # Try GetBroadcastStatus if available
                    try:
                        if hasattr(self._client, "get_broadcast_status"):
                            self._client.get_broadcast_status()
                        elif hasattr(self._client, "call"):
                            try:
                                self._client.call("GetBroadcastStatus")
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"Error getting broadcast_status: {e}")
                        pass

                    # Parse stream_service_settings string to dict
                    stream_settings_dict = None
                    try:
                        if service_settings_full and hasattr(
                            service_settings_full, "stream_service_settings"
                        ):
                            stream_settings_str = service_settings_full.stream_service_settings
                            if isinstance(stream_settings_str, str):
                                # Try to parse as Python dict string representation
                                try:
                                    stream_settings_dict = ast.literal_eval(stream_settings_str)
                                except Exception:
                                    # If ast.literal_eval fails, try regex extraction
                                    pass
                            elif isinstance(stream_settings_str, dict):
                                stream_settings_dict = stream_settings_str
                    except Exception as e:
                        logger.debug(f"Error parsing stream_service_settings: {e}")

                    # First, try to get broadcast_id to identify the selected stream
                    broadcast_id = None
                    try:
                        if stream_settings_dict and isinstance(stream_settings_dict, dict):
                            broadcast_id = stream_settings_dict.get(
                                "broadcast_id"
                            ) or stream_settings_dict.get("broadcastId")
                        elif service_settings_full:
                            if hasattr(service_settings_full, "stream_service_settings"):
                                stream_settings = service_settings_full.stream_service_settings
                                if isinstance(stream_settings, str):
                                    # Try regex to extract broadcast_id
                                    broadcast_match = re.search(
                                        r"['\"]broadcast_id['\"]:\s*['\"]([^'\"]+)['\"]",
                                        stream_settings,
                                    )
                                    if broadcast_match:
                                        broadcast_id = broadcast_match.group(1)
                            elif hasattr(service_settings_full, "datain") and isinstance(
                                service_settings_full.datain, dict
                            ):
                                data = service_settings_full.datain
                                if "streamServiceSettings" in data:
                                    sss = data["streamServiceSettings"]
                                    if isinstance(sss, dict):
                                        broadcast_id = sss.get("broadcast_id") or sss.get(
                                            "broadcastId"
                                        )
                                    elif isinstance(sss, str):
                                        broadcast_match = re.search(
                                            r"['\"]broadcast_id['\"]:\s*['\"]([^'\"]+)['\"]",
                                            sss,
                                        )
                                        if broadcast_match:
                                            broadcast_id = broadcast_match.group(1)
                    except Exception as e:
                        logger.debug(f"Error extracting broadcast_id: {e}")

                    # Try multiple methods to get stream title
                    title = None

                    # Method 1: Try to get from stream service settings (using already fetched service_settings_full)
                    try:
                        service_settings = service_settings_full
                        if service_settings is None:
                            if hasattr(self._client, "get_stream_service_settings"):
                                service_settings = self._client.get_stream_service_settings()
                            elif hasattr(self._client, "get_stream_service"):
                                service_settings = self._client.get_stream_service()

                        if service_settings is not None:

                            # Check direct attributes
                            if hasattr(service_settings, "stream_title"):
                                title = service_settings.stream_title
                                logger.debug(f"Found title in stream_title: {title}")
                            elif hasattr(service_settings, "streamTitle"):
                                title = service_settings.streamTitle
                                logger.debug(f"Found title in streamTitle: {title}")
                            elif hasattr(service_settings, "title"):
                                title = service_settings.title
                                logger.debug(f"Found title in title: {title}")

                            # Check settings dict
                            if (
                                title is None
                                and hasattr(service_settings, "settings")
                                and isinstance(service_settings.settings, dict)
                            ):
                                title = service_settings.settings.get(
                                    "streamTitle"
                                ) or service_settings.settings.get("title")
                                if title:
                                    logger.debug(f"Found title in settings dict: {title}")

                            # Check datain dict format
                            if (
                                title is None
                                and hasattr(service_settings, "datain")
                                and isinstance(service_settings.datain, dict)
                            ):
                                data = service_settings.datain
                                logger.debug(f"datain keys: {list(data.keys())}")
                                title = data.get("streamTitle") or data.get("title")
                                # Also check nested settings
                                if (
                                    title is None
                                    and "settings" in data
                                    and isinstance(data["settings"], dict)
                                ):
                                    logger.debug(f"settings keys: {list(data['settings'].keys())}")
                                    title = data["settings"].get("streamTitle") or data[
                                        "settings"
                                    ].get("title")
                                # Check streamServiceSettings nested
                                if title is None and "streamServiceSettings" in data:
                                    sss = data["streamServiceSettings"]
                                    if isinstance(sss, dict):
                                        title = sss.get("title") or sss.get("streamTitle")
                                    elif isinstance(sss, str):
                                        # Try regex to extract title
                                        title_match = re.search(
                                            r"['\"]title['\"]:\s*['\"]([^'\"]+)['\"]",
                                            sss,
                                        )
                                        if title_match:
                                            title = title_match.group(1)
                                if title:
                                    logger.debug(f"Found title in datain: {title}")
                    except Exception as e:
                        logger.debug(f"Error getting service settings: {e}", exc_info=True)

                    # Method 2: Try to get from output settings (some OBS versions store title here)
                    if title is None:
                        try:
                            if hasattr(self._client, "get_output_settings"):
                                output_settings = self._client.get_output_settings()
                                if output_settings:
                                    if hasattr(output_settings, "stream_title"):
                                        title = output_settings.stream_title
                                    elif hasattr(output_settings, "streamTitle"):
                                        title = output_settings.streamTitle
                                    elif hasattr(output_settings, "datain") and isinstance(
                                        output_settings.datain, dict
                                    ):
                                        title = output_settings.datain.get(
                                            "streamTitle"
                                        ) or output_settings.datain.get("title")
                        except Exception:
                            pass

                    # Method 3: Try to get from stream metadata (if available)
                    if title is None:
                        try:
                            if hasattr(self._client, "get_stream_metadata"):
                                metadata = self._client.get_stream_metadata()
                                if metadata:
                                    logger.debug(f"Stream metadata type: {type(metadata)}")
                                    if hasattr(metadata, "title"):
                                        title = metadata.title
                                        logger.debug(f"Found title in metadata.title: {title}")
                                    elif hasattr(metadata, "datain") and isinstance(
                                        metadata.datain, dict
                                    ):
                                        logger.debug(
                                            f"Metadata datain keys: {list(metadata.datain.keys())}"
                                        )
                                        title = metadata.datain.get("title")
                                        if title:
                                            logger.debug(f"Found title in metadata.datain: {title}")
                        except Exception as e:
                            logger.debug(f"Error getting stream metadata: {e}")

                    # Method 4: Try to get title from stream_settings_dict (which we already parsed)
                    # Note: OBS WebSocket API doesn't store YouTube broadcast title in stream settings,
                    # but we check here in case it's somehow present
                    if title is None:
                        try:
                            if stream_settings_dict and isinstance(stream_settings_dict, dict):
                                # Check for title in stream_settings_dict (unlikely but possible)
                                title = stream_settings_dict.get(
                                    "title"
                                ) or stream_settings_dict.get("streamTitle")
                                if title:
                                    logger.debug(f"Found title in stream_settings_dict: {title}")
                        except Exception as e:
                            logger.debug(
                                f"Error getting title from stream_settings_dict in Method 4: {e}"
                            )

                    # Try to get title and description from parsed stream_settings_dict
                    # Note: OBS WebSocket API doesn't directly provide YouTube broadcast title/description
                    # These are stored in YouTube Broadcast Manager, not in OBS stream settings
                    # We can only get them if they're somehow stored in stream_service_settings
                    description = None
                    try:
                        if stream_settings_dict and isinstance(stream_settings_dict, dict):
                            # Try to get title if not already found
                            if title is None:
                                title = stream_settings_dict.get(
                                    "title"
                                ) or stream_settings_dict.get("streamTitle")
                            description = stream_settings_dict.get(
                                "description"
                            ) or stream_settings_dict.get("streamDescription")
                    except Exception as e:
                        logger.debug(f"Error getting title/description from parsed dict: {e}")

                    # Note: Vendor requests removed - they don't work (all fail with code 600 "No vendor found")
                    # YouTube Data API fallback is used instead (see async part below)

                    # Return title and description if found

                    final_title = None
                    if title and isinstance(title, str) and title.strip():
                        final_title = title.strip()

                    final_description = None
                    if description and isinstance(description, str) and description.strip():
                        final_description = description.strip()

                    return (final_title, final_description, broadcast_id)

                # Run synchronous part
                sync_result = await asyncio.to_thread(_get_stream_info_sync)

                title, description, broadcast_id = sync_result

                # Update result with title and description from sync part
                title_result = title
                description_result = description

                # Log what we found in sync part
                if title:
                    logger.debug(f"Stream title found via OBS API: {title}")
                else:
                    logger.debug(
                        f"No stream title found via OBS API (broadcast_id: {broadcast_id})"
                    )

                # Now fetch extended info from YouTube API if we have broadcast_id and OAuth
                if broadcast_id and self._oauth_manager:
                    # Check if OAuth is actually authenticated before making API calls
                    if not self._oauth_manager.is_authenticated():
                        logger.debug(
                            "OAuth manager exists but not authenticated - skipping YouTube API call"
                        )
                    else:
                        try:
                            from irswitch.oauth import OAuthError, OAuthReauthRequired

                            logger.debug(
                                f"Fetching stream info from YouTube API for broadcast_id: {broadcast_id}"
                            )
                            async with aiohttp.ClientSession() as session:
                                access_token = await self._oauth_manager.get_valid_access_token(
                                    session
                                )

                                # Fetch liveBroadcasts with snippet, status, and contentDetails parts
                                live_broadcasts_url = (
                                    "https://www.googleapis.com/youtube/v3/liveBroadcasts"
                                )
                                params = {
                                    "part": "snippet,status,contentDetails",
                                    "id": broadcast_id,
                                }

                                headers = {"Authorization": f"Bearer {access_token}"}
                                async with session.get(
                                    live_broadcasts_url, params=params, headers=headers
                                ) as response:
                                    if response.status == 200:
                                        try:
                                            data = await response.json()
                                            if "items" in data and len(data["items"]) > 0:
                                                broadcast = data["items"][0]

                                                # Get snippet data
                                                if "snippet" in broadcast:
                                                    snippet = broadcast["snippet"]
                                                    if title_result is None and "title" in snippet:
                                                        title_result = snippet["title"]
                                                    if (
                                                        description_result is None
                                                        and "description" in snippet
                                                    ):
                                                        description_result = snippet.get(
                                                            "description"
                                                        )

                                                # Get status data (lifeCycleStatus, privacyStatus)
                                                stream_status = None
                                                privacy_status = None
                                                if "status" in broadcast:
                                                    status_obj = broadcast["status"]
                                                    stream_status = status_obj.get(
                                                        "lifeCycleStatus"
                                                    )
                                                    privacy_status = status_obj.get("privacyStatus")

                                                # Get scheduled start time from snippet
                                                scheduled_start_time = None
                                                if "snippet" in broadcast:
                                                    snippet = broadcast["snippet"]
                                                    scheduled_start_time = snippet.get(
                                                        "scheduledStartTime"
                                                    )

                                                # Try to get concurrent viewers from videos.list API
                                                # For live broadcasts, we need to find the associated video_id
                                                # The broadcast_id might be the video_id when the broadcast is live
                                                # Or we can get video_id from contentDetails.monitorStream.broadcastStreamId
                                                video_id_for_viewers = None

                                                # Try to get video_id from broadcast contentDetails
                                                if "contentDetails" in broadcast:
                                                    # When broadcast is live, there might be a video_id
                                                    # For now, try using broadcast_id as video_id
                                                    video_id_for_viewers = broadcast_id

                                                # Try to get concurrent viewers using video_id
                                                if video_id_for_viewers:
                                                    videos_url = "https://www.googleapis.com/youtube/v3/videos"
                                                    videos_params = {
                                                        "part": "liveStreamingDetails",
                                                        "id": video_id_for_viewers,
                                                    }
                                                    async with session.get(
                                                        videos_url,
                                                        params=videos_params,
                                                        headers=headers,
                                                    ) as videos_response:
                                                        if videos_response.status == 200:
                                                            try:
                                                                videos_data = (
                                                                    await videos_response.json()
                                                                )
                                                                if (
                                                                    "items" in videos_data
                                                                    and len(videos_data["items"])
                                                                    > 0
                                                                ):
                                                                    # concurrent_viewers not returned in tuple format
                                                                    pass
                                                            except Exception as e:
                                                                logger.debug(
                                                                    f"Failed to get concurrent viewers: {e}"
                                                                )
                                                        elif videos_response.status == 404:
                                                            # broadcast_id is not a video_id, concurrent viewers not available
                                                            logger.debug(
                                                                f"broadcast_id {broadcast_id} is not a video_id, concurrent viewers not available"
                                                            )
                                        except Exception as e:
                                            logger.debug(f"YouTube OAuth API error: {e}")
                                    elif response.status == 403:
                                        error_data = await response.json()
                                        error_reason = (
                                            error_data.get("error", {})
                                            .get("errors", [{}])[0]
                                            .get("reason", "")
                                        )
                                        if (
                                            error_reason == "quotaExceeded"
                                            or "quota" in str(error_data).lower()
                                        ):
                                            self._youtube_quota_exceeded = True
                                            logger.warning("YouTube API quota exceeded via OAuth")
                                    elif response.status == 401:
                                        # Token expired, try to refresh
                                        try:
                                            await self._oauth_manager.refresh_access_token(session)
                                            logger.debug(
                                                "OAuth token refreshed, will retry on next call"
                                            )
                                        except OAuthReauthRequired as e:
                                            logger.warning(
                                                "OAuth reauth required after 401 refresh: %s", e
                                            )
                                            self._oauth_manager.request_interactive_reauth(
                                                "youtube_api_401_invalid_grant"
                                            )
                                        except OAuthError:
                                            logger.warning("OAuth token refresh failed")
                        except OAuthReauthRequired as e:
                            # Interactive reauth already requested inside get_valid_access_token
                            logger.warning(
                                "Skipping YouTube stream info until OAuth reauth completes: %s", e
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to fetch extended stream info via OAuth: {e}",
                                exc_info=True,
                            )
                else:
                    if not broadcast_id:
                        logger.debug(
                            "No broadcast_id available - cannot fetch stream info from YouTube API"
                        )
                    elif not self._oauth_manager:
                        logger.debug(
                            "No OAuth manager set - cannot fetch stream info from YouTube API"
                        )

                # Update cache (store as dict to include extended info)
                # Only update cache if we have new data OR broadcast_id changed
                # Don't overwrite existing cache with None values if broadcast_id is the same
                cache_dict = {
                    "title": title_result,
                    "description": description_result,
                    "status": stream_status,
                    "privacy_status": privacy_status,
                    "scheduled_start_time": scheduled_start_time,
                }

                if broadcast_id != self._stream_info_cache_broadcast_id:
                    # Broadcast ID changed - always update cache (even if None, stream selection changed)
                    self._stream_info_cache = cache_dict
                    self._stream_info_cache_broadcast_id = broadcast_id
                    logger.debug(
                        f"Cache updated: broadcast_id changed to {broadcast_id}, title: {title_result}, status: {stream_status}, privacy: {privacy_status}"
                    )
                elif (
                    title_result is not None
                    or description_result is not None
                    or stream_status is not None
                    or privacy_status is not None
                ):
                    # Same broadcast_id but we have new data - update cache
                    # Merge with existing cache to preserve any fields that weren't updated
                    if isinstance(self._stream_info_cache, dict):
                        cache_dict.update(self._stream_info_cache)
                    self._stream_info_cache = cache_dict
                    logger.debug(
                        f"Cache updated: new data for broadcast_id {broadcast_id}, title: {title_result}, status: {stream_status}, privacy: {privacy_status}"
                    )
                else:
                    # Same broadcast_id, no new data - keep existing cache
                    if self._stream_info_cache is not None:
                        logger.debug(
                            f"Cache preserved: no new data for broadcast_id {broadcast_id}, keeping existing cache"
                        )
                        # Return cached values instead of None
                        if isinstance(self._stream_info_cache, tuple):
                            title_result = (
                                self._stream_info_cache[0]
                                if len(self._stream_info_cache) > 0
                                else None
                            )
                            description_result = (
                                self._stream_info_cache[1]
                                if len(self._stream_info_cache) > 1
                                else None
                            )
                        elif isinstance(self._stream_info_cache, dict):
                            title_result = self._stream_info_cache.get("title")
                            description_result = self._stream_info_cache.get("description")

                return (title_result, description_result)

            result = await _get_stream_info_async()

            return result

        except Exception as e:
            logger.warning(f"Failed to get stream info: {e}", exc_info=True)
            return (None, None)

    async def get_stream_title(self) -> str | None:
        """
        Get current stream title from OBS.

        Returns:
            Stream title string if available, None otherwise
        """
        title, _ = await self.get_stream_info()
        return title

    def set_oauth_manager(self, oauth_manager) -> None:
        """Set the OAuth manager for YouTube API access."""
        self._oauth_manager = oauth_manager

    def clear_stream_info_cache(self) -> None:
        """Clear cached stream title/description so the next fetch hits OBS/YouTube."""
        self._stream_info_cache = None
        self._stream_info_cache_broadcast_id = None
        logger.debug("Stream info cache cleared")

    async def refresh_stream_info(
        self, reason: str = "", *, force: bool = True
    ) -> tuple[str | None, str | None]:
        """
        Single ownership path for stream-info refresh (main loop, API, OAuth).

        Serializes concurrent callers with a lock so clear+fetch cannot interleave.
        """
        async with self._stream_info_refresh_lock:
            if reason:
                logger.info("Refreshing stream info (%s)", reason)
            else:
                logger.debug("Refreshing stream info")
            if force:
                self.clear_stream_info_cache()
            return await self.get_stream_info(force_refresh=force)

    def get_cached_stream_info(self) -> tuple[str | None, str | None, bool, bool]:
        """
        Get cached stream info without making API calls.

        For backward compatibility, returns tuple format.

        Returns:
            Tuple of (title: Optional[str], description: Optional[str], quota_exceeded: bool, api_key_missing: bool)
        """
        if self._stream_info_cache is not None:
            # Cache is stored as tuple (title, description)
            if isinstance(self._stream_info_cache, tuple):
                title = self._stream_info_cache[0] if len(self._stream_info_cache) > 0 else None
                description = (
                    self._stream_info_cache[1] if len(self._stream_info_cache) > 1 else None
                )
            elif isinstance(self._stream_info_cache, dict):
                # Backward compatibility with dict format
                title = self._stream_info_cache.get("title")
                description = self._stream_info_cache.get("description")
            else:
                title = None
                description = None
            return (
                title,
                description,
                self._youtube_quota_exceeded,
                self._youtube_api_key_missing,
            )
        return (None, None, self._youtube_quota_exceeded, self._youtube_api_key_missing)

    def get_cached_stream_info_full(self) -> dict[str, str | None] | None:
        """
        Get full cached stream info without making API calls.

        Returns:
            Dict with all stream info fields or None if not cached
        """
        if isinstance(self._stream_info_cache, dict):
            return self._stream_info_cache
        if isinstance(self._stream_info_cache, tuple):
            title = self._stream_info_cache[0] if len(self._stream_info_cache) > 0 else None
            description = self._stream_info_cache[1] if len(self._stream_info_cache) > 1 else None
            return {"title": title, "description": description}
        return None

    def get_cached_broadcast_id(self) -> str | None:
        """Return last known OBS/YouTube broadcast_id from stream info cache."""
        return self._stream_info_cache_broadcast_id

    async def is_stream_selected(self) -> tuple[bool, bool]:
        """
        Check if stream is selected/active (not just defined) in OBS Broadcast Manager.

        Returns:
            Tuple of (is_selected: bool, is_ready: bool)
            - is_selected: True if stream is selected/active (not just defined)
            - is_ready: True if stream is ready to stream (selected and configured)
        """
        if not self.is_connected() or self._client is None:
            return (False, False)

        try:

            def _check_selected() -> tuple[bool, bool]:

                # Step 1: Check if already streaming
                is_streaming = False
                stream_status = None
                try:
                    if hasattr(self._client, "get_stream_status"):
                        stream_status = self._client.get_stream_status()
                        if stream_status is not None:
                            if hasattr(stream_status, "output_active"):
                                is_streaming = bool(stream_status.output_active)
                            elif hasattr(stream_status, "outputActive"):
                                is_streaming = bool(stream_status.outputActive)
                            elif hasattr(stream_status, "datain") and isinstance(
                                stream_status.datain, dict
                            ):
                                is_streaming = bool(stream_status.datain.get("outputActive", False))
                except Exception:
                    pass

                # If streaming, stream is definitely selected
                if is_streaming:
                    return (True, True)

                # Step 2: Check stream service settings to see if stream is selected
                service_settings = None
                try:
                    if hasattr(self._client, "get_stream_service_settings"):
                        service_settings = self._client.get_stream_service_settings()
                    elif hasattr(self._client, "get_stream_service"):
                        service_settings = self._client.get_stream_service()
                except Exception:
                    pass

                if service_settings is None:
                    return (False, False)

                # Check if service type is set (configured)
                service_type = None
                if hasattr(service_settings, "stream_service_type"):
                    service_type = service_settings.stream_service_type
                elif hasattr(service_settings, "streamServiceType"):
                    service_type = service_settings.streamServiceType
                elif hasattr(service_settings, "datain") and isinstance(
                    service_settings.datain, dict
                ):
                    service_type = service_settings.datain.get("streamServiceType")

                # Check for stream key or other indicators that stream is actually selected/active
                # A stream that is only "defined" won't have stream key set
                stream_key = None
                broadcast_id = None

                # Try to get stream_service_settings dict
                stream_service_settings_dict = None
                if hasattr(service_settings, "stream_service_settings"):
                    stream_service_settings_dict = service_settings.stream_service_settings
                elif hasattr(service_settings, "streamServiceSettings"):
                    stream_service_settings_dict = service_settings.streamServiceSettings
                elif hasattr(service_settings, "datain") and isinstance(
                    service_settings.datain, dict
                ):
                    stream_service_settings_dict = service_settings.datain.get(
                        "streamServiceSettings"
                    ) or service_settings.datain.get("stream_service_settings")

                # Extract key and broadcast_id from stream_service_settings
                if stream_service_settings_dict:
                    if isinstance(stream_service_settings_dict, dict):
                        stream_key = stream_service_settings_dict.get(
                            "key"
                        ) or stream_service_settings_dict.get("streamKey")
                        broadcast_id = stream_service_settings_dict.get(
                            "broadcast_id"
                        ) or stream_service_settings_dict.get("broadcastId")
                    elif isinstance(stream_service_settings_dict, str):
                        # Try to parse if it's a string representation
                        # The string might be like "{'broadcast_id': 'Ew3yOcL0e5s', 'key': 'yc5y-3hfq-msah-c2fx-f2jj', ...}"
                        try:
                            import ast

                            # Replace single quotes with double quotes for JSON-like parsing, or use ast.literal_eval
                            parsed = ast.literal_eval(stream_service_settings_dict)
                            if isinstance(parsed, dict):
                                stream_key = parsed.get("key") or parsed.get("streamKey")
                                broadcast_id = parsed.get("broadcast_id") or parsed.get(
                                    "broadcastId"
                                )
                        except Exception:
                            # If ast.literal_eval fails, try regex to extract key and broadcast_id
                            # Extract key: 'key': 'value' or "key": "value"
                            key_match = re.search(
                                r"['\"]key['\"]:\s*['\"]([^'\"]+)['\"]",
                                stream_service_settings_dict,
                            )
                            if key_match:
                                stream_key = key_match.group(1)
                            # Extract broadcast_id: 'broadcast_id': 'value' or "broadcast_id": "value"
                            broadcast_match = re.search(
                                r"['\"]broadcast_id['\"]:\s*['\"]([^'\"]+)['\"]",
                                stream_service_settings_dict,
                            )
                            if broadcast_match:
                                broadcast_id = broadcast_match.group(1)

                # Fallback: try direct attributes
                if not stream_key:
                    if hasattr(service_settings, "stream_key"):
                        stream_key = service_settings.stream_key
                    elif hasattr(service_settings, "streamKey"):
                        stream_key = service_settings.streamKey
                    elif hasattr(service_settings, "key"):
                        stream_key = service_settings.key

                # Fallback: try datain
                if (
                    not stream_key
                    and hasattr(service_settings, "datain")
                    and isinstance(service_settings.datain, dict)
                ):
                    stream_key = service_settings.datain.get(
                        "streamKey"
                    ) or service_settings.datain.get("key")
                    broadcast_id = service_settings.datain.get(
                        "broadcast_id"
                    ) or service_settings.datain.get("broadcastId")
                    # Also check nested settings
                    if (
                        not stream_key
                        and "settings" in service_settings.datain
                        and isinstance(service_settings.datain["settings"], dict)
                    ):
                        stream_key = service_settings.datain["settings"].get(
                            "streamKey"
                        ) or service_settings.datain["settings"].get("key")
                        broadcast_id = service_settings.datain["settings"].get(
                            "broadcast_id"
                        ) or service_settings.datain["settings"].get("broadcastId")

                # Stream is selected/active ONLY if:
                # 1. Streaming is active (definitely selected)
                # OR
                # 2. Service type is set AND (stream key OR broadcast_id is set) - indicates stream is actually selected
                #
                # NOTE: We cannot rely on just YouTube RTMPS service being configured, as that only means
                # the service type is set, not that a specific stream is selected in Broadcast Manager.
                # OBS WebSocket API does not provide broadcast_id/key until stream is actually selected/ready.
                has_stream_info = (stream_key is not None and stream_key != "") or (
                    broadcast_id is not None and broadcast_id != ""
                )

                # Stream is selected ONLY if streaming OR has actual stream info (key/broadcast_id)
                is_selected = is_streaming or (
                    (service_type is not None and service_type != "") and has_stream_info
                )
                is_ready = is_selected and not is_streaming

                return (is_selected, is_ready)

            return await asyncio.to_thread(_check_selected)

        except Exception as e:
            logger.warning(f"Failed to check if stream is selected: {e}", exc_info=True)
            return (False, False)

    async def is_broadcast_ready(self) -> bool:
        """
        Check if broadcast is ready (configured but not streaming).

        Uses get_stream_status() to check if streaming, and get_stream_service_settings()
        to check if stream service is configured.

        Returns:
            True if broadcast is ready (configured and not streaming), False otherwise
        """
        if not self.is_connected() or self._client is None:
            return False

        try:

            def _check_ready() -> bool:
                # Step 1: Check if already streaming using get_stream_status()
                is_streaming = False
                stream_status = None
                try:
                    if hasattr(self._client, "get_stream_status"):
                        stream_status = self._client.get_stream_status()
                        if stream_status is not None:
                            # Extract streaming state from response
                            if hasattr(stream_status, "output_active"):
                                is_streaming = bool(stream_status.output_active)
                            elif hasattr(stream_status, "outputActive"):
                                is_streaming = bool(stream_status.outputActive)
                            elif hasattr(stream_status, "datain") and isinstance(
                                stream_status.datain, dict
                            ):
                                is_streaming = bool(stream_status.datain.get("outputActive", False))
                except Exception:
                    pass

                # If already streaming, broadcast is not "ready to start"
                if is_streaming:
                    return False

                # Step 2: Check if stream service is configured
                service_settings = None
                try:
                    if hasattr(self._client, "get_stream_service_settings"):
                        service_settings = self._client.get_stream_service_settings()
                    elif hasattr(self._client, "get_stream_service"):
                        service_settings = self._client.get_stream_service()
                except Exception:
                    pass

                if service_settings is None:
                    return False

                # Check if service type is set (configured)
                service_type = None
                if hasattr(service_settings, "stream_service_type"):
                    service_type = service_settings.stream_service_type
                elif hasattr(service_settings, "streamServiceType"):
                    service_type = service_settings.streamServiceType
                elif hasattr(service_settings, "datain") and isinstance(
                    service_settings.datain, dict
                ):
                    service_type = service_settings.datain.get("streamServiceType")

                # Broadcast is ready if service is configured and not streaming
                result = service_type is not None and service_type != ""
                return result

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
                    if hasattr(self._client, "start_stream"):
                        self._client.start_stream()
                    else:
                        # Fallback: try direct call
                        self._client.start_stream()
                    # OBS WebSocket v5: StartStream returns None/empty on success
                    # If no exception was raised, the command was successful
                    return True
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
                    if hasattr(self._client, "stop_stream"):
                        response = self._client.stop_stream()
                    else:
                        # Fallback: try direct call
                        response = self._client.stop_stream()
                    return response is not None
                except Exception as e:
                    error_str = str(e).lower()
                    # If stream is not running, that's okay
                    if (
                        "not running" in error_str
                        or "not active" in error_str
                        or "not streaming" in error_str
                    ):
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
            if (
                "not running" in error_str
                or "not active" in error_str
                or "not streaming" in error_str
            ):
                logger.debug("Stream not running")
                return True
            logger.warning(f"Error stopping stream: {e}")
            return False
