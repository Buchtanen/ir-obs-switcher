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
    approach_enter_gap: float = 1.5
    approach_exit_gap: float = 1.8
    attack_enter_gap: float = 0.8
    attack_exit_gap: float = 1.0
    side_by_side_enter_gap: float = 0.35
    side_by_side_exit_gap: float = 0.45
    intensity_min_closing_rate: float = 0.15
    # Floor between intensity ladder swaps (exit→enter). Matches presentation minHoldMs.
    min_intensity_hold_s: float = 2.5
    # Throttle UPDATE spam while intensity is unchanged.
    update_min_interval_s: float = 1.0
    update_gap_epsilon_s: float = 0.08


@dataclass(frozen=True)
class OvertakeClassifierSettings:
    max_gap: float = 2.5
    min_closing_rate: float = 0.08


@dataclass(frozen=True)
class BattleSettings:
    hunting: HuntingSettings = field(default_factory=HuntingSettings)
    hunted: HuntingSettings = field(default_factory=HuntingSettings)
    position_stable_seconds: float = 1.0
    gap_history_seconds: float = 3.0
    overtake: OvertakeClassifierSettings = field(default_factory=OvertakeClassifierSettings)


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
    gain_found: int = 45
    time_lost: int = 45
    projected_lap: int = 42
    position_attack: int = 55
    position_change: int = 70
    leader_change: int = 75
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
class OverlayTapeSettings:
    """Session HUD JSONL tape. Default ON; set session_tape=false to disable."""

    enabled: bool = True
    directory: str = "recordings"


@dataclass(frozen=True)
class CommentarySchedulerSettings:
    """Busy-defer / silence / interrupt policy. All safe defaults off."""

    defer_enabled: bool = False
    hard_interrupt: bool = False
    max_deferred: int = 8
    default_ttl_s: float = 12.0
    incident_ttl_s: float = 45.0
    max_silence_s: float = 33.0
    llm_past_framing: bool = True


@dataclass(frozen=True)
class CommentarySettings:
    """Spoken commentary rollout. Default off; no audio until enabled on stream PC."""

    enabled: bool = False
    use_hr_emotion: bool = True
    cooldown_s: float = 4.0
    max_utterance_s: float = 14.0
    tts_backend: str = "auto"
    tts_voice: str = ""
    tts_rate: int = 0
    audio_device: str = ""
    duck_input: str = ""
    duck_ratio: float = 0.25
    duck_fade_ms: int = 750
    decision_log_size: int = 32
    # Sector absolute-time speak path (HUD SECTOR_SPLIT stays independent).
    sector_speak: bool = False
    sector_speak_max_per_lap: int = 1
    # Session intro / SoF / weather commentary sidecars (default off).
    session_briefs: bool = False
    stream_start: bool = False
    # Gap-hunt TTS in practice/qualifying. HUD hunting stays independent.
    gap_hunt_tts_in_practice: bool = False
    gap_hunt_tts_in_qualifying: bool = False
    # Optional remote LLM style polish (Ollama OpenAI-compatible). Default off.
    llm_polish: bool = False
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    llm_timeout_s: float = 12.0
    llm_temperature: float = 0.45
    llm_max_tokens: int = 360
    llm_max_attempts: int = 2
    # Spoken hero identity. Empty = iRacing UserName first/last tokens.
    driver_name: str = ""
    driver_nickname: str = ""
    scheduler: CommentarySchedulerSettings = field(default_factory=CommentarySchedulerSettings)


@dataclass(frozen=True)
class RaceObserverSettings:
    """RaceObserver policy. N3/N5 add keys here — do not invent a second type."""

    leader_pace_cooldown_s: float = 300.0
    # When true, INCIDENT metrics.branch is off_track | unknown. Default off until trusted.
    incident_classify: bool = False
    # Race yellow/green/checkered SESSION_FLAG commentary. Default off.
    flags: bool = False
    # Quali recap + ParadeLaps padding. Default off. Independent of session_briefs.
    grid_story: bool = False


@dataclass(frozen=True)
class OverlaySettings:
    """Feature flags and overlay presentation."""

    enabled: bool = True
    theme: str = "cyber_racing"
    debug: bool = False
    language: str = "en"
    v4: OverlayV4Settings = field(default_factory=OverlayV4Settings)
    tape: OverlayTapeSettings = field(default_factory=OverlayTapeSettings)
    event_engine: EventEngineFeatureSettings = field(default_factory=EventEngineFeatureSettings)
    commentary: CommentarySettings = field(default_factory=CommentarySettings)
    race_observer: RaceObserverSettings = field(default_factory=RaceObserverSettings)
    sampling: SamplingSettings = field(default_factory=SamplingSettings)
    battle: BattleSettings = field(default_factory=BattleSettings)
    heart_rate: HeartRateSettings = field(default_factory=HeartRateSettings)
    system_info: SystemInfoSettings = field(default_factory=SystemInfoSettings)
    events: EventSettings = field(default_factory=EventSettings)
