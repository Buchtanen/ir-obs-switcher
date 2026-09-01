"""Story context snapshot for RaceObserver (session + bounded stream memory)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
