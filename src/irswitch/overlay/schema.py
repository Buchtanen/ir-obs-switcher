"""Schema-driven overlay/config field descriptors for the config page and PUT API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from irswitch.overlay.settings import OverlaySettings

FieldType = Literal["float", "int", "bool", "str"]


@dataclass(frozen=True)
class FieldSpec:
    key: str
    field_type: FieldType
    default: Any
    live: bool
    section: str
    help: str
    minimum: float | None = None
    maximum: float | None = None
    optional: bool = False
    choices: tuple[str, ...] | None = None
    secret: bool = False


OVERLAY_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "overlay.enabled",
        "bool",
        True,
        True,
        "overlay",
        "Enable race overlay pipeline.",
    ),
    FieldSpec(
        "overlay.theme",
        "str",
        "cyber_racing",
        True,
        "overlay",
        "Theme id (same widget geometry, different tokens).",
        choices=("cyber_racing", "stealth_graphite", "night_attack"),
    ),
    FieldSpec("overlay.debug", "bool", False, True, "overlay", "Verbose overlay debug logging."),
    FieldSpec(
        "sampling.default_hz",
        "float",
        5.0,
        True,
        "sampling",
        "Global sample rate. Components may override.",
        0.2,
        30.0,
    ),
    FieldSpec(
        "sampling.race.hz",
        "float",
        None,
        True,
        "sampling.race",
        "Race telemetry Hz. Empty = global default.",
        0.2,
        30.0,
        optional=True,
    ),
    FieldSpec(
        "sampling.system.hz",
        "float",
        None,
        True,
        "sampling.system",
        "System info Hz. Empty = global default.",
        0.2,
        30.0,
        optional=True,
    ),
    FieldSpec(
        "sampling.bio.hz",
        "float",
        None,
        True,
        "sampling.bio",
        "Heart-rate poll Hz. Empty or 0 = BLE notifications (push).",
        0.0,
        30.0,
        optional=True,
    ),
    FieldSpec("battle.hunting.enter_gap", "float", 3.0, True, "battle.hunting", "Enter hunting when gap < this (s).", 0.1, 20.0),
    FieldSpec("battle.hunting.exit_gap", "float", 4.0, True, "battle.hunting", "Exit hunting when gap > this (s).", 0.1, 30.0),
    FieldSpec(
        "battle.hunting.min_closing_rate",
        "float",
        0.10,
        True,
        "battle.hunting",
        "Minimum closing rate (s/s).",
        0.0,
        5.0,
    ),
    FieldSpec(
        "battle.hunting.activation_delay",
        "float",
        2.0,
        True,
        "battle.hunting",
        "Seconds conditions must hold before ENTER.",
        0.0,
        15.0,
    ),
    FieldSpec(
        "battle.hunting.exit_delay",
        "float",
        1.5,
        True,
        "battle.hunting",
        "Seconds conditions must fail before EXIT.",
        0.0,
        15.0,
    ),
    FieldSpec("battle.hunted.enter_gap", "float", 3.0, True, "battle.hunted", "Enter hunted when gap < this (s).", 0.1, 20.0),
    FieldSpec("battle.hunted.exit_gap", "float", 4.0, True, "battle.hunted", "Exit hunted when gap > this (s).", 0.1, 30.0),
    FieldSpec(
        "battle.hunted.min_closing_rate",
        "float",
        0.10,
        True,
        "battle.hunted",
        "Minimum closing rate (s/s).",
        0.0,
        5.0,
    ),
    FieldSpec(
        "battle.hunted.activation_delay",
        "float",
        2.0,
        True,
        "battle.hunted",
        "Seconds conditions must hold before ENTER.",
        0.0,
        15.0,
    ),
    FieldSpec(
        "battle.hunted.exit_delay",
        "float",
        1.5,
        True,
        "battle.hunted",
        "Seconds conditions must fail before EXIT.",
        0.0,
        15.0,
    ),
    FieldSpec(
        "battle.position_stable_seconds",
        "float",
        1.0,
        True,
        "battle",
        "Position must be stable this long before emit.",
        0.3,
        5.0,
    ),
    FieldSpec(
        "battle.gap_history_seconds",
        "float",
        3.0,
        True,
        "battle",
        "Rolling window for closing-rate regression.",
        1.0,
        8.0,
    ),
    FieldSpec("heart_rate.enabled", "bool", True, True, "heart_rate", "Enable BLE heart-rate provider."),
    FieldSpec("heart_rate.source", "str", "bluetooth", True, "heart_rate", "HR source (bluetooth)."),
    FieldSpec("heart_rate.bluetooth.device", "str", "auto", True, "heart_rate.bluetooth", "Device name/address or auto."),
    FieldSpec("heart_rate.bluetooth.reconnect", "bool", True, True, "heart_rate.bluetooth", "Auto-reconnect on disconnect."),
    FieldSpec(
        "heart_rate.baseline_window",
        "float",
        300.0,
        True,
        "heart_rate",
        "Rolling baseline window in seconds.",
        30.0,
        1800.0,
    ),
    FieldSpec("heart_rate.calm_delta", "float", 5.0, True, "heart_rate", "Delta BPM below this is CALM.", 0.0, 50.0),
    FieldSpec("heart_rate.focused_delta", "float", 15.0, True, "heart_rate", "Delta BPM below this is FOCUSED.", 0.0, 80.0),
    FieldSpec("heart_rate.pushing_delta", "float", 25.0, True, "heart_rate", "Delta BPM below this is PUSHING; above is HIGH.", 0.0, 100.0),
    FieldSpec("system_info.enabled", "bool", True, True, "system_info", "Enable system info provider."),
    FieldSpec("system_info.cpu.enabled", "bool", True, True, "system_info.cpu", "Read CPU sensors."),
    FieldSpec("system_info.gpu.enabled", "bool", True, True, "system_info.gpu", "Read NVIDIA GPU via NVML."),
    FieldSpec("system_info.memory.enabled", "bool", True, True, "system_info.memory", "Read RAM via psutil."),
    FieldSpec(
        "system_info.lhm_dll_path",
        "str",
        None,
        False,
        "system_info",
        "Optional LibreHardwareMonitorLib.dll path. Empty = disabled.",
        optional=True,
    ),
    FieldSpec("system_info.cpu_temp_warn", "float", 80.0, True, "system_info", "CPU warning temperature °C.", 40.0, 120.0),
    FieldSpec("system_info.cpu_temp_crit", "float", 95.0, True, "system_info", "CPU critical temperature °C.", 50.0, 130.0),
    FieldSpec("system_info.gpu_temp_warn", "float", 80.0, True, "system_info", "GPU warning temperature °C.", 40.0, 120.0),
    FieldSpec("system_info.gpu_temp_crit", "float", 90.0, True, "system_info", "GPU critical temperature °C.", 50.0, 130.0),
    FieldSpec(
        "events.system_events_on_overlay",
        "bool",
        False,
        True,
        "events",
        "Show CPU/GPU alerts on the stream overlay (default: debug only).",
    ),
    FieldSpec("events.incident_min_delta", "int", 2, True, "events", "Minimum incident delta to show.", 1, 16),
    FieldSpec("events.lap_duration", "float", 4.0, True, "events", "Lap widget display seconds.", 1.0, 15.0),
    FieldSpec("events.lap_cooldown", "float", 5.0, True, "events", "Lap event cooldown seconds.", 0.0, 30.0),
    FieldSpec("events.priorities.hunting", "int", 20, True, "events.priorities", "Hunting priority.", 1, 100),
    FieldSpec("events.priorities.hunted", "int", 20, True, "events.priorities", "Hunted priority.", 1, 100),
    FieldSpec("events.priorities.lap_complete", "int", 40, True, "events.priorities", "Lap complete priority.", 1, 100),
    FieldSpec("events.priorities.personal_best", "int", 60, True, "events.priorities", "Personal best priority.", 1, 100),
    FieldSpec("events.priorities.position_change", "int", 70, True, "events.priorities", "Position change priority.", 1, 100),
    FieldSpec("events.priorities.incident", "int", 90, True, "events.priorities", "Incident priority.", 1, 100),
    FieldSpec("events.priorities.final_lap", "int", 95, True, "events.priorities", "Final lap priority.", 1, 100),
    FieldSpec("events.priorities.finish", "int", 100, True, "events.priorities", "Finish priority.", 1, 100),
)

_FIELD_BY_KEY = {spec.key: spec for spec in OVERLAY_FIELDS}


def field_by_key(key: str) -> FieldSpec | None:
    return _FIELD_BY_KEY.get(key)


def schema_as_dicts() -> list[dict[str, Any]]:
    rows = []
    for spec in OVERLAY_FIELDS:
        rows.append(
            {
                "key": spec.key,
                "type": spec.field_type,
                "default": spec.default,
                "live": spec.live,
                "section": spec.section,
                "help": spec.help,
                "min": spec.minimum,
                "max": spec.maximum,
                "optional": spec.optional,
                "choices": list(spec.choices) if spec.choices else None,
                "secret": spec.secret,
            }
        )
    return rows


def overlay_values(settings: OverlaySettings) -> dict[str, Any]:
    """Flatten OverlaySettings to dotted keys used by the config UI."""
    s = settings
    return {
        "overlay.enabled": s.enabled,
        "overlay.theme": s.theme,
        "overlay.debug": s.debug,
        "sampling.default_hz": s.sampling.default_hz,
        "sampling.race.hz": s.sampling.race_hz,
        "sampling.system.hz": s.sampling.system_hz,
        "sampling.bio.hz": s.sampling.bio_hz,
        "battle.hunting.enter_gap": s.battle.hunting.enter_gap,
        "battle.hunting.exit_gap": s.battle.hunting.exit_gap,
        "battle.hunting.min_closing_rate": s.battle.hunting.min_closing_rate,
        "battle.hunting.activation_delay": s.battle.hunting.activation_delay,
        "battle.hunting.exit_delay": s.battle.hunting.exit_delay,
        "battle.hunted.enter_gap": s.battle.hunted.enter_gap,
        "battle.hunted.exit_gap": s.battle.hunted.exit_gap,
        "battle.hunted.min_closing_rate": s.battle.hunted.min_closing_rate,
        "battle.hunted.activation_delay": s.battle.hunted.activation_delay,
        "battle.hunted.exit_delay": s.battle.hunted.exit_delay,
        "battle.position_stable_seconds": s.battle.position_stable_seconds,
        "battle.gap_history_seconds": s.battle.gap_history_seconds,
        "heart_rate.enabled": s.heart_rate.enabled,
        "heart_rate.source": s.heart_rate.source,
        "heart_rate.bluetooth.device": s.heart_rate.device,
        "heart_rate.bluetooth.reconnect": s.heart_rate.reconnect,
        "heart_rate.baseline_window": s.heart_rate.baseline_window,
        "heart_rate.calm_delta": s.heart_rate.calm_delta,
        "heart_rate.focused_delta": s.heart_rate.focused_delta,
        "heart_rate.pushing_delta": s.heart_rate.pushing_delta,
        "system_info.enabled": s.system_info.enabled,
        "system_info.cpu.enabled": s.system_info.cpu_enabled,
        "system_info.gpu.enabled": s.system_info.gpu_enabled,
        "system_info.memory.enabled": s.system_info.memory_enabled,
        "system_info.lhm_dll_path": s.system_info.lhm_dll_path,
        "system_info.cpu_temp_warn": s.system_info.cpu_temp_warn,
        "system_info.cpu_temp_crit": s.system_info.cpu_temp_crit,
        "system_info.gpu_temp_warn": s.system_info.gpu_temp_warn,
        "system_info.gpu_temp_crit": s.system_info.gpu_temp_crit,
        "events.system_events_on_overlay": s.events.system_events_on_overlay,
        "events.incident_min_delta": s.events.incident_min_delta,
        "events.lap_duration": s.events.lap_duration,
        "events.lap_cooldown": s.events.lap_cooldown,
        "events.priorities.hunting": s.events.priorities.hunting,
        "events.priorities.hunted": s.events.priorities.hunted,
        "events.priorities.lap_complete": s.events.priorities.lap_complete,
        "events.priorities.personal_best": s.events.priorities.personal_best,
        "events.priorities.position_change": s.events.priorities.position_change,
        "events.priorities.incident": s.events.priorities.incident,
        "events.priorities.final_lap": s.events.priorities.final_lap,
        "events.priorities.finish": s.events.priorities.finish,
    }


def coerce_value(spec: FieldSpec, raw: Any) -> Any:
    if raw is None or raw == "":
        if spec.optional:
            return None
        return spec.default
    if spec.field_type == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    if spec.field_type == "int":
        value = int(raw)
        if spec.minimum is not None and value < spec.minimum:
            raise ValueError(f"{spec.key} must be >= {spec.minimum}")
        if spec.maximum is not None and value > spec.maximum:
            raise ValueError(f"{spec.key} must be <= {spec.maximum}")
        return value
    if spec.field_type == "float":
        value = float(raw)
        if spec.minimum is not None and value < spec.minimum:
            raise ValueError(f"{spec.key} must be >= {spec.minimum}")
        if spec.maximum is not None and value > spec.maximum:
            raise ValueError(f"{spec.key} must be <= {spec.maximum}")
        return value
    text = str(raw).strip()
    if spec.choices and text not in spec.choices:
        raise ValueError(f"{spec.key} must be one of {spec.choices}")
    if spec.key.endswith("lhm_dll_path") or spec.key.endswith("theme"):
        if ".." in text.replace("\\", "/").split("/"):
            raise ValueError(f"{spec.key} must not contain path traversal")
    return text
