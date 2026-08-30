"""Session-scoped overlay HUD tape (JSONL). Fail-soft; no telemetry ticks.

Clocks (seconds):
- ``t_mono`` — from tape open (replay delay)
- ``t_stream`` — from OBS stream start (VOD sync); null if not streaming
- ``t_session`` — iRacing SessionTime
- ``t_green`` — from first irsdk Racing (SessionState=4) this tape
- ``t`` — best sync clock: stream, else session, else mono
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from irswitch.overlay.models import RaceState
from irswitch.overlay.session import MODE_GENERIC
from irswitch.overlay.settings import OverlaySettings

logger = logging.getLogger(__name__)

ACTIVE_MODES = frozenset({"PRACTICE", "QUALIFYING", "RACE"})
IRSDK_STATE_RACING = 4
TAPE_SCHEMA = "1.0"
_SLUG = re.compile(r"[^A-Za-z0-9._-]+")
CLOCK_KEYS = frozenset({"t", "t_mono", "t_stream", "t_session", "t_green"})


def _strip_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    from irswitch.overlay.bus import strip_secrets

    return strip_secrets(payload)


def safe_tape_dir(raw: str | None) -> str:
    text = (raw or "recordings").strip() or "recordings"
    if ".." in text.replace("\\", "/"):
        return "recordings"
    return text


def playback_offset(row: dict[str, Any]) -> float:
    """Replay sleep clock. Prefer ``t_mono`` so ``t``/``t_stream`` can match VOD."""
    if row.get("t_mono") is not None:
        return float(row["t_mono"])
    return float(row.get("t") or 0.0)


def strip_tape_clocks(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in CLOCK_KEYS}


def _slug(value: str) -> str:
    return _SLUG.sub("-", value).strip("-")[:80] or "session"


def _default_stream_origin() -> float | None:
    try:
        from irswitch.server.metrics import get_metrics

        return get_metrics().stream_started_ts
    except Exception:
        return None


def _default_obs_scene() -> str | None:
    try:
        from irswitch.server.api import get_current_state

        state = get_current_state()
        return state.current_scene if state else None
    except Exception:
        return None


def _default_driving_mode() -> str | None:
    try:
        from irswitch.server.api import get_current_state

        state = get_current_state()
        if state is None or state.mode is None:
            return None
        return getattr(state.mode, "name", None) or str(state.mode)
    except Exception:
        return None


def _default_version() -> str:
    try:
        from irswitch import resolve_version

        return resolve_version()
    except Exception:
        return "unknown"


class OverlaySessionTape:
    """One JSONL file per overlay-active iRacing session."""

    def __init__(
        self,
        *,
        get_stream_origin_mono: Callable[[], float | None] | None = None,
        get_obs_scene: Callable[[], str | None] | None = None,
        get_driving_mode: Callable[[], str | None] | None = None,
        get_version: Callable[[], str] | None = None,
    ) -> None:
        self._get_stream_origin = get_stream_origin_mono or _default_stream_origin
        self._get_obs_scene = get_obs_scene or _default_obs_scene
        self._get_driving_mode = get_driving_mode or _default_driving_mode
        self._get_version = get_version or _default_version
        self._path: Path | None = None
        self._key: str | None = None
        self._origin_mono: float | None = None
        self._stream_origin: float | None = None
        self._green_mono: float | None = None
        self._scene_sig: tuple[str | None, str | None] | None = None
        self._noted_stream = False

    @property
    def path(self) -> Path | None:
        return self._path

    def status_snapshot(self) -> dict[str, Any]:
        """Public read-only status for dashboards. No side effects.

        The tape does not own ``overlay.tape.enabled``; callers combine
        ``pathOpen`` with config to decide ``recording`` vs ``disabled``.
        """
        path = self._path
        return {
            "available": True,
            "pathOpen": path is not None,
            "path": str(path) if path is not None else None,
            "sessionKey": self._key,
        }

    def close(self) -> None:
        self._path = None
        self._key = None
        self._origin_mono = None
        self._stream_origin = None
        self._green_mono = None
        self._scene_sig = None
        self._noted_stream = False

    def observe(self, state: RaceState, now: float, settings: OverlaySettings) -> None:
        tape = settings.tape
        if not tape.enabled:
            self.close()
            return
        active = state.connected and state.overlay_mode in ACTIVE_MODES
        if not active:
            self.close()
            return
        key = f"{state.subsession_id or 'unknown'}:{state.session_num if state.session_num is not None else 0}"
        if self._key != key or self._path is None:
            self.close()
            self._open(state, now, settings, key)
        self._refresh_stream_origin(now, state)
        if state.session_state == IRSDK_STATE_RACING and self._green_mono is None:
            self._green_mono = now
            self._write(now, state, {"type": "green"})
        scene = self._get_obs_scene()
        mode = self._get_driving_mode()
        sig = (scene, mode)
        if sig != self._scene_sig:
            self._scene_sig = sig
            self._write(
                now,
                state,
                {"type": "scene", "obsScene": scene, "drivingMode": mode},
            )

    def record_event(self, envelope: dict[str, Any], now: float, state: RaceState | None) -> None:
        if self._path is None:
            return
        payload = dict(envelope)
        payload.setdefault("type", "event")
        self._write(now, state, payload)

    def record_decision(self, entry: dict[str, Any], now: float, state: RaceState | None) -> None:
        if self._path is None:
            return
        self._write(
            now,
            state,
            {
                "type": "decision",
                "eventType": entry.get("event_type"),
                "action": entry.get("action"),
                "reason": entry.get("reason"),
                "details": entry.get("details") or {},
            },
        )

    def record_stories(
        self, stories: list[dict[str, Any]], now: float, state: RaceState | None
    ) -> None:
        if self._path is None:
            return
        self._write(now, state, {"type": "stories", "activeStories": list(stories)})

    def _open(self, state: RaceState, now: float, settings: OverlaySettings, key: str) -> None:
        directory = Path(safe_tape_dir(settings.tape.directory))
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning("Overlay tape mkdir failed: %s", directory, exc_info=True)
            return
        stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        sub = _slug(str(state.subsession_id or "unknown"))
        num = state.session_num if state.session_num is not None else 0
        path = directory / f"overlay-{stamp}-{sub}-{num}.jsonl"
        self._path = path
        self._key = key
        self._origin_mono = now
        self._stream_origin = self._get_stream_origin()
        self._noted_stream = self._stream_origin is not None
        self._green_mono = now if state.session_state == IRSDK_STATE_RACING else None
        scene = self._get_obs_scene()
        mode = self._get_driving_mode()
        header = {
            "type": "header",
            "schemaVersion": TAPE_SCHEMA,
            "wallClock": datetime.now(tz=UTC).isoformat(),
            "version": self._get_version(),
            "sessionId": key,
            "overlayMode": state.overlay_mode or MODE_GENERIC,
            "theme": settings.theme,
            "v4Renderer": bool(settings.v4.renderer),
            "language": settings.language,
            "obsScene": scene,
            "drivingMode": mode,
            "origins": {
                "mono": now,
                "stream": self._stream_origin,
                "sessionTime": state.session_time,
            },
        }
        self._write(now, state, header)

    def _refresh_stream_origin(self, now: float, state: RaceState) -> None:
        if self._noted_stream:
            return
        origin = self._get_stream_origin()
        if origin is None:
            return
        self._stream_origin = origin
        self._noted_stream = True
        self._write(now, state, {"type": "stream_origin", "streamOriginMono": origin})

    def _clocks(self, now: float, state: RaceState | None) -> dict[str, Any]:
        origin = self._origin_mono if self._origin_mono is not None else now
        t_mono = round(now - origin, 4)
        t_stream = None
        if self._stream_origin is not None:
            t_stream = round(max(0.0, now - self._stream_origin), 4)
        session_time = state.session_time if state is not None else None
        t_session = round(session_time, 4) if session_time is not None else None
        t_green = None
        if self._green_mono is not None:
            t_green = round(now - self._green_mono, 4)
        if t_stream is not None:
            t_best = t_stream
        elif t_session is not None:
            t_best = t_session
        else:
            t_best = t_mono
        return {
            "t": t_best,
            "t_mono": t_mono,
            "t_stream": t_stream,
            "t_session": t_session,
            "t_green": t_green,
        }

    def _write(self, now: float, state: RaceState | None, payload: dict[str, Any]) -> None:
        if self._path is None:
            return
        record = {**self._clocks(now, state), **_strip_secrets(payload)}
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        except OSError:
            logger.warning("Overlay tape write failed: %s", self._path, exc_info=True)
