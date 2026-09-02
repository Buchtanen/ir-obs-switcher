"""In-memory overlay bus: snapshot + coalesced state + immediate events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable
from copy import deepcopy
from typing import Any

from aiohttp.web_ws import WebSocketResponse

from irswitch.overlay.activity import OverlayActivityLog
from irswitch.overlay.models import BioState, RaceState, SystemState
from irswitch.overlay.protocol import snapshot_envelope, state_envelope, state_snapshot_envelope

logger = logging.getLogger(__name__)

# Exact key match only — substring "token" must NOT match headlineToken/statusToken.
_SECRET_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "client_secret",
        "access_token",
        "refresh_token",
        "api_token",
        "auth_token",
        "id_token",
    }
)
_SECRET_SUFFIXES = ("_password", "_secret")


def _is_secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    if lowered in _SECRET_KEYS:
        return True
    return any(lowered.endswith(suffix) for suffix in _SECRET_SUFFIXES)


class OverlayBus:
    """Fan-out to overlay WebSocket clients. Switcher ``/ws`` is independent."""

    def __init__(self) -> None:
        self._clients: set[WebSocketResponse] = set()
        self.race = RaceState()
        self.bio = BioState()
        self.system = SystemState()
        self.active_events: list[dict[str, Any]] = []
        self.active_stories_v4: list[dict[str, Any]] = []
        self.activity_log = OverlayActivityLog()
        self._dirty: set[str] = set()
        self._lock = asyncio.Lock()

    def snapshot(self) -> dict[str, Any]:
        return snapshot_envelope(self.race, self.bio, self.system, self.active_events)

    async def add_client(self, ws: WebSocketResponse, extra: dict[str, Any] | None = None) -> None:
        self._clients.add(ws)
        try:
            payload = self.snapshot()
            if extra:
                payload.update(extra)
            await ws.send_str(json.dumps(payload))
            await ws.send_str(json.dumps(state_snapshot_envelope(self.active_stories_v4)))
        except Exception:
            logger.debug("Overlay WS snapshot send failed", exc_info=True)
            self._clients.discard(ws)

    def discard_client(self, ws: WebSocketResponse) -> None:
        self._clients.discard(ws)

    def set_race(self, state: RaceState) -> None:
        self.race = state
        self._dirty.add("race")

    def set_bio(self, state: BioState) -> None:
        self.bio = state
        self._dirty.add("bio")

    def set_system(self, state: SystemState) -> None:
        self.system = state
        self._dirty.add("system")

    def set_active_events(self, events: list[dict[str, Any]]) -> None:
        self.active_events = list(events)
        self._dirty.add("events")

    def set_active_stories_v4(self, stories: list[dict[str, Any]]) -> None:
        if stories != self.active_stories_v4:
            self.active_stories_v4 = deepcopy(stories)
            self._dirty.add("stories_v4")

    async def publish_event(self, envelope: dict[str, Any]) -> None:
        try:
            self.activity_log.add(envelope)
        except Exception:
            logger.debug("Overlay lifecycle activity append failed", exc_info=True)
        await self._broadcast(envelope)

    async def flush_state(self) -> None:
        """Send dirty domain state envelopes. Events go out immediately elsewhere."""
        dirty = self._dirty.copy()
        self._dirty.clear()
        if not dirty or not self._clients:
            return
        messages: list[dict[str, Any]] = []
        if "race" in dirty:
            messages.append(state_envelope("race", self.race.to_dict()))
        if "bio" in dirty:
            messages.append(state_envelope("bio", self.bio.to_dict()))
        if "system" in dirty:
            messages.append(state_envelope("system", self.system.to_dict()))
        if "events" in dirty:
            messages.append({"type": "activeEvents", "data": self.active_events})
        if "stories_v4" in dirty:
            messages.append(state_snapshot_envelope(self.active_stories_v4))
        for msg in messages:
            await self._broadcast(msg)

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        if not self._clients:
            return
        text = json.dumps(payload)
        stale: list[WebSocketResponse] = []
        for ws in list(self._clients):
            try:
                await ws.send_str(text)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)


def strip_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop secret-looking keys before JSONL recording.

    Uses exact / suffix match so overlay copy fields like ``headlineToken``
    are preserved on session tapes.
    """
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if _is_secret_key(key):
            continue
        if isinstance(value, dict):
            cleaned[key] = strip_secrets(value)
        else:
            cleaned[key] = value
    return cleaned


class OverlayRecorder:
    """Append-only JSONL writer. Never records secrets."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._origin: float | None = None

    def write(self, monotonic_ts: float, envelope: dict[str, Any]) -> None:
        if self._origin is None:
            self._origin = monotonic_ts
        record = {"t": round(monotonic_ts - self._origin, 4), **strip_secrets(envelope)}
        try:
            with open(self._path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        except OSError:
            logger.warning("Overlay recorder failed to write %s", self._path, exc_info=True)


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def iter_replay_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(rows)
