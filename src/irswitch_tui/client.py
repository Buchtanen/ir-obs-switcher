"""Client for connecting to the core service."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional

import aiohttp

logger = logging.getLogger(__name__)


class AsyncClient:
    """Async client for communicating with core service API."""

    def __init__(self, base_url: str) -> None:
        """
        Initialize API client.

        Args:
            base_url: Base URL of the core service (e.g., "http://127.0.0.1:17321")
        """
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._status_callback: Optional[Callable[[dict], None]] = None

    async def connect(self) -> None:
        """Connect to the service and start WebSocket listener."""
        self._session = aiohttp.ClientSession()
        await self._connect_websocket()

    async def disconnect(self) -> None:
        """Disconnect from the service."""
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.close()

        if self._session:
            await self._session.close()

    async def _connect_websocket(self) -> None:
        """Connect to WebSocket for real-time updates."""
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"

        try:
            self._ws = await self._session.ws_connect(ws_url)
            self._ws_task = asyncio.create_task(self._ws_listener())
            logger.info("WebSocket connected")
        except Exception as e:
            logger.warning(f"Failed to connect WebSocket: {e}")

    async def _ws_listener(self) -> None:
        """Listen for WebSocket messages."""
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if self._status_callback:
                            self._status_callback(data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from WebSocket: {msg.data}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.warning(f"WebSocket error: {self._ws.exception()}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WebSocket listener error: {e}")

    def set_status_callback(self, callback: Callable[[dict], None]) -> None:
        """Set callback for status updates from WebSocket."""
        self._status_callback = callback

    async def get_status(self) -> dict:
        """Get current status from REST API."""
        if not self._session:
            raise RuntimeError("Client not connected")

        async with self._session.get(f"{self.base_url}/status") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def override_scene(self, scene: str, seconds: int = 120) -> dict:
        """Apply scene override."""
        if not self._session:
            raise RuntimeError("Client not connected")

        async with self._session.post(
            f"{self.base_url}/override", json={"scene": scene, "seconds": seconds}
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def toggle_autoswitch(self) -> dict:
        """Toggle autoswitch on/off."""
        if not self._session:
            raise RuntimeError("Client not connected")

        async with self._session.post(f"{self.base_url}/autoswitch/toggle") as resp:
            resp.raise_for_status()
            return await resp.json()
