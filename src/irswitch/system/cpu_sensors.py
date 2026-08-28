"""CPU package temperature/power. Optional backends; never crash the sampler."""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PSUTIL_TEMP_LOGGED = False
_LHM_NET_LOGGED = False
_CPU_SENSORS_EMPTY_LOGGED = False
_LHM_LOCK = threading.Lock()
_LHM_COMPUTER: Any = None
_LHM_DLL_LOADED: str | None = None

_WMI_CACHE: tuple[float, dict[str, float | None], float] | None = None
_WMI_TTL_HIT = 2.0
_WMI_TTL_MISS = 5.0
_WMI_NAMESPACES = ("root/LibreHardwareMonitor", "root/OpenHardwareMonitor")
_CREATE_NO_WINDOW = 0x08000000

_RAPL_LAST: tuple[float, float] | None = None  # monotonic, energy_uj
_RAPL_PATHS = (
    Path("/sys/class/powercap/intel-rapl:0/energy_uj"),
    Path("/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"),
)

HWiNFO_MAP_NAMES = ("Global\\HWiNFO_SENS_SM2", "HWiNFO_SENS_SM2")
HWiNFO_HEADER_SIZE = 44
HWiNFO_TYPE_TEMP = 1
HWiNFO_TYPE_POWER = 5


def pick_cpu_package(sensors: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    """Choose CPU package temp/power from a list of hardware-monitor sensors."""
    temperature: float | None = None
    power: float | None = None
    temp_score = -1
    power_score = -1
    for raw in sensors:
        name = str(raw.get("name") or "")
        ident = str(raw.get("identifier") or "")
        parent = str(raw.get("parent") or "")
        stype = str(raw.get("sensor_type") or raw.get("type") or "").strip().lower()
        value = _as_float(raw.get("value"))
        if value is None:
            continue
        blob = f"{name} {ident} {parent}".lower()
        if _looks_like_gpu(blob):
            continue
        if not _looks_like_cpu(blob):
            continue
        if stype in {"temperature", "temp", "2"} or "temp" in stype:
            score = _temperature_score(name)
            if score > temp_score:
                temperature = value
                temp_score = score
        elif stype in {"power", "10"}:
            score = _power_score(name)
            if score > power_score:
                power = value
                power_score = score
    return {"temperature": temperature, "power": power}


def kelvin_raw_to_celsius(raw: float | None) -> float | None:
    """Convert ACPI/perf-counter Kelvin (or tenths of Kelvin) to a sane °C."""
    if raw is None:
        return None
    if raw >= 2000:
        celsius = raw / 10.0 - 273.15
    elif raw >= 200:
        celsius = raw - 273.15
    else:
        return None
    if 15.0 <= celsius <= 115.0:
        return round(celsius, 2)
    return None


def thermal_raw_to_celsius(raw: float | None) -> float | None:
    """ACPI/PDH Kelvin, tenths of Kelvin, or a value already in °C."""
    converted = kelvin_raw_to_celsius(raw)
    if converted is not None:
        return converted
    if raw is not None and 15.0 <= raw <= 115.0:
        return round(float(raw), 2)
    return None


def pick_thermal_zone(rows: Sequence[Mapping[str, Any]]) -> float | None:
    """Pick a CPU-ish ACPI/perf thermal zone. Last resort when LHM/OHM WMI is empty."""
    best: tuple[int, float] | None = None
    for row in rows:
        name = str(row.get("name") or row.get("Name") or row.get("InstanceName") or "")
        raw = None
        for key in (
            "value",
            "HighPrecisionTemperature",
            "CurrentTemperature",
            "Temperature",
        ):
            if row.get(key) is not None:
                raw = _as_float(row.get(key))
                break
        celsius = thermal_raw_to_celsius(raw)
        if celsius is None:
            continue
        lowered = name.lower()
        score = 5
        if "cpu" in lowered or "proc" in lowered:
            score = 30
        elif "tz00" in lowered or "thrm" in lowered:
            score = 20
        if best is None or score > best[0] or (score == best[0] and celsius > best[1]):
            best = (score, celsius)
    return None if best is None else best[1]


def merge_wmi_cpu_readings(
    lhm: Sequence[Mapping[str, Any]],
    ohm: Sequence[Mapping[str, Any]],
    thermal: Sequence[Mapping[str, Any]],
) -> dict[str, float | None]:
    """LHM/OHM package sensors win; Windows thermal zone fills temperature only."""
    picked = pick_cpu_package(lhm)
    if picked.get("temperature") is None and picked.get("power") is None:
        picked = pick_cpu_package(ohm)
    if picked.get("temperature") is None:
        zone = pick_thermal_zone(thermal)
        if zone is not None:
            picked = {"temperature": zone, "power": picked.get("power")}
    return picked


def resolve_lhm_dll(configured: str | None) -> str | None:
    """Use an explicit path when set; otherwise look in common install locations."""
    if configured:
        path = Path(configured)
        return str(path) if path.is_file() else configured
    for candidate in _lhm_candidate_paths():
        if candidate.is_file():
            return str(candidate)
    return None


def read_cpu_package_sensors(dll_path: str | None) -> dict[str, float | None]:
    """Best available CPU package temp/power. Later sources overwrite when they have a value."""
    result: dict[str, float | None] = {"temperature": None, "power": None}
    for reader in (
        _read_psutil_cpu_sensors,
        _read_rapl_power,
        _read_pdh_thermal,
        _read_lhm_http,
        _read_hardware_monitor_wmi,
        lambda: _read_lhm(dll_path if dll_path and Path(dll_path).is_file() else None),
    ):
        try:
            extra = reader()
        except Exception:
            logger.debug("CPU package sensor reader failed", exc_info=True)
            extra = {}
        for key in ("temperature", "power"):
            value = extra.get(key)
            if value is not None:
                result[key] = float(value)
        if result["temperature"] is not None and result["power"] is not None:
            break
    _log_if_empty(result)
    return result


def parse_hwinfo_shared_memory(data: bytes) -> dict[str, float | None]:
    """Parse a HWiNFO shared-memory snapshot (SENS_SM2)."""
    if len(data) < HWiNFO_HEADER_SIZE:
        return {}
    offset_sensor, size_sensor, num_sensor, offset_reading, size_reading, num_reading = (
        struct.unpack_from("<IIIIII", data, 20)
    )
    if size_reading < 12 + 128 + 128 + 16 + 8 or num_reading > 4096 or num_sensor > 1024:
        return {}
    gpu_indexes: set[int] = set()
    for i in range(num_sensor):
        start = offset_sensor + i * size_sensor
        chunk = data[start : start + size_sensor]
        if len(chunk) < 8 + 128:
            continue
        orig = _cstr(chunk[8 : 8 + 128])
        user = _cstr(chunk[8 + 128 : 8 + 256]) if len(chunk) >= 8 + 256 else ""
        if _looks_like_gpu(f"{orig} {user}".lower()):
            gpu_indexes.add(i)
    rows: list[dict[str, Any]] = []
    for i in range(num_reading):
        start = offset_reading + i * size_reading
        chunk = data[start : start + size_reading]
        if len(chunk) < 12 + 128 + 128 + 16 + 8:
            continue
        reading_type, sensor_index = struct.unpack_from("<II", chunk, 0)
        if sensor_index in gpu_indexes:
            continue
        label = _cstr(chunk[12 : 12 + 128])
        user = _cstr(chunk[12 + 128 : 12 + 256])
        value_off = 12 + 128 + 128 + 16
        (value,) = struct.unpack_from("<d", chunk, value_off)
        sensor_name = ""
        sensor_start = offset_sensor + sensor_index * size_sensor
        if 0 <= sensor_index < num_sensor and sensor_start + 8 + 128 <= len(data):
            sensor_name = _cstr(data[sensor_start + 8 : sensor_start + 8 + 128])
        stype = {HWiNFO_TYPE_TEMP: "temperature", HWiNFO_TYPE_POWER: "power"}.get(
            reading_type, str(reading_type)
        )
        rows.append(
            {
                "name": user or label,
                "sensor_type": stype,
                "value": value,
                "identifier": label,
                "parent": sensor_name,
            }
        )
    return pick_cpu_package(rows)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _cstr(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("latin-1", errors="replace").strip()


def _looks_like_gpu(blob: str) -> bool:
    return any(token in blob for token in ("gpu", "nvidia", "geforce", "radeon", "intel arc"))


def _looks_like_cpu(blob: str) -> bool:
    return any(
        token in blob
        for token in (
            "cpu",
            "amdcpu",
            "intelcpu",
            "/intelcpu/",
            "/amdcpu/",
            "package",
            "tctl",
            "tdie",
            "ryzen",
            "threadripper",
            "epyc",
            "core(tm)",
            "core tm",
        )
    )


def _temperature_score(name: str) -> int:
    lowered = name.lower()
    if "package" in lowered:
        return 40
    if "tctl" in lowered or "tdie" in lowered:
        return 30
    if "ccd" in lowered:
        return 15
    if "core" in lowered:
        return 5
    return 1


def _power_score(name: str) -> int:
    lowered = name.lower()
    if "package" in lowered:
        return 40
    if "ppt" in lowered:
        return 30
    if "cores" in lowered:
        return 5
    return 1


def _log_if_empty(result: dict[str, float | None]) -> None:
    global _CPU_SENSORS_EMPTY_LOGGED
    if result.get("temperature") is not None or result.get("power") is not None:
        return
    if _CPU_SENSORS_EMPTY_LOGGED:
        return
    _CPU_SENSORS_EMPTY_LOGGED = True
    logger.info(
        "CPU package temp/power still empty. LibreHardwareMonitor 0.9.5+ removed WMI; "
        "keep Options → Remote Web Server → Run and File → Hardware → CPU checked "
        "(http://127.0.0.1:8085/data.json, or the NIC LHM bound to). Older LHM still uses "
        "root/LibreHardwareMonitor via Get-WmiObject."
    )


def _read_psutil_cpu_sensors() -> dict[str, float | None]:
    global _PSUTIL_TEMP_LOGGED
    try:
        import psutil
    except ImportError:
        return {}
    temps = getattr(psutil, "sensors_temperatures", None)
    if temps is None:
        return {}
    try:
        grouped = temps() or {}
    except Exception:
        if not _PSUTIL_TEMP_LOGGED:
            logger.debug("psutil.sensors_temperatures failed", exc_info=True)
            _PSUTIL_TEMP_LOGGED = True
        return {}
    rows: list[dict[str, Any]] = []
    for chip, entries in grouped.items():
        chip_l = str(chip).lower()
        if _looks_like_gpu(chip_l):
            continue
        for entry in entries:
            label = getattr(entry, "label", "") or chip
            current = getattr(entry, "current", None)
            rows.append(
                {
                    "name": label,
                    "sensor_type": "temperature",
                    "value": current,
                    "identifier": chip,
                    "parent": chip,
                }
            )
    picked = pick_cpu_package(rows)
    if picked.get("temperature") is None and rows:
        # Linux coretemp/k10temp often labels the package clearly; if the CPU
        # filter missed (generic 'acpi'), keep the first plausible chip reading.
        for chip, entries in grouped.items():
            if _looks_like_gpu(str(chip).lower()):
                continue
            if str(chip).lower() in {"coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"}:
                for entry in entries:
                    current = _as_float(getattr(entry, "current", None))
                    if current is not None:
                        picked["temperature"] = current
                        break
            if picked.get("temperature") is not None:
                break
    return picked


def _read_rapl_power() -> dict[str, float | None]:
    global _RAPL_LAST
    path = next((candidate for candidate in _RAPL_PATHS if candidate.is_file()), None)
    if path is None:
        return {}
    try:
        energy_uj = float(path.read_text().strip())
    except (OSError, ValueError):
        return {}
    now = time.monotonic()
    prev = _RAPL_LAST
    _RAPL_LAST = (now, energy_uj)
    if prev is None:
        return {}
    dt = now - prev[0]
    if dt <= 0:
        return {}
    watts = (energy_uj - prev[1]) / (dt * 1_000_000.0)
    if watts < 0 or watts > 500:
        return {}
    return {"power": watts}


def _read_pdh_thermal() -> dict[str, float | None]:
    try:
        from irswitch.system.pdh_thermal import read_pdh_thermal_rows
    except Exception:
        return {}
    try:
        rows = read_pdh_thermal_rows()
    except Exception:
        logger.debug("PDH thermal zone failed", exc_info=True)
        return {}
    celsius = pick_thermal_zone(rows)
    if celsius is None:
        return {}
    return {"temperature": celsius}


def _read_lhm_http() -> dict[str, float | None]:
    try:
        from irswitch.system.lhm_http import fetch_lhm_http_rows
    except Exception:
        return {}
    try:
        rows = fetch_lhm_http_rows()
    except Exception:
        logger.debug("LibreHardwareMonitor HTTP read failed", exc_info=True)
        return {}
    return pick_cpu_package(rows)


def _read_hardware_monitor_wmi(
    fetch: Callable[[str], list[dict[str, Any]]] | None = None,
) -> dict[str, float | None]:
    if sys.platform != "win32" and fetch is None:
        return {}
    global _WMI_CACHE
    now = time.monotonic()
    if _WMI_CACHE is not None:
        cached_at, cached, ttl = _WMI_CACHE
        if now - cached_at < ttl:
            return cached
    if fetch is not None:
        picked: dict[str, float | None] = {}
        for namespace in _WMI_NAMESPACES:
            try:
                rows = fetch(namespace)
            except Exception:
                logger.debug("WMI %s query failed", namespace, exc_info=True)
                rows = []
            candidate = pick_cpu_package(rows)
            if candidate.get("temperature") is not None or candidate.get("power") is not None:
                picked = candidate
                break
    else:
        bundle = _fetch_wmi_bundle()
        picked = merge_wmi_cpu_readings(
            bundle.get("lhm") or [],
            bundle.get("ohm") or [],
            (bundle.get("tz") or []) + (bundle.get("acpi") or []),
        )
    ttl = _WMI_TTL_HIT if picked else _WMI_TTL_MISS
    _WMI_CACHE = (now, picked, ttl)
    return picked


def _fetch_wmi_bundle() -> dict[str, list[dict[str, Any]]]:
    if sys.platform != "win32":
        return {}
    try:
        return _win32com_wmi_bundle()
    except Exception:
        logger.debug("win32com WMI bundle failed", exc_info=True)
        return _powershell_wmi_bundle()


def _fetch_wmi_sensors(namespace: str) -> list[dict[str, Any]]:
    if sys.platform != "win32":
        return []
    try:
        import win32com.client  # type: ignore[import-untyped]

        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        return _com_query_sensors(locator, namespace.replace("/", "\\"))
    except Exception:
        return _powershell_cim_sensors(namespace)


def _com_query_sensors(locator: Any, namespace: str) -> list[dict[str, Any]]:
    try:
        service = locator.ConnectServer(".", namespace)
        items = service.ExecQuery("SELECT Name, SensorType, Value, Identifier FROM Sensor")
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append(
            {
                "name": str(getattr(item, "Name", "")),
                "sensor_type": str(getattr(item, "SensorType", "")),
                "value": getattr(item, "Value", None),
                "identifier": str(getattr(item, "Identifier", "")),
            }
        )
    return rows


def _win32com_wmi_bundle() -> dict[str, list[dict[str, Any]]]:
    import win32com.client

    locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
    return {
        "lhm": _com_query_sensors(locator, "root\\LibreHardwareMonitor"),
        "ohm": _com_query_sensors(locator, "root\\OpenHardwareMonitor"),
        "tz": _com_query_class(
            locator,
            "root\\cimv2",
            "SELECT Name, Temperature, HighPrecisionTemperature "
            "FROM Win32_PerfFormattedData_Counters_ThermalZoneInformation",
            name_attr="Name",
            value_attrs=("HighPrecisionTemperature", "Temperature"),
        ),
        "acpi": _com_query_class(
            locator,
            "root\\wmi",
            "SELECT InstanceName, CurrentTemperature FROM MSAcpi_ThermalZoneTemperature",
            name_attr="InstanceName",
            value_attrs=("CurrentTemperature",),
        ),
    }


def _com_query_class(
    locator: Any,
    namespace: str,
    wql: str,
    *,
    name_attr: str,
    value_attrs: tuple[str, ...],
) -> list[dict[str, Any]]:
    try:
        service = locator.ConnectServer(".", namespace)
        items = service.ExecQuery(wql)
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for item in items:
        value = None
        for attr in value_attrs:
            value = getattr(item, attr, None)
            if value is not None:
                break
        rows.append({"name": str(getattr(item, name_attr, "")), "value": value})
    return rows


def _powershell_wmi_bundle() -> dict[str, list[dict[str, Any]]]:
    script = (
        "$ErrorActionPreference='SilentlyContinue'; "
        "[pscustomobject]@{"
        "lhm=@(Get-WmiObject -Namespace root/LibreHardwareMonitor -Class Sensor "
        "| Select-Object Name,SensorType,Value,Identifier);"
        "ohm=@(Get-WmiObject -Namespace root/OpenHardwareMonitor -Class Sensor "
        "| Select-Object Name,SensorType,Value,Identifier);"
        "tz=@(Get-CimInstance -ClassName Win32_PerfFormattedData_Counters_ThermalZoneInformation "
        "| Select-Object Name,Temperature,HighPrecisionTemperature);"
        "acpi=@(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
        "| Select-Object InstanceName,CurrentTemperature)"
        "} | ConvertTo-Json -Compress -Depth 5"
    )
    payload = _powershell_json(script, timeout=20)
    if not isinstance(payload, dict):
        return {}
    return {
        "lhm": _json_sensor_rows(payload.get("lhm")),
        "ohm": _json_sensor_rows(payload.get("ohm")),
        "tz": _json_zone_rows(
            payload.get("tz"), "Name", ("HighPrecisionTemperature", "Temperature")
        ),
        "acpi": _json_zone_rows(payload.get("acpi"), "InstanceName", ("CurrentTemperature",)),
    }


def _json_sensor_rows(raw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_json_list(raw):
        rows.append(
            {
                "name": item.get("Name"),
                "sensor_type": item.get("SensorType"),
                "value": item.get("Value"),
                "identifier": item.get("Identifier") or "",
            }
        )
    return rows


def _json_zone_rows(raw: Any, name_key: str, value_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_json_list(raw):
        value = None
        for key in value_keys:
            if item.get(key) is not None:
                value = item.get(key)
                break
        rows.append({"name": item.get(name_key), "value": value})
    return rows


def _as_json_list(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _powershell_json(script: str, *, timeout: int) -> Any:
    wrapped = (
        "$ErrorActionPreference='SilentlyContinue'; "
        "$ProgressPreference='SilentlyContinue'; "
        f"{script}; exit 0"
    )
    encoded = base64.b64encode(wrapped.encode("utf-16-le")).decode("ascii")
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encoded,
    ]
    try:
        if sys.platform == "win32":
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
        else:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        logger.debug("PowerShell WMI timed out or failed to start", exc_info=True)
        return None
    text = proc.stdout or ""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        if proc.stderr:
            logger.debug("PowerShell WMI stderr: %s", proc.stderr[:500])
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        logger.debug("PowerShell WMI JSON parse failed: %s", text[:300])
        return None


def _powershell_cim_sensors(namespace: str) -> list[dict[str, Any]]:
    script = (
        f"$ErrorActionPreference='SilentlyContinue'; "
        f"Get-CimInstance -Namespace '{namespace}' -ClassName Sensor | "
        "Select-Object Name,SensorType,Value,Identifier | ConvertTo-Json -Compress"
    )
    payload = _powershell_json(script, timeout=3)
    return _json_sensor_rows(payload)


def _read_hwinfo_shared_memory() -> dict[str, float | None]:
    if sys.platform != "win32":
        return {}
    import ctypes

    kernel32 = ctypes.windll.kernel32
    file_map_read = 0x0004
    for name in HWiNFO_MAP_NAMES:
        handle = kernel32.OpenFileMappingW(file_map_read, False, name)
        if not handle:
            continue
        try:
            view = kernel32.MapViewOfFile(handle, file_map_read, 0, 0, 0)
            if not view:
                continue
            try:
                header = ctypes.string_at(view, HWiNFO_HEADER_SIZE)
                if len(header) < HWiNFO_HEADER_SIZE:
                    continue
                (
                    _sig,
                    _ver,
                    _rev,
                    _poll,
                    offset_sensor,
                    size_sensor,
                    num_sensor,
                    offset_reading,
                    size_reading,
                    num_reading,
                ) = struct.unpack("<IIIQIIIIII", header)
                if (
                    size_reading < 292
                    or size_reading > 1024
                    or size_sensor > 1024
                    or num_reading > 4096
                    or num_sensor > 1024
                ):
                    continue
                end = max(
                    offset_sensor + size_sensor * num_sensor,
                    offset_reading + size_reading * num_reading,
                    HWiNFO_HEADER_SIZE,
                )
                blob = ctypes.string_at(view, min(end, 2 * 1024 * 1024))
                return parse_hwinfo_shared_memory(blob)
            finally:
                kernel32.UnmapViewOfFile(view)
        finally:
            kernel32.CloseHandle(handle)
    return {}


def _lhm_candidate_paths() -> list[Path]:
    if sys.platform != "win32":
        return []
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_app = os.environ.get("LOCALAPPDATA", "")
    names = ("LibreHardwareMonitorLib.dll",)
    roots = [
        Path(program_files) / "LibreHardwareMonitor",
        Path(program_files_x86) / "LibreHardwareMonitor",
        Path(program_files) / "Libre Hardware Monitor",
        Path(program_files_x86) / "Libre Hardware Monitor",
    ]
    if local_app:
        roots.append(Path(local_app) / "LibreHardwareMonitor")
    return [root / name for root in roots for name in names]


def _read_lhm(dll_path: str | None) -> dict[str, float | None]:
    global _LHM_NET_LOGGED, _LHM_COMPUTER, _LHM_DLL_LOADED
    if not dll_path or not Path(dll_path).is_file():
        return {}
    try:
        import clr
    except ImportError:
        if not _LHM_NET_LOGGED:
            logger.info(
                "LibreHardwareMonitor DLL found at %s but pythonnet is not installed; "
                "CPU package via LHM skipped. pip install pythonnet (extra sysinfo-lhm).",
                dll_path,
            )
            _LHM_NET_LOGGED = True
        return {}
    with _LHM_LOCK:
        try:
            if _LHM_COMPUTER is None or _LHM_DLL_LOADED != dll_path:
                if _LHM_COMPUTER is not None:
                    try:
                        _LHM_COMPUTER.Close()
                    except Exception:
                        pass
                    _LHM_COMPUTER = None
                clr.AddReference(dll_path)
                from LibreHardwareMonitor.Hardware import Computer  # type: ignore

                computer = Computer()
                computer.IsCpuEnabled = True
                computer.Open()
                _LHM_COMPUTER = computer
                _LHM_DLL_LOADED = dll_path
            rows: list[dict[str, Any]] = []
            for hardware in _LHM_COMPUTER.Hardware:
                rows.extend(_lhm_rows(hardware))
            return pick_cpu_package(rows)
        except Exception:
            logger.debug("LibreHardwareMonitor sample failed", exc_info=True)
            return {}


def _lhm_rows(hardware: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        hardware.Update()
    except Exception:
        return rows
    parent = str(getattr(hardware, "Name", ""))
    for sensor in getattr(hardware, "Sensors", ()) or ():
        rows.append(
            {
                "name": str(getattr(sensor, "Name", "")),
                "sensor_type": str(getattr(sensor, "SensorType", "")),
                "value": getattr(sensor, "Value", None),
                "identifier": str(getattr(sensor, "Identifier", "")),
                "parent": parent,
            }
        )
    for sub in getattr(hardware, "SubHardware", ()) or ():
        rows.extend(_lhm_rows(sub))
    return rows
