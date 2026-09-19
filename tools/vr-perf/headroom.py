"""Headroom classification for VR perf JSONL samples (stdlib only)."""

from __future__ import annotations

from collections import Counter
from typing import Any


def percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolation percentile for ``p`` in ``[0, 100]``. Empty → None."""
    if not values:
        return None
    if p < 0 or p > 100:
        raise ValueError(f"percentile p must be in [0, 100], got {p}")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    if p <= 0:
        return ordered[0]
    if p >= 100:
        return ordered[-1]
    # Excel-style: index = (n-1) * p/100
    pos = (len(ordered) - 1) * (p / 100.0)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def classify_sample(
    fps: float | None,
    gpu_load: float | None,
    *,
    target_hz: float = 90.0,
) -> str:
    """Return headroom | ok | gpu_bound | fps_low | unknown."""
    if fps is None and gpu_load is None:
        return "unknown"
    # fps_low wins over gpu_bound when under 92% target (see tests)
    if fps is not None and fps < target_hz * 0.92:
        return "fps_low"
    if gpu_load is not None and gpu_load >= 95 and (fps is None or fps < target_hz):
        return "gpu_bound"
    if (
        fps is not None
        and fps >= target_hz * 0.98
        and gpu_load is not None
        and gpu_load < 80
    ):
        return "headroom"
    return "ok"


def _stats(values: list[float], keys: tuple[str, ...]) -> dict[str, float]:
    out: dict[str, float] = {}
    mapping = {
        "p05": 5.0,
        "p50": 50.0,
        "p95": 95.0,
        "min": 0.0,
        "max": 100.0,
    }
    for key in keys:
        val = percentile(values, mapping[key])
        if val is not None:
            out[key] = round(val, 3)
    return out


def _bottleneck_hint(counts: Counter[str]) -> str:
    total = sum(counts.values()) or 1
    gpu = counts.get("gpu_bound", 0)
    low = counts.get("fps_low", 0)
    head = counts.get("headroom", 0)
    if gpu / total >= 0.15:
        return (
            "GPU bound in field spikes — cut shadows/cars/particles before raising MSAA/SS"
        )
    if low / total >= 0.15:
        return (
            "FPS dips without full GPU — check CPU cars/AI, mirrors, or thermal/CPU limit"
        )
    if head / total >= 0.5:
        return "Headroom present — safe to raise SS / quality carefully"
    return "Mostly on target — tune one setting at a time and re-sample field vs solo"


def summarize_samples(
    samples: list[dict[str, Any]],
    *,
    target_hz: float = 90.0,
) -> dict[str, Any]:
    fps_vals: list[float] = []
    ft_vals: list[float] = []
    gpu_vals: list[float] = []
    gpu_temp_vals: list[float] = []
    cpu_vals: list[float] = []
    classes: Counter[str] = Counter()
    low_notes: list[str] = []
    seen_notes: set[str] = set()

    for sample in samples:
        fps = _as_float(sample.get("fps"))
        ft = _as_float(sample.get("frametime_ms"))
        gpu = _as_float(sample.get("gpu_load"))
        gpu_temp = _as_float(sample.get("gpu_temp"))
        cpu = _as_float(sample.get("cpu_load"))
        if fps is not None:
            fps_vals.append(fps)
        if ft is not None:
            ft_vals.append(ft)
        if gpu is not None:
            gpu_vals.append(gpu)
        if gpu_temp is not None:
            gpu_temp_vals.append(gpu_temp)
        if cpu is not None:
            cpu_vals.append(cpu)

        label = classify_sample(fps, gpu, target_hz=target_hz)
        classes[label] += 1
        if label in {"fps_low", "gpu_bound"}:
            note = str(sample.get("note") or "").strip()
            if note and note not in seen_notes and len(low_notes) < 10:
                seen_notes.add(note)
                low_notes.append(note)

    report: dict[str, Any] = {
        "n": len(samples),
        "target_hz": target_hz,
        "class_counts": dict(classes),
        "bottleneck_hint": _bottleneck_hint(classes),
        "low_fps_notes": low_notes,
    }
    if fps_vals:
        report["fps"] = _stats(fps_vals, ("p05", "p50", "p95", "min", "max"))
    if ft_vals:
        report["frametime_ms"] = _stats(ft_vals, ("p50", "p95", "max"))
    if gpu_vals:
        report["gpu_load"] = _stats(gpu_vals, ("p50", "p95", "max"))
    if gpu_temp_vals:
        report["gpu_temp"] = _stats(gpu_temp_vals, ("p50", "max"))
    if cpu_vals:
        report["cpu_load"] = _stats(cpu_vals, ("p50", "p95"))
    return report


def _as_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return value
