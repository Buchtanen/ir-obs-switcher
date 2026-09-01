"""RaceObserver: session/stream story memory + weather/field fillers."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.iracing.drivers import speakable_name_mix_for_car
from irswitch.iracing.weather import WeatherSnapshot, extract_weather, spoken_weather_bindings
from irswitch.overlay.models import RaceState, TelemetrySnapshot
from irswitch.overlay.session import build_session_key, overlay_mode_from_session_type
from irswitch.race.aftermath import IncidentAftermathFsm
from irswitch.race.narrative import StreamNarrativeFsm
from irswitch.race.opponents import (
    NearFieldCar,
    class_position_of,
    is_active_racer,
    relevant_near_field,
    same_class,
)
from irswitch.race.story import HeroSnapshot, StoryContext, StreamMemory

logger = logging.getLogger(__name__)

_AIR_TEMP_DELTA_C = 1.5
_TRACK_TEMP_DELTA_C = 2.0
_WIND_DELTA_MPS = 1.5
_PRECIP_DELTA = 0.08
_FIELD_FACT_PRIORITY = 28
_WEATHER_CHANGE_PRIORITY = 34


@dataclass
class RaceObserver:
    """Deterministic story ledger around the hero (streamer).

    P2: context + commentary-only filler envelopes. No HUD derived emitters yet.
    """

    ahead_n: int = 2
    behind_n: int = 2
    stream: StreamMemory = field(default_factory=StreamMemory)
    aftermath: IncidentAftermathFsm = field(default_factory=IncidentAftermathFsm)
    narrative: StreamNarrativeFsm = field(default_factory=StreamNarrativeFsm)
    _session_key: str | None = None
    _context: StoryContext | None = None
    _last_weather: WeatherSnapshot | None = None
    _pending_weather_change: WeatherSnapshot | None = None
    _last_filler_kind: str | None = None
    _filler_cooldown_until: float = 0.0
    _after_session: bool = False
    _session_checkered: bool = False

    def reset_session(self) -> None:
        self._session_key = None
        self._context = None
        self._last_weather = None
        self._pending_weather_change = None
        self._last_filler_kind = None
        self._filler_cooldown_until = 0.0
        self._after_session = False
        self._session_checkered = False
        self.aftermath.reset()
        self.narrative.reset_session()

    def reset_stream(self) -> None:
        self.reset_session()
        self.stream.reset_stream()
        self.narrative.reset_stream()

    def take_derived_envelopes(self) -> list[EventEnvelope]:
        """Drain derived commentary envelopes (narrative then aftermath)."""
        out = self.narrative.take_pending()
        out.extend(self.aftermath.take_pending())
        return out

    @property
    def context(self) -> StoryContext | None:
        return self._context

    def observe(
        self,
        snap: TelemetrySnapshot,
        state: RaceState,
        *,
        now: float,
        telemetry_data: Mapping[str, Any] | None = None,
    ) -> StoryContext:
        """Update story context from telemetry + race state. Fail-soft."""
        try:
            return self._observe(snap, state, now=now, telemetry_data=telemetry_data)
        except Exception:
            logger.warning("RaceObserver.observe failed", exc_info=True)
            empty = StoryContext(
                session_key=None,
                overlay_mode="GENERIC",
                hero=HeroSnapshot(None, None, None, None),
            )
            self._context = empty
            return empty

    def _observe(
        self,
        snap: TelemetrySnapshot,
        state: RaceState,
        *,
        now: float,
        telemetry_data: Mapping[str, Any] | None,
    ) -> StoryContext:
        key = build_session_key(
            subsession_id=snap.subsession_id,
            session_num=snap.session_num,
            track_id=snap.track_id,
        )
        if key != self._session_key:
            self._session_key = key
            self._last_weather = None
            self._pending_weather_change = None
            self.aftermath.reset()
            if key:
                self.stream.note_session(key)

        ahead: list[NearFieldCar] = []
        behind: list[NearFieldCar] = []
        if snap.connected and snap.player_car_idx is not None:
            ahead, behind = relevant_near_field(snap, ahead_n=self.ahead_n, behind_n=self.behind_n)
            self.stream.note_rivals([*ahead, *behind])

        hero_name = None
        hero_names: tuple[str, ...] = ()
        if snap.player_car_idx is not None:
            names = snap.car_idx_driver_name
            idx = snap.player_car_idx
            if 0 <= idx < len(names) and names[idx]:
                hero_name = names[idx]
            if telemetry_data is not None:
                driver_info = telemetry_data.get("DriverInfo")
                hero_names = speakable_name_mix_for_car(driver_info, idx)
        if not hero_names and hero_name:
            hero_names = (hero_name,)

        leader_name, leader_cp = _find_leader(snap)

        weather = None
        if telemetry_data is not None:
            weather = extract_weather(telemetry_data, prefer="live")
            self._note_weather(weather)

        overlay_mode = state.overlay_mode or overlay_mode_from_session_type(snap.session_type)
        ctx = StoryContext(
            session_key=key,
            overlay_mode=overlay_mode,
            hero=HeroSnapshot(
                car_idx=snap.player_car_idx,
                class_position=state.class_position or snap.class_position,
                overall_position=state.position or snap.position,
                lap=state.lap or snap.lap,
                display_name=hero_name,
                speakable_names=hero_names,
            ),
            ahead=tuple(ahead),
            behind=tuple(behind),
            leader_name=leader_name,
            leader_class_position=leader_cp,
            weather=weather,
            stream_sessions=tuple(self.stream.sessions_seen),
        )
        self._context = ctx
        self._after_session = bool(state.session_finished)
        self._session_checkered = bool(state.session_checkered)
        try:
            self.narrative.tick(state, now, session_key=key)
        except Exception:
            logger.warning("StreamNarrativeFsm.tick failed", exc_info=True)
        try:
            self.aftermath.tick(state, now)
        except Exception:
            logger.warning("IncidentAftermathFsm.tick failed", exc_info=True)
        return ctx

    def next_filler_envelope(self, now: float, *, locale: str = "en") -> EventEnvelope | None:
        """Commentary-only filler for silence watchdog. At most one pending weather."""
        if now < self._filler_cooldown_until:
            return None
        ctx = self._context
        if ctx is None:
            return None
        if self._after_session or self._session_checkered:
            return None

        if self._pending_weather_change is not None:
            snap = self._pending_weather_change
            self._pending_weather_change = None
            bindings = spoken_weather_bindings(snap, "cs" if locale.startswith("cs") else "en")
            metrics = {k: v for k, v in bindings.items() if v}
            metrics["kind"] = "weather_change"
            self._filler_cooldown_until = now + 20.0
            self._last_filler_kind = "weather_change"
            return make_envelope(
                event_type="WEATHER_CHANGE",
                phase="RESULT",
                mode=ctx.overlay_mode,
                priority=_WEATHER_CHANGE_PRIORITY,
                monotonic_ms=int(now * 1000),
                metrics=metrics,
                correlation_id=f"weather:{ctx.session_key or 'na'}",
            )

        # Rotate field facts so silence fill is not identical every time.
        slots = ctx.slot_bindings()
        pos = slots.get("position")
        leader = slots.get("leaderName")
        target = slots.get("target_name")
        gap = slots.get("gap")
        kind_cycle = ("position", "leader", "gap")
        start = 0
        if self._last_filler_kind in kind_cycle:
            start = (kind_cycle.index(self._last_filler_kind) + 1) % len(kind_cycle)
        for offset in range(len(kind_cycle)):
            kind = kind_cycle[(start + offset) % len(kind_cycle)]
            if kind == "position" and pos is not None:
                text_key = "position"
                break
            if kind == "leader" and leader:
                text_key = "leader"
                break
            if kind == "gap" and target and gap is not None:
                text_key = "gap"
                break
        else:
            return None

        metrics = {k: v for k, v in slots.items() if v is not None}
        metrics["kind"] = "field_fact"
        metrics["fact"] = text_key
        self._filler_cooldown_until = now + 15.0
        self._last_filler_kind = text_key
        return make_envelope(
            event_type="FIELD_FACT",
            phase="RESULT",
            mode=ctx.overlay_mode,
            priority=_FIELD_FACT_PRIORITY,
            monotonic_ms=int(now * 1000),
            metrics=metrics,
            correlation_id=f"field:{ctx.session_key or 'na'}:{text_key}",
        )

    def format_filler_text(self, envelope: EventEnvelope, *, locale: str = "en") -> str | None:
        """Template lines when graph has no FIELD_FACT / WEATHER_CHANGE / aftermath node."""
        metrics = envelope.metrics or {}
        kind = str(metrics.get("kind") or "")
        cs = locale.lower().startswith("cs")
        if envelope.event_type == "WEATHER_CHANGE" or kind == "weather_change":
            skies = metrics.get("skies")
            air = metrics.get("air_temp")
            wind = metrics.get("wind_speed")
            parts = [p for p in (skies, air, wind) if p]
            if not parts:
                return None
            if cs:
                return "Počasí se mění: " + ", ".join(str(p) for p in parts) + "."
            return "Weather update: " + ", ".join(str(p) for p in parts) + "."

        if envelope.event_type == "INCIDENT_AFTERMATH":
            if kind == "stalled":
                return (
                    "Stojí. Čeká se, až se znovu rozjede."
                    if cs
                    else "He's stalled. Waiting to get going again."
                )
            return "Incident a pořád v pohybu." if cs else "Incident there, and he's still rolling."

        if envelope.event_type == "BACK_UNDER_WAY" or kind == "back_under_way":
            return "Znovu jede." if cs else "He's back under way."

        if envelope.event_type == "SESSION_WRAP" or kind == "session_wrap":
            label = metrics.get("modeLabelCs" if cs else "modeLabel") or metrics.get("mode")
            pos = metrics.get("position")
            if cs:
                if pos is not None:
                    return f"Konec: {label}, P{int(pos)}."
                return f"Konec session: {label}."
            if pos is not None:
                return f"That's a wrap on {label}, P{int(pos)}."
            return f"That's a wrap on {label}."

        if envelope.event_type == "SESSION_CHECKERED" or kind == "session_checkered":
            label = metrics.get("modeLabelCs" if cs else "modeLabel") or metrics.get("mode")
            if cs:
                return f"Šachovnice. Tohle kolo v {label} ještě platí."
            return f"Checkered. This lap in {label} still counts."

        if envelope.event_type == "SESSION_PREVIEW" or kind == "session_preview":
            label = metrics.get("modeLabelCs" if cs else "modeLabel") or metrics.get("mode")
            if cs:
                return f"Další: {label}."
            return f"Up next: {label}."

        fact = str(metrics.get("fact") or "")
        pos = metrics.get("position")
        leader = metrics.get("leaderName")
        target = metrics.get("target_name")
        gap = metrics.get("gap")
        if fact == "position" and pos is not None:
            return f"Jede na P{int(pos)}." if cs else f"He runs P{int(pos)}."
        if fact == "leader" and leader:
            return f"V čele je {leader}." if cs else f"The leader is {leader}."
        if fact == "gap" and target and gap is not None:
            gap_s = float(gap)
            if cs:
                return f"Na {target} ztrácí {gap_s:.1f} s."
            return f"Gap to {target} is {gap_s:.1f} seconds."
        return None

    def _note_weather(self, weather: WeatherSnapshot) -> None:
        prev = self._last_weather
        self._last_weather = weather
        if prev is None:
            return
        if _weather_changed(prev, weather):
            self._pending_weather_change = weather


def _weather_changed(prev: WeatherSnapshot, cur: WeatherSnapshot) -> bool:
    if prev.skies and cur.skies and prev.skies != cur.skies:
        return True
    if _delta(prev.air_temp_c, cur.air_temp_c, _AIR_TEMP_DELTA_C):
        return True
    if _delta(prev.track_temp_c, cur.track_temp_c, _TRACK_TEMP_DELTA_C):
        return True
    if _delta(prev.wind_speed_mps, cur.wind_speed_mps, _WIND_DELTA_MPS):
        return True
    if _delta(prev.precipitation, cur.precipitation, _PRECIP_DELTA):
        return True
    return False


def _delta(a: float | None, b: float | None, threshold: float) -> bool:
    if a is None or b is None:
        return False
    return abs(float(b) - float(a)) >= threshold


def _find_leader(snap: TelemetrySnapshot) -> tuple[str | None, int | None]:
    player_idx = snap.player_car_idx
    if player_idx is None:
        return None, None
    n = max(len(snap.car_idx_class_position), len(snap.car_idx_driver_name), 0)
    best_idx: int | None = None
    best_cp = 10_000
    for car_idx in range(n):
        if car_idx != player_idx:
            if not is_active_racer(snap, car_idx, player_idx):
                continue
            if not same_class(snap, car_idx, player_idx):
                continue
        cp = class_position_of(snap, car_idx)
        if cp is None or cp <= 0:
            continue
        if cp < best_cp:
            best_cp = cp
            best_idx = car_idx
    if best_idx is None:
        return None, None
    names = snap.car_idx_driver_name
    name = names[best_idx] if 0 <= best_idx < len(names) else None
    return (name if name else None), best_cp
