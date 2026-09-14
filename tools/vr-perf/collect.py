#!/usr/bin/env python3
"""Standalone VR/iRacing performance sampler (Windows). Not part of irswitch."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from headroom import summarize_samples

_DEFAULT_LHM = "http://127.0.0.1:8085/data.json"
_UA = {"User-Agent": "vr-perf-collect/1.0", "Accept": "application/json"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sample LHM (+ optional NVML/iRacing) to JSONL for VR tuning"
    )
    sub = parser.add_subparsers(dest="cmd")

    collect_p = sub.add_parser("collect", help="Record samples (default if omitted)")
    _add_collect_args(collect_p)

    sum_p = sub.add_parser("summarize", help="Summarize a JSONL recording")
    sum_p.add_argument("path", type=Path)
    sum_p.add_argument("--hz", type=float, default=90.0)

    # Allow `python collect.py --out ...` without subcommand
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] not in {"collect", "summarize", "-h", "--help"}:
        argv = ["collect", *argv]

    args = parser.parse_args(argv)
    if args.cmd == "summarize":
        return cmd_summarize(args)
    if args.cmd == "collect":
        return cmd_collect(args)
    parser.print_help()
    return 2


def _add_collect_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", type=Path, required=True, help="JSONL output path")
    p.add_argument("--hz", type=float, default=90.0, help="Target headset Hz")
    p.add_argument("--interval", type=float, default=0.5, help="Sample period seconds")
    p.add_argument("--lhm-url", default=_DEFAULT_LHM, help="LibreHardwareMonitor data.json")
    p.add_argument("--note", default="", help="Sticky segment label (solo/field/...)")
    p.add_argument(
        "--note-file",
        type=Path,
        default=None,
        help="Optional text file polled for live note changes",
    )
    p.add_argument(
        "--renderer-ini",
        type=Path,
        default=None,
        help="Optional iRacing renderer.ini to snapshot once at start",
    )
    p.add_argument("--duration", type=float, default=0.0, help="Stop after N seconds (0=forever)")


def cmd_summarize(args: argparse.Namespace) -> int:
    samples = list(_iter_jsonl(args.path))
    report = summarize_samples(samples, target_hz=args.hz)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print()
    print(report.get("bottleneck_hint", ""))
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    args.out.parent.mkdir(parents=True, exist_ok=True)
    note = str(args.note or "").strip()
    meta = {
        "type": "meta",
        "ts": time.time(),
        "target_hz": args.hz,
        "lhm_url": args.lhm_url,
        "interval": args.interval,
        "renderer_ini": _snapshot_ini(args.renderer_ini) if args.renderer_ini else None,
        "sources": _probe_sources(args.lhm_url),
    }
    with args.out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
        fh.flush()
        print(f"recording → {args.out}", flush=True)
        print(f"sources: {meta['sources']}", flush=True)
        print("Ctrl+C to stop. Change --note-file to tag solo/field.", flush=True)

        started = time.monotonic()
        n = 0
        try:
            while True:
                if args.note_file and args.note_file.exists():
                    text = args.note_file.read_text(encoding="utf-8", errors="replace")
                    line = text.strip().splitlines()
                    if line:
                        note = line[0].strip()
                sample = take_sample(args.lhm_url, note=note, target_hz=args.hz)
                fh.write(json.dumps(sample, ensure_ascii=False) + "\n")
                fh.flush()
                n += 1
                if n % 10 == 0:
                    fps = sample.get("fps")
                    gpu = sample.get("gpu_load")
                    print(
                        f"n={n} note={note!r} fps={fps} gpu={gpu} class={sample.get('class')}",
                        flush=True,
                    )
                if args.duration > 0 and (time.monotonic() - started) >= args.duration:
                    break
                time.sleep(max(0.05, float(args.interval)))
        except KeyboardInterrupt:
            print(f"\nstopped after {n} samples", flush=True)
    return 0


def take_sample(lhm_url: str, *, note: str, target_hz: float) -> dict[str, Any]:
    from headroom import classify_sample

    lhm = read_lhm(lhm_url)
    nvml = read_nvml()
    ir = read_iracing()

    gpu_load = _first(lhm.get("gpu_load"), nvml.get("gpu_load"))
    gpu_temp = _first(lhm.get("gpu_temp"), nvml.get("gpu_temp"))
    gpu_power = _first(lhm.get("gpu_power"), nvml.get("gpu_power"))
    gpu_clock = _first(lhm.get("gpu_clock"), nvml.get("gpu_clock"))
    vram_used = _first(lhm.get("vram_used_gb"), nvml.get("vram_used_gb"))
    vram_total = _first(lhm.get("vram_total_gb"), nvml.get("vram_total_gb"))

    fps = ir.get("fps")
    frametime_ms = ir.get("frametime_ms")
    if frametime_ms is None and fps and fps > 0:
        frametime_ms = 1000.0 / fps

    sample = {
        "type": "sample",
        "ts": time.time(),
        "note": note,
        "fps": fps,
        "frametime_ms": frametime_ms,
        "cars_active": ir.get("cars_active"),
        "gpu_load": gpu_load,
        "gpu_temp": gpu_temp,
        "gpu_power": gpu_power,
        "gpu_clock": gpu_clock,
        "vram_used_gb": vram_used,
        "vram_total_gb": vram_total,
        "cpu_load": lhm.get("cpu_load"),
        "cpu_temp": lhm.get("cpu_temp"),
        "cpu_power": lhm.get("cpu_power"),
        "lhm_ok": lhm.get("ok", False),
        "nvml_ok": nvml.get("ok", False),
        "iracing_ok": ir.get("ok", False),
    }
    sample["class"] = classify_sample(fps, gpu_load, target_hz=target_hz)
    return sample


def read_lhm(url: str) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False}
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=2.5) as resp:  # noqa: S310 — local LHM only
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        out["error"] = str(exc)
        return out

    rows = _flatten_lhm(payload)
    out["ok"] = True
    out["gpu_load"] = _pick(rows, want_gpu=True, types=("Load",), names=("GPU Core", "D3D", "Core"))
    out["gpu_temp"] = _pick(rows, want_gpu=True, types=("Temperature",), names=("GPU Core", "Core"))
    out["gpu_power"] = _pick(rows, want_gpu=True, types=("Power",), names=("GPU Package", "Package", "Power"))
    out["gpu_clock"] = _pick(rows, want_gpu=True, types=("Clock",), names=("GPU Core", "Clock"))
    out["vram_used_gb"] = _pick_vram_used(rows)
    out["vram_total_gb"] = _pick_vram_total(rows)
    out["cpu_load"] = _pick(rows, want_gpu=False, types=("Load",), names=("CPU Total", "Total"))
    out["cpu_temp"] = _pick(
        rows, want_gpu=False, types=("Temperature",), names=("CPU Package", "Package", "Tctl")
    )
    out["cpu_power"] = _pick(
        rows, want_gpu=False, types=("Power",), names=("CPU Package", "Package")
    )
    return out


def read_nvml() -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False}
    try:
        import pynvml  # type: ignore
    except ImportError:
        return out
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        out["gpu_load"] = float(util.gpu)
        out["gpu_temp"] = float(temp)
        try:
            out["gpu_power"] = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
        except Exception:
            pass
        try:
            out["gpu_clock"] = float(
                pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)
            )
        except Exception:
            pass
        try:
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            out["vram_used_gb"] = float(mem.used) / (1024**3)
            out["vram_total_gb"] = float(mem.total) / (1024**3)
        except Exception:
            pass
        out["ok"] = True
    except Exception as exc:
        out["error"] = str(exc)
    return out


def read_iracing() -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False}
    # Prefer irsdk (community) then pyirsdk naming
    sdk = None
    for mod_name in ("irsdk", "pyirsdk"):
        try:
            sdk = __import__(mod_name)
            break
        except ImportError:
            continue
    if sdk is None:
        return out
    try:
        ir = sdk.IRSDK()
        if not ir.startup():
            return out
        if not ir.is_initialized or not ir.is_connected:
            return out
        fps = ir["FrameRate"]
        if fps is not None:
            out["fps"] = float(fps)
            if float(fps) > 0:
                out["frametime_ms"] = 1000.0 / float(fps)
        # Rough active car count from lap dist pct
        dists = ir["CarIdxLapDistPct"]
        if dists is not None:
            active = 0
            for val in list(dists):
                try:
                    f = float(val)
                except (TypeError, ValueError):
                    continue
                if f >= 0.0:
                    active += 1
            out["cars_active"] = active
        out["ok"] = True
    except Exception as exc:
        out["error"] = str(exc)
    return out


def _flatten_lhm(node: Any, parent: str = "", hardware: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(node, dict):
        return rows
    text = str(node.get("Text") or "")
    hardware_id = str(node.get("HardwareId") or "")
    sensor_id = str(node.get("SensorId") or "")
    typ = str(node.get("Type") or "")
    raw = node.get("Value")
    value = _parse_number(raw)
    next_hardware = hardware
    if hardware_id:
        next_hardware = f"{hardware_id} {text}".strip()
    elif not typ and text and node.get("Children"):
        next_hardware = f"{hardware} {text}".strip()
    next_parent = hardware_id or parent or next_hardware
    if typ and value is not None:
        rows.append(
            {
                "name": text,
                "sensor_type": typ,
                "value": value,
                "identifier": sensor_id or hardware_id,
                "parent": next_parent,
                "blob": f"{text} {sensor_id} {hardware_id} {next_parent}".lower(),
            }
        )
    for child in node.get("Children") or []:
        if isinstance(child, dict):
            rows.extend(_flatten_lhm(child, next_parent, next_hardware))
    # Some LHM builds nest under Children of root only — also accept list roots
    return rows


def _pick(
    rows: list[dict[str, Any]],
    *,
    want_gpu: bool,
    types: tuple[str, ...],
    names: tuple[str, ...],
) -> float | None:
    best: tuple[int, float] | None = None
    type_set = {t.lower() for t in types}
    for row in rows:
        stype = str(row.get("sensor_type") or "").lower()
        if stype not in type_set:
            continue
        blob = str(row.get("blob") or "")
        is_gpu = "gpu" in blob or "/gpu" in blob or "nvidia" in blob or "radeon" in blob
        if want_gpu and not is_gpu:
            continue
        if not want_gpu and is_gpu:
            continue
        name = str(row.get("name") or "")
        score = 0
        for i, needle in enumerate(names):
            if needle.lower() in name.lower() or needle.lower() in blob:
                score = 100 - i
                break
        if score == 0 and want_gpu and stype == "load" and "core" in name.lower():
            score = 50
        if score == 0:
            continue
        value = float(row["value"])
        if best is None or score > best[0]:
            best = (score, value)
    return None if best is None else best[1]


def _pick_vram_used(rows: list[dict[str, Any]]) -> float | None:
    for row in rows:
        blob = str(row.get("blob") or "")
        name = str(row.get("name") or "").lower()
        if "gpu" not in blob and "nvidia" not in blob:
            continue
        if "memory" in name and "used" in name:
            return _to_gb(float(row["value"]), name)
    return None


def _pick_vram_total(rows: list[dict[str, Any]]) -> float | None:
    for row in rows:
        blob = str(row.get("blob") or "")
        name = str(row.get("name") or "").lower()
        if "gpu" not in blob and "nvidia" not in blob:
            continue
        if "memory" in name and ("total" in name or "dedicated" in name):
            return _to_gb(float(row["value"]), name)
    return None


def _to_gb(value: float, name: str) -> float:
    lowered = name.lower()
    if "mb" in lowered:
        return value / 1024.0
    if "gb" in lowered:
        return value
    # LHM often reports MB without unit in name
    if value > 32:
        return value / 1024.0
    return value


def _parse_number(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        return None if value != value else value
    text = str(raw).replace(",", ".")
    num = ""
    for ch in text:
        if ch.isdigit() or ch in ".-":
            num += ch
        elif num:
            break
    if not num or num in {"-", ".", "-."}:
        return None
    try:
        return float(num)
    except ValueError:
        return None


def _first(*vals: Any) -> Any:
    for val in vals:
        if val is not None:
            return val
    return None


def _snapshot_ini(path: Path) -> dict[str, Any]:
    keys = (
        "GPUVideoMemMB",
        "MaxCars",
        "MaxCarsUnderSteward",
        "ShadowMaps",
        "MSAA",
        "RenderWidth",
        "RenderHeight",
        "ParticleDensity",
        "FoliageDensity",
        "NumLights",
        "UseFoveatedRendering",
    )
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"path": str(path), "error": str(exc)}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        key = key.strip()
        if key in keys:
            found[key] = val.strip()
    return {"path": str(path), "keys": found}


def _probe_sources(lhm_url: str) -> dict[str, bool]:
    lhm = read_lhm(lhm_url)
    nvml = read_nvml()
    ir = read_iracing()
    return {"lhm": bool(lhm.get("ok")), "nvml": bool(nvml.get("ok")), "iracing": bool(ir.get("ok"))}


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "sample" or "fps" in obj or "gpu_load" in obj:
                if obj.get("type") == "meta":
                    continue
                yield obj


if __name__ == "__main__":
    raise SystemExit(main())
