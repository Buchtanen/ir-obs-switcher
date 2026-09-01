"""Rebuild overlay models from frozen JSON-safe dicts."""

from __future__ import annotations

from dataclasses import fields
from typing import Any, get_origin

from irswitch.overlay.models import (
    BioState,
    CPUState,
    GPUState,
    MemoryState,
    OpponentInfo,
    PerformanceState,
    RaceState,
    SystemHistory,
    SystemState,
)


def _is_tuple_annotation(annotation: object) -> bool:
    if get_origin(annotation) is tuple:
        return True
    return isinstance(annotation, str) and annotation.startswith("tuple")


def race_from_dict(data: dict[str, Any]) -> RaceState:
    ahead = data.get("opponent_ahead")
    behind = data.get("opponent_behind")
    clean = dict(data)
    clean["opponent_ahead"] = OpponentInfo(**ahead) if isinstance(ahead, dict) else ahead
    clean["opponent_behind"] = OpponentInfo(**behind) if isinstance(behind, dict) else behind
    allowed = {item.name: item for item in fields(RaceState)}
    hydrated: dict[str, Any] = {}
    for key, value in clean.items():
        field = allowed.get(key)
        if field is None:
            continue
        if isinstance(value, list) and _is_tuple_annotation(field.type):
            value = tuple(value)
        hydrated[key] = value
    return RaceState(**hydrated)


def bio_from_dict(data: dict[str, Any]) -> BioState:
    allowed = {item.name for item in fields(BioState)}
    if "rr_intervals" in data and isinstance(data["rr_intervals"], list):
        data = {**data, "rr_intervals": tuple(data["rr_intervals"])}
    if "state" not in data and "hr_state" in data:
        data = {**data, "state": data["hr_state"]}
    return BioState(**{key: value for key, value in data.items() if key in allowed})


def system_from_dict(data: dict[str, Any]) -> SystemState:
    def _sub(cls: Any, payload: object) -> Any:
        if not isinstance(payload, dict):
            return cls()
        allowed = {item.name for item in fields(cls)}
        clean = dict(payload)
        if "per_core_load" in clean and isinstance(clean["per_core_load"], list):
            clean["per_core_load"] = tuple(clean["per_core_load"])
        return cls(**{key: value for key, value in clean.items() if key in allowed})

    return SystemState(
        cpu=_sub(CPUState, data.get("cpu")),
        gpu=_sub(GPUState, data.get("gpu")),
        memory=_sub(MemoryState, data.get("memory")),
        performance=_sub(PerformanceState, data.get("performance")),
        history=_sub(SystemHistory, data.get("history")),
    )
