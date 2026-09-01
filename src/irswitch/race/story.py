"""Story context snapshot for RaceObserver (session + bounded stream memory)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from irswitch.events.envelope import EventEnvelope
from irswitch.iracing.sdk_units import as_completed_lap_time
from irswitch.iracing.weather import WeatherSnapshot
from irswitch.race.opponents import NearFieldCar


@dataclass(frozen=True)
class QualiBag:
    """Hero quali result remembered across the OBS stream (not YAML ResultsPositions)."""

    class_position: int
    best_lap_s: float | None = None


@dataclass(frozen=True)
class HeroSnapshot:
    car_idx: int | None
    class_position: int | None
    overall_position: int | None
    lap: int | None
    display_name: str | None = None
    speakable_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoryBeat:
    """Small factual record of one accepted event; safe to freeze into N12 context."""

    event_id: str
    event_type: str
    phase: str
    mode: str
    correlation_id: str
    monotonic_ms: int
    target_name: str | None = None
    target_car_id: str | None = None
    gap: int | float | str | None = None
    position: int | None = None
    lap: int | None = None
    lap_time: int | float | None = None
    delta: int | float | None = None
    streak: int | None = None
    branch: str | None = None
    front_target_name: str | None = None
    front_gap: int | float | str | None = None
    rear_target_name: str | None = None
    rear_gap: int | float | str | None = None


@dataclass
class StoryHistory:
    """Bounded, session-scoped accepted-beat history owned by RaceObserver."""

    max_beats: int = 24
    _beats: deque[StoryBeat] = field(default_factory=deque, init=False, repr=False)

    def __post_init__(self) -> None:
        self.max_beats = max(1, int(self.max_beats))
        self._beats = deque(maxlen=self.max_beats)

    def note(self, envelope: EventEnvelope) -> None:
        if envelope.phase not in {"ENTER", "RESULT", "EXIT", "UPDATE"}:
            return
        if envelope.event_id and any(beat.event_id == envelope.event_id for beat in self._beats):
            return
        metrics = envelope.metrics if isinstance(envelope.metrics, dict) else {}
        target = envelope.target
        self._beats.append(
            StoryBeat(
                event_id=str(envelope.event_id or ""),
                event_type=str(envelope.event_type or "").upper(),
                phase=str(envelope.phase or "").upper(),
                mode=str(envelope.mode or "").upper(),
                correlation_id=str(envelope.correlation_id or ""),
                monotonic_ms=max(0, int(envelope.monotonic_ms or 0)),
                target_name=(
                    str(target.display_name).strip()
                    if target is not None and target.display_name
                    else _text(_first(metrics, "targetName", "target_name"))
                ),
                target_car_id=(
                    str(target.car_id) if target is not None and target.car_id else None
                ),
                gap=_scalar(_first(metrics, "gap")),
                position=_integer(
                    _first(metrics, "newPosition", "position", "classPosition")
                    or envelope.subject.class_position
                ),
                lap=_integer(_first(metrics, "lap", "current_lap", "currentLap")),
                lap_time=_number(_first(metrics, "lapTime")),
                delta=_number(_first(metrics, "delta", "deltaToBest")),
                streak=_integer(_first(metrics, "streak")),
                branch=_text(_first(metrics, "branch")),
                front_target_name=_text(_first(metrics, "frontTargetName", "front_target_name")),
                front_gap=_scalar(_first(metrics, "frontGap", "front_gap")),
                rear_target_name=_text(_first(metrics, "rearTargetName", "rear_target_name")),
                rear_gap=_scalar(_first(metrics, "rearGap", "rear_gap")),
            )
        )

    def snapshot(self) -> tuple[StoryBeat, ...]:
        return tuple(self._beats)

    def clear(self) -> None:
        self._beats.clear()


@dataclass(frozen=True)
class StoryContext:
    """Read-only race story bag for commentary slots / silence fillers."""

    session_key: str | None
    overlay_mode: str
    hero: HeroSnapshot
    ahead: tuple[NearFieldCar, ...] = ()
    behind: tuple[NearFieldCar, ...] = ()
    leader_name: str | None = None
    leader_class_position: int | None = None
    weather: WeatherSnapshot | None = None
    stream_sessions: tuple[str, ...] = ()
    recent_beats: tuple[StoryBeat, ...] = ()

    def slot_bindings(self) -> dict[str, Any]:
        """Flat metrics useful for FIELD_FACT / WEATHER_CHANGE speech."""
        ahead0 = self.ahead[0] if self.ahead else None
        behind0 = self.behind[0] if self.behind else None
        return {
            "position": self.hero.class_position or self.hero.overall_position,
            "classPosition": self.hero.class_position,
            "overallPosition": self.hero.overall_position,
            "lap": self.hero.lap,
            "leaderName": self.leader_name,
            "target_name": ahead0.display_name if ahead0 else None,
            "gap": ahead0.gap_s if ahead0 else None,
            "behindName": behind0.display_name if behind0 else None,
            "gapBehind": behind0.gap_s if behind0 else None,
            "aheadCount": len(self.ahead),
            "behindCount": len(self.behind),
            "mode": self.overlay_mode,
        }


@dataclass
class StreamMemory:
    """Bounded cross-session memory for one stream run."""

    max_sessions: int = 8
    sessions_seen: list[str] = field(default_factory=list)
    rival_seen: dict[int, str] = field(default_factory=dict)
    quali_class_position: int | None = None
    quali_best_lap_s: float | None = None

    def note_session(self, session_key: str) -> None:
        if not session_key:
            return
        if self.sessions_seen and self.sessions_seen[-1] == session_key:
            return
        self.sessions_seen.append(session_key)
        if len(self.sessions_seen) > self.max_sessions:
            del self.sessions_seen[: len(self.sessions_seen) - self.max_sessions]

    def note_rivals(self, cars: list[NearFieldCar]) -> None:
        for car in cars:
            if car.display_name:
                self.rival_seen[car.car_idx] = car.display_name
        # Bound rival map
        if len(self.rival_seen) > 64:
            keys = list(self.rival_seen.keys())[: len(self.rival_seen) - 64]
            for key in keys:
                self.rival_seen.pop(key, None)

    def note_quali(self, class_position: int | None, best_lap_s: float | None) -> None:
        """Keep last-good quali class position and official best lap (seconds)."""
        if class_position is not None and int(class_position) > 0:
            self.quali_class_position = int(class_position)
        seconds = as_completed_lap_time(best_lap_s)
        if seconds is not None:
            self.quali_best_lap_s = seconds

    def quali_bag(self) -> QualiBag | None:
        """None when this stream never saw a quali class position."""
        if self.quali_class_position is None:
            return None
        return QualiBag(self.quali_class_position, self.quali_best_lap_s)

    def reset_stream(self) -> None:
        self.sessions_seen.clear()
        self.rival_seen.clear()
        self.quali_class_position = None
        self.quali_best_lap_s = None


def _first(metrics: dict[str, Any], *keys: str) -> object | None:
    for key in keys:
        value: object = metrics.get(key)
        if value not in (None, ""):
            return value
    return None


def _text(value: object) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _number(value: object) -> int | float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _integer(value: object) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _scalar(value: object) -> int | float | str | None:
    number = _number(value)
    if number is not None:
        return number
    return _text(value)
