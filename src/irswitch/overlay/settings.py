"""Overlay-related INI settings. Nested under AppConfig.overlay."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SamplingSettings:
    """Global sample rate plus optional per-domain overrides."""

    default_hz: float = 5.0
    race_hz: float | None = None
    system_hz: float | None = None
    bio_hz: float | None = None  # None/0 = BLE notifications (push)


@dataclass(frozen=True)
class HuntingSettings:
    enter_gap: float = 3.0
    exit_gap: float = 4.0
    min_closing_rate: float = 0.10
    activation_delay: float = 2.0
    exit_delay: float = 1.5


@dataclass(frozen=True)
class BattleSettings:
    hunting: HuntingSettings = field(default_factory=HuntingSettings)
    hunted: HuntingSettings = field(default_factory=HuntingSettings)
    position_stable_seconds: float = 1.0
    gap_history_seconds: float = 3.0


@dataclass(frozen=True)
class HeartRateSettings:
    enabled: bool = True
    source: str = "bluetooth"
    device: str = "auto"
    reconnect: bool = True
    baseline_window: float = 300.0
    calm_delta: float = 5.0
    focused_delta: float = 15.0
    pushing_delta: float = 25.0


@dataclass(frozen=True)
class SystemInfoSettings:
    enabled: bool = True
    cpu_enabled: bool = True
    gpu_enabled: bool = True
    memory_enabled: bool = True
    lhm_dll_path: str | None = None
    cpu_temp_warn: float = 80.0
    cpu_temp_crit: float = 95.0
    gpu_temp_warn: float = 80.0
    gpu_temp_crit: float = 90.0


@dataclass(frozen=True)
class EventPrioritySettings:
    hunting: int = 20
    hunted: int = 20
    battle_start: int = 30
    lap_complete: int = 40
    personal_best: int = 60
    position_change: int = 70
    overtake: int = 80
    incident: int = 90
    pit: int = 50
    final_lap: int = 95
    finish: int = 100
    bio: int = 35
    system: int = 15


@dataclass(frozen=True)
class EventSettings:
    incident_min_delta: int = 2
    lap_duration: float = 4.0
    lap_cooldown: float = 5.0
    alert_duration: float = 4.0
    session_duration: float = 6.0
    battle_update_hz: float = 8.0
    system_events_on_overlay: bool = False
    priorities: EventPrioritySettings = field(default_factory=EventPrioritySettings)


@dataclass(frozen=True)
class EventEngineFeatureSettings:
    """Event-engine rollout flags. All OFF until the matching track lands."""

    v2_payload: bool = False
    practice: bool = False
    quali_projection: bool = False
    overtake_classifier: bool = False
    pit_story: bool = False
    hr_pressure: bool = False


@dataclass(frozen=True)
class OverlayV4Settings:
    """Overlay V4 rollout flags. All OFF until the matching track lands."""

    assets: bool = False
    renderer: bool = False


@dataclass(frozen=True)
class OverlaySettings:
    """Feature flags and overlay presentation."""

    enabled: bool = True
    theme: str = "cyber_racing"
    debug: bool = False
    language: str = "en"
    v4: OverlayV4Settings = field(default_factory=OverlayV4Settings)
    event_engine: EventEngineFeatureSettings = field(
        default_factory=EventEngineFeatureSettings
    )
    sampling: SamplingSettings = field(default_factory=SamplingSettings)
    battle: BattleSettings = field(default_factory=BattleSettings)
    heart_rate: HeartRateSettings = field(default_factory=HeartRateSettings)
    system_info: SystemInfoSettings = field(default_factory=SystemInfoSettings)
    events: EventSettings = field(default_factory=EventSettings)
