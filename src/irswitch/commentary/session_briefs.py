"""Once-per-session intro / SoF / weather commentary sidecars.

Mirror of ``in_car``: COMMENTARY_ONLY event envelopes, not overlay HUD catalog
entries. Reset on ``(SubSessionID, SessionNum)`` change or disconnect.

Trigger policy (documented product choice for W4/H4):

* **Session intro** — once when ``session_type`` resolves to Practice /
  Qualify / Race (slot-light lines allow missing track / field_size).
* **SoF brief** — once when the race session is active, intro has already
  been acknowledged, and the racing roster is ready (``field_size > 0``).
  Arithmetic-mean interim SoF only (not official iRacing SoF).
* **Weather brief** — once after the intro attempt, preferring a live
  weather snapshot (session fallbacks inside ``extract_weather``).

``tick`` returns the next pending envelope without consuming it. Callers must
``acknowledge(event_type)`` after a terminal director decision (spoken, flag
off, disabled). Do **not** acknowledge on ``busy`` / ``global_cooldown`` so
the brief can retry next frame without starving ``ENTER_CAR`` forever.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.iracing.session_context import SessionContext, SessionContextCache, session_key
from irswitch.iracing.sof import compute_sof_bundle, format_sof_label
from irswitch.iracing.weather import extract_weather, spoken_weather_bindings
from irswitch.overlay.models import RaceState
from irswitch.overlay.session import (
    MODE_PRACTICE,
    MODE_QUALIFYING,
    MODE_RACE,
    overlay_mode_from_session_type,
)

# Envelope priorities align with sequence_graph speak_priority proposals.
_INTRO_PRIORITY = {
    "practice": 36,
    "qualify": 44,
    "race": 64,
}
_SOF_PRIORITY = 46
_WEATHER_PRIORITY = 34

_INTRO_EVENT = {
    "practice": "SESSION_INTRO_PRACTICE",
    "qualify": "SESSION_INTRO_QUALIFY",
    "race": "SESSION_INTRO_RACE",
}
_INTRO_EVENTS = frozenset(_INTRO_EVENT.values())


class SessionBriefsDetector:
    """Emit session intro / SoF / weather envelopes once per session key."""

    def __init__(self) -> None:
        self._key: tuple[int, int] | None = None
        self._intro_done = False
        self._sof_done = False
        self._weather_done = False
        self._sof_skipped = False
        self._cache = SessionContextCache()

    def reset(self) -> None:
        self._key = None
        self._intro_done = False
        self._sof_done = False
        self._weather_done = False
        self._sof_skipped = False
        self._cache.clear()

    def acknowledge(self, event_type: str) -> None:
        """Mark the matching brief as consumed for this session key."""
        if event_type in _INTRO_EVENTS:
            self._intro_done = True
        elif event_type == "SOF_BRIEF":
            self._sof_done = True
        elif event_type == "WEATHER_BRIEF":
            self._weather_done = True

    def tick(
        self,
        state: RaceState,
        data: Mapping[str, object] | None,
        now: float,
        *,
        locale: str = "en",
    ) -> EventEnvelope | None:
        """Return the next pending brief envelope without consuming it."""
        try:
            return self._tick(state, data, now, locale=locale)
        except Exception:
            # Caller logs; never break the race loop.
            return None

    def _tick(
        self,
        state: RaceState,
        data: Mapping[str, object] | None,
        now: float,
        *,
        locale: str,
    ) -> EventEnvelope | None:
        if not state.connected:
            self.reset()
            return None

        key = self._resolve_key(state, data)
        if key != self._key:
            self._key = key
            self._intro_done = False
            self._sof_done = False
            self._weather_done = False
            self._sof_skipped = False
            self._cache.clear()

        kind = _session_kind(state.session_type)
        if kind is None:
            return None

        ctx = self._context(data)
        mode = overlay_mode_from_session_type(state.session_type)

        if not self._intro_done:
            return self._intro_envelope(kind, state, ctx, now, mode=mode)

        if kind == "race" and not self._sof_done and not self._sof_skipped:
            sof_env = self._sof_envelope(state, ctx, now, mode=mode, locale=locale)
            if sof_env is not None:
                return sof_env
            if ctx is not None and len(ctx.roster) == 0:
                self._sof_skipped = True
            elif data is None:
                self._sof_skipped = True
            else:
                # Roster not ready yet — wait without blocking weather forever
                # only when we have no extract; with non-empty pending data keep waiting.
                return None

        if not self._weather_done:
            return self._weather_envelope(state, ctx, data, now, mode=mode, locale=locale)

        return None

    def _resolve_key(
        self,
        state: RaceState,
        data: Mapping[str, object] | None,
    ) -> tuple[int, int] | None:
        if data is not None:
            key = session_key(data)
            if key is not None:
                return key
        try:
            sub = int(state.subsession_id) if state.subsession_id is not None else None
        except (TypeError, ValueError):
            sub = None
        num = state.session_num
        if sub is None or num is None:
            return None
        return (sub, num)

    def _context(self, data: Mapping[str, object] | None) -> SessionContext | None:
        if data is None:
            return None
        return self._cache.get_or_extract(data)

    def _intro_envelope(
        self,
        kind: str,
        state: RaceState,
        ctx: SessionContext | None,
        now: float,
        *,
        mode: str,
    ) -> EventEnvelope:
        event_type = _INTRO_EVENT[kind]
        metrics: dict[str, object] = {"sessionType": state.session_type}
        track = ctx.track if ctx is not None else None
        if track:
            metrics["track"] = track
        field_size = len(ctx.roster) if ctx is not None else 0
        if field_size > 0:
            metrics["field_size"] = field_size
        return make_envelope(
            event_type=event_type,
            phase="RESULT",
            mode=mode,
            priority=_INTRO_PRIORITY[kind],
            monotonic_ms=int(now * 1000),
            dedupe_key=f"{mode}:{event_type}",
            correlation_id=f"session_brief:{event_type}",
            metrics=metrics,
        )

    def _sof_envelope(
        self,
        state: RaceState,
        ctx: SessionContext | None,
        now: float,
        *,
        mode: str,
        locale: str,
    ) -> EventEnvelope | None:
        if ctx is None or len(ctx.roster) == 0:
            return None
        bundle = compute_sof_bundle(ctx.roster, ctx.player_class_id)
        if bundle.field_size <= 0:
            return None
        metrics: dict[str, object] = {
            "sessionType": state.session_type,
            "field_size": bundle.field_size,
            "sofOverallSamples": bundle.overall_samples,
            "sofClassSamples": bundle.class_samples,
            "sofOfficial": False,
        }
        sof = format_sof_label(bundle.overall, locale)
        if sof is not None:
            metrics["sof"] = sof
        sof_class = format_sof_label(bundle.class_sof, locale)
        if sof_class is not None:
            metrics["sof_class"] = sof_class
        return make_envelope(
            event_type="SOF_BRIEF",
            phase="RESULT",
            mode=mode,
            priority=_SOF_PRIORITY,
            monotonic_ms=int(now * 1000),
            dedupe_key=f"{mode}:SOF_BRIEF",
            correlation_id="session_brief:SOF_BRIEF",
            metrics=metrics,
        )

    def _weather_envelope(
        self,
        state: RaceState,
        ctx: SessionContext | None,
        data: Mapping[str, object] | None,
        now: float,
        *,
        mode: str,
        locale: str,
    ) -> EventEnvelope:
        metrics: dict[str, object] = {"sessionType": state.session_type}
        track = ctx.track if ctx is not None else None
        if track:
            metrics["track"] = track
        if data is not None:
            snap = extract_weather(data, prefer="live")
            loc = "cs" if str(locale).lower().startswith("cs") else "en"
            for key, value in spoken_weather_bindings(snap, loc).items():  # type: ignore[arg-type]
                if value:
                    metrics[key] = value
            metrics["weatherSource"] = snap.source
        return make_envelope(
            event_type="WEATHER_BRIEF",
            phase="RESULT",
            mode=mode,
            priority=_WEATHER_PRIORITY,
            monotonic_ms=int(now * 1000),
            dedupe_key=f"{mode}:WEATHER_BRIEF",
            correlation_id="session_brief:WEATHER_BRIEF",
            metrics=metrics,
        )


def _session_kind(session_type: str | None) -> str | None:
    if not session_type:
        return None
    mode = overlay_mode_from_session_type(session_type)
    if mode == MODE_PRACTICE:
        return "practice"
    if mode == MODE_QUALIFYING:
        return "qualify"
    if mode == MODE_RACE:
        return "race"
    return None


def build_session_data_view(
    *,
    weekend_info: object = None,
    driver_info: object = None,
    subsession_id: object = None,
    session_num: object = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    """Test helper: assemble a SessionInfo-like mapping for the detector."""
    data: dict[str, object] = {}
    if weekend_info is not None:
        data["WeekendInfo"] = weekend_info
    if driver_info is not None:
        data["DriverInfo"] = driver_info
    if subsession_id is not None:
        data["SubSessionID"] = subsession_id
    if session_num is not None:
        data["SessionNum"] = session_num
    if extra:
        data.update(dict(extra))
    return data
