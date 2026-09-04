"""Normalized overlay state models. JSON-serializable, nullable fields."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _asdict(obj: Any) -> dict[str, Any]:
    return asdict(obj)


@dataclass(frozen=True)
class OpponentInfo:
    car_idx: int
    position: int | None = None
    class_position: int | None = None
    gap: float | None = None
    closing_rate: float | None = None
    display_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class TelemetrySnapshot:
    """Raw iRSDK extraction. No race interpretation."""

    connected: bool = False
    timestamp: float = 0.0
    player_car_idx: int | None = None
    position: int | None = None
    class_position: int | None = None
    lap: int | None = None
    lap_completed: int | None = None
    current_lap_time: float | None = None
    last_lap_time: float | None = None
    best_lap_time: float | None = None
    incidents: int | None = None
    on_pit_road: bool | None = None
    session_laps_remain: float | None = None
    session_state: int | None = None
    fps: float | None = None
    frametime_ms: float | None = None
    car_dist_ahead: float | None = None
    car_dist_behind: float | None = None
    player_car_class: int | None = None
    car_idx_lap_dist_pct: tuple[float | None, ...] = ()
    car_idx_lap_completed: tuple[int | None, ...] = ()
    car_idx_class: tuple[int | None, ...] = ()
    car_idx_class_position: tuple[int | None, ...] = ()
    car_idx_position: tuple[int | None, ...] = ()
    car_idx_on_pit_road: tuple[bool | None, ...] = ()
    car_idx_est_time: tuple[float | None, ...] = ()
    car_idx_best_lap_time: tuple[float | None, ...] = ()
    car_idx_last_lap_time: tuple[float | None, ...] = ()
    car_idx_track_surface: tuple[int | None, ...] = ()
    car_idx_driver_name: tuple[str | None, ...] = ()
    speed_mps: float | None = None
    # Session / quality (Event Engine normalized input — optional until adapter fills them)
    session_num: int | None = None
    subsession_id: str | None = None
    session_type: str | None = None  # Practice/Qualify/Race/...
    track_id: str | None = None
    session_time: float | None = None
    session_flags: int | None = None
    player_lap_dist_pct: float | None = None
    stale_for_ms: float | None = None
    data_quality: str = "ok"  # ok/degraded/stale
    player_track_surface: int | None = None
    player_tow_time: float | None = None
    sector_start_pcts: tuple[float, ...] = ()

    @classmethod
    def disconnected(cls, timestamp: float = 0.0) -> TelemetrySnapshot:
        return cls(connected=False, timestamp=timestamp, data_quality="stale")

    def to_dict(self) -> dict[str, Any]:
        data = _asdict(self)
        # Tuples become lists for JSON.
        for key, value in list(data.items()):
            if isinstance(value, tuple):
                data[key] = list(value)
        return data


@dataclass(frozen=True)
class RaceState:
    """Interpreted overlay state for **every** session row (Practice/Qualify/Race).

    Historical name — not Race-session-only. ``overlay_mode`` is the HUD mode
    (PRACTICE/QUALIFYING/RACE/GENERIC), not ``DrivingMode`` and not CLI input.
    """

    connected: bool = False
    player_car_idx: int | None = None
    position: int | None = None
    class_position: int | None = None
    class_field_size: int | None = None
    player_car_class: int | None = None
    leader_car_idx: int | None = None
    leader_name: str | None = None
    p1_name: str | None = None
    p2_name: str | None = None
    p3_name: str | None = None
    lap: int | None = None
    lap_completed: int | None = None
    current_lap_time: float | None = None
    last_lap_time: float | None = None
    best_lap_time: float | None = None
    incidents: int | None = None
    on_pit_road: bool = False
    is_final_lap: bool = False
    session_finished: bool = False
    session_checkered: bool = False
    player_finished: bool = False
    mute_field: bool = False
    opponent_ahead: OpponentInfo | None = None
    opponent_behind: OpponentInfo | None = None
    gap_ahead: float | None = None
    gap_behind: float | None = None
    closing_rate_ahead: float | None = None
    closing_rate_behind: float | None = None
    car_idx_on_pit_road: tuple[bool | None, ...] = ()
    fps: float | None = None
    frametime_ms: float | None = None
    session_num: int | None = None
    subsession_id: str | None = None
    session_type: str | None = None
    track_id: str | None = None
    session_time: float | None = None
    session_state: int | None = None
    overlay_mode: str = "GENERIC"  # PRACTICE/QUALIFYING/RACE/GENERIC
    player_lap_dist_pct: float | None = None
    stale_for_ms: float | None = None
    data_quality: str = "ok"
    player_track_surface: int | None = None
    player_tow_time: float | None = None
    speed_mps: float | None = None
    session_flags: int | None = None
    session_flag_names: tuple[str, ...] = ()
    flag_checkered: bool = False
    flag_yellow: bool = False
    flag_green: bool = False
    car_idx_best_lap_time: tuple[float | None, ...] = ()
    car_idx_last_lap_time: tuple[float | None, ...] = ()

    run_epoch: int = 0
    green_session_time: float | None = None
    green_lap_completed: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = _asdict(self)
        if self.opponent_ahead is not None:
            data["opponent_ahead"] = self.opponent_ahead.to_dict()
        if self.opponent_behind is not None:
            data["opponent_behind"] = self.opponent_behind.to_dict()
        return data


@dataclass(frozen=True)
class BioState:
    connected: bool = False
    status: str = "disconnected"  # connected/connecting/disconnected/reconnecting
    device_name: str | None = None
    bpm: int | None = None
    baseline_bpm: float | None = None
    delta_bpm: float | None = None
    state: str = "unknown"  # calm/focused/pushing/high
    rr_intervals: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = _asdict(self)
        data["rr_intervals"] = list(self.rr_intervals)
        return data


@dataclass(frozen=True)
class CPUState:
    load: float | None = None
    temperature: float | None = None
    power: float | None = None
    frequency: float | None = None
    per_core_load: tuple[float, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = _asdict(self)
        data["per_core_load"] = list(self.per_core_load)
        return data


@dataclass(frozen=True)
class GPUState:
    load: float | None = None
    temperature: float | None = None
    power: float | None = None
    power_limit: float | None = None
    clock: float | None = None
    memory_clock: float | None = None
    vram_used: float | None = None
    vram_total: float | None = None
    throttle_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class MemoryState:
    used: float | None = None
    total: float | None = None
    percent: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class PerformanceState:
    fps: float | None = None
    frametime: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class SystemHistory:
    gpu_load_avg_10s: float | None = None
    gpu_temp_max_60s: float | None = None
    cpu_load_avg_10s: float | None = None
    cpu_temp_max_60s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class SystemState:
    cpu: CPUState = field(default_factory=CPUState)
    gpu: GPUState = field(default_factory=GPUState)
    memory: MemoryState = field(default_factory=MemoryState)
    performance: PerformanceState = field(default_factory=PerformanceState)
    history: SystemHistory = field(default_factory=SystemHistory)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu": self.cpu.to_dict(),
            "gpu": self.gpu.to_dict(),
            "memory": self.memory.to_dict(),
            "performance": self.performance.to_dict(),
            "history": self.history.to_dict(),
        }
