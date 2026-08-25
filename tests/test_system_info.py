"""System history aggregation, CPU package sensors, null-safe merge."""

from __future__ import annotations

import struct
from pathlib import Path

from irswitch.overlay.models import CPUState, GPUState, MemoryState
from irswitch.overlay.settings import SystemInfoSettings
from irswitch.system import cpu_sensors
from irswitch.system.history import MetricHistory
from irswitch.system.provider import collect_system_state


def test_metric_history_avg_and_max() -> None:
    hist = MetricHistory(keep_seconds=60)
    hist.add(0, 10)
    hist.add(5, 30)
    hist.add(9, 20)
    assert hist.average(10, 9) == 20
    assert hist.maximum(60, 9) == 30


def test_collect_without_optional_backends() -> None:
    state = collect_system_state(SystemInfoSettings(enabled=True))
    assert state.cpu is not None
    assert state.gpu is not None
    assert state.memory is not None
    # Missing backends leave nullable fields, never crash.
    _ = state.to_dict()


def test_pick_cpu_package_prefers_package_over_core_and_skips_gpu() -> None:
    picked = cpu_sensors.pick_cpu_package(
        [
            {
                "name": "GPU Core",
                "sensor_type": "Temperature",
                "value": 80,
                "identifier": "/nvidiagpu/0/temperature/0",
            },
            {
                "name": "Core #1",
                "sensor_type": "Temperature",
                "value": 60,
                "identifier": "/amdcpu/0/temperature/1",
            },
            {
                "name": "CPU Package",
                "sensor_type": "Temperature",
                "value": 71,
                "identifier": "/amdcpu/0/temperature/2",
            },
            {
                "name": "Package",
                "sensor_type": "Power",
                "value": 88,
                "identifier": "/amdcpu/0/power/0",
            },
            {
                "name": "GPU Power",
                "sensor_type": "Power",
                "value": 250,
                "identifier": "/nvidiagpu/0/power/0",
            },
        ]
    )
    assert picked == {"temperature": 71.0, "power": 88.0}


def test_resolve_lhm_dll_autodiscovers_when_unconfigured(tmp_path: Path, monkeypatch) -> None:
    dll = tmp_path / "LibreHardwareMonitorLib.dll"
    dll.write_bytes(b"x")
    monkeypatch.setattr(cpu_sensors, "_lhm_candidate_paths", lambda: [dll])
    assert cpu_sensors.resolve_lhm_dll(None) == str(dll)
    missing = tmp_path / "missing.dll"
    assert cpu_sensors.resolve_lhm_dll(str(missing)) == str(missing)


def test_parse_hwinfo_shared_memory_reads_cpu_package() -> None:
    picked = cpu_sensors.parse_hwinfo_shared_memory(_hwinfo_blob())
    assert picked["temperature"] == 72.5
    assert picked["power"] == 91.0


def test_wmi_reader_uses_injected_fetch() -> None:
    cpu_sensors._WMI_CACHE = None
    rows = [
        {
            "name": "CPU Package",
            "sensor_type": "Temperature",
            "value": 66,
            "identifier": "/intelcpu/0/temperature/0",
        }
    ]
    picked = cpu_sensors._read_hardware_monitor_wmi(fetch=lambda _ns: rows)
    assert picked["temperature"] == 66.0
    cpu_sensors._WMI_CACHE = None


def test_kelvin_raw_to_celsius_tenths_and_kelvin() -> None:
    assert cpu_sensors.kelvin_raw_to_celsius(3132) == 40.05
    assert cpu_sensors.kelvin_raw_to_celsius(313.15) == 40.0
    assert cpu_sensors.kelvin_raw_to_celsius(40) is None
    assert cpu_sensors.thermal_raw_to_celsius(55) == 55.0
    assert cpu_sensors.thermal_raw_to_celsius(3132) == 40.05


def test_merge_wmi_prefers_lhm_then_thermal_zone() -> None:
    lhm = [
        {
            "name": "CPU Package",
            "sensor_type": "Temperature",
            "value": 71,
            "identifier": "/amdcpu/0/temperature/2",
        },
        {
            "name": "Package",
            "sensor_type": "Power",
            "value": 88,
            "identifier": "/amdcpu/0/power/0",
        },
    ]
    zone = [{"name": "CPU", "value": 3132}]
    picked = cpu_sensors.merge_wmi_cpu_readings(lhm, [], zone)
    assert picked == {"temperature": 71.0, "power": 88.0}
    fallback = cpu_sensors.merge_wmi_cpu_readings([], [], zone)
    assert fallback["temperature"] == 40.05
    assert fallback.get("power") is None


def test_pick_cpu_package_accepts_lhm_numeric_sensor_types() -> None:
    picked = cpu_sensors.pick_cpu_package(
        [
            {
                "name": "CPU Package",
                "sensor_type": 2,
                "value": 64,
                "identifier": "/intelcpu/0/temperature/2",
            },
            {
                "name": "Package",
                "sensor_type": 10,
                "value": 91,
                "identifier": "/intelcpu/0/power/0",
            },
        ]
    )
    assert picked == {"temperature": 64.0, "power": 91.0}


def test_parse_lhm_http_json_package_sensors() -> None:
    from irswitch.system.lhm_http import parse_lhm_data_json

    payload = {
        "Text": "Computer",
        "Children": [
            {
                "Text": "AMD Ryzen 9",
                "HardwareId": "/amdcpu/0",
                "Children": [
                    {
                        "Text": "Core (Tctl/Tdie)",
                        "Value": "46.9 °C",
                        "SensorId": "/amdcpu/0/temperature/2",
                        "Type": "Temperature",
                        "Children": [],
                    },
                    {
                        "Text": "Package",
                        "Value": "88.0 W",
                        "SensorId": "/amdcpu/0/power/0",
                        "Type": "Power",
                        "Children": [],
                    },
                    {
                        "Text": "GPU Core",
                        "Value": "70 °C",
                        "SensorId": "/gpu-nvidia/0/temperature/0",
                        "Type": "Temperature",
                        "Children": [],
                    },
                ],
            }
        ],
    }
    rows = parse_lhm_data_json(payload)
    picked = cpu_sensors.pick_cpu_package(rows)
    assert picked["temperature"] == 46.9
    assert picked["power"] == 88.0


def test_collect_merges_cpu_package_sensors(monkeypatch) -> None:
    monkeypatch.setattr(
        "irswitch.system.provider.read_cpu_package_sensors",
        lambda _path: {"temperature": 71.0, "power": 88.0},
    )
    monkeypatch.setattr(
        "irswitch.system.provider._read_psutil",
        lambda: (
            CPUState(load=9.0, frequency=3.4),
            MemoryState(used=8.0, total=32.0, percent=25.0),
        ),
    )
    monkeypatch.setattr("irswitch.system.provider._read_nvml", lambda: GPUState())
    state = collect_system_state(SystemInfoSettings(enabled=True))
    assert state.cpu.load == 9.0
    assert state.cpu.frequency == 3.4
    assert state.cpu.temperature == 71.0
    assert state.cpu.power == 88.0


def _hwinfo_blob() -> bytes:
    size_sensor = 8 + 128 + 128
    size_reading = 12 + 128 + 128 + 16 + 32
    num_sensor = 2
    num_reading = 4
    offset_sensor = 44
    offset_reading = offset_sensor + size_sensor * num_sensor
    header = struct.pack(
        "<IIIQIIIIII",
        0,
        2,
        0,
        0,
        offset_sensor,
        size_sensor,
        num_sensor,
        offset_reading,
        size_reading,
        num_reading,
    )

    def sensor(name: str) -> bytes:
        padded = name.encode("ascii").ljust(128, b"\0")[:128]
        return struct.pack("<II", 1, 0) + padded + padded

    def reading(kind: int, sensor_index: int, label: str, value: float) -> bytes:
        padded = label.encode("ascii").ljust(128, b"\0")[:128]
        unit = b"\0" * 16
        return (
            struct.pack("<III", kind, sensor_index, 0)
            + padded
            + padded
            + unit
            + struct.pack("<dddd", value, 0.0, 0.0, 0.0)
        )

    body = (
        sensor("AMD Ryzen 9")
        + sensor("NVIDIA GeForce RTX")
        + reading(cpu_sensors.HWiNFO_TYPE_TEMP, 0, "CPU Package", 72.5)
        + reading(cpu_sensors.HWiNFO_TYPE_TEMP, 0, "Core 0", 60.0)
        + reading(cpu_sensors.HWiNFO_TYPE_POWER, 0, "CPU Package Power", 91.0)
        + reading(cpu_sensors.HWiNFO_TYPE_TEMP, 1, "GPU Core", 80.0)
    )
    return header + body
