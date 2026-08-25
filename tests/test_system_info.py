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


def test_parse_lhm_http_json_via_type_nodes_and_locale() -> None:
    from irswitch.system.lhm_http import parse_lhm_data_json

    payload = {
        "Text": "Sensor",
        "Children": [
            {
                "Text": "PC",
                "Children": [
                    {
                        "Text": "AMD Ryzen 9 9950X",
                        "HardwareId": "/amdcpu/0",
                        "Children": [
                            {
                                "Text": "Temperatures",
                                "Children": [
                                    {
                                        "Text": "Core (Tctl/Tdie)",
                                        "Value": "46,9 °C",
                                        "RawValue": 46.9,
                                        "SensorId": "/amdcpu/0/temperature/2",
                                        "Type": "Temperature",
                                        "Children": [],
                                    }
                                ],
                            },
                            {
                                "Text": "Powers",
                                "Children": [
                                    {
                                        "Text": "Package",
                                        "Value": "88,0 W",
                                        "SensorId": "/amdcpu/0/power/0",
                                        "Type": "Power",
                                        "Children": [],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    picked = cpu_sensors.pick_cpu_package(parse_lhm_data_json(payload))
    assert picked == {"temperature": 46.9, "power": 88.0}


def test_parse_lhm_config_and_http_bases() -> None:
    from irswitch.system.lhm_http import iter_http_bases, parse_lhm_config

    parsed = parse_lhm_config("""<?xml version="1.0"?>
<configuration>
  <appSettings>
    <add key="listenerPort" value="18085" />
    <add key="listenerIp" value="192.168.1.50" />
  </appSettings>
</configuration>
""")
    assert parsed == {"port": 18085, "ip": "192.168.1.50"}
    bases = iter_http_bases(int(parsed["port"]), parsed["ip"])
    assert bases[0] == "http://192.168.1.50:18085"
    assert "http://127.0.0.1:18085" in bases
    wild = parse_lhm_config(
        '<add key="listenerIp" value="+" /><add key="listenerPort" value="8085" />'
    )
    assert wild["ip"] is None
    assert iter_http_bases(8085, None)[0] == "http://127.0.0.1:8085"
    public = parse_lhm_config(
        '<add key="listenerIp" value="8.8.8.8" /><add key="listenerPort" value="8085" />'
    )
    assert public["ip"] is None
    assert "http://8.8.8.8:8085" not in iter_http_bases(8085, "8.8.8.8")
    from irswitch.system.lhm_http import is_allowed_lhm_url

    assert is_allowed_lhm_url("http://127.0.0.1:8085/data.json")
    assert not is_allowed_lhm_url("https://127.0.0.1:8085/data.json")
    assert not is_allowed_lhm_url("http://example.com:8085/data.json")
    assert not is_allowed_lhm_url("http://127.0.0.1:8085/other")


def test_parse_lhm_prometheus_cpu_gauges() -> None:
    from irswitch.system.lhm_http import parse_lhm_prometheus

    text = """
# TYPE lhm_cpu_temperature_celsius gauge
lhm_cpu_temperature_celsius {"sensorName"="CPU Package", "hardwareName"="AMD Ryzen 9", "sensorId"="/temperature/2", "hardwareId"="/amdcpu/0"} 71.5
lhm_cpu_temperature_celsius {"sensorName"="CPU Package", "hardwareName"="AMD Ryzen 9", "sensorId"="/temperature/2", "hardwareId"="/amdcpu/0"} 70.0
# TYPE lhm_cpu_power_watts gauge
lhm_cpu_power_watts {"sensorName"="Package", "hardwareName"="AMD Ryzen 9", "sensorId"="/power/0", "hardwareId"="/amdcpu/0"} 88
lhm_gpuamd_temperature_celsius {"sensorName"="GPU Core", "hardwareId"="/gpu-amd/0"} 80
"""
    picked = cpu_sensors.pick_cpu_package(parse_lhm_prometheus(text))
    assert picked == {"temperature": 71.5, "power": 88.0}


def test_fetch_lhm_http_uses_bound_nic_and_gzip() -> None:
    import gzip
    import json
    import urllib.error

    from irswitch.system import lhm_http

    _reset_lhm_http(lhm_http)
    payload = {
        "Text": "Sensor",
        "Children": [
            {
                "Text": "AMD Ryzen 9",
                "HardwareId": "/amdcpu/0",
                "Children": [
                    {
                        "Text": "CPU Package",
                        "Value": "64.0 °C",
                        "SensorId": "/amdcpu/0/temperature/2",
                        "Type": "Temperature",
                        "Children": [],
                    },
                    {
                        "Text": "Package",
                        "Value": "91.0 W",
                        "SensorId": "/amdcpu/0/power/0",
                        "Type": "Power",
                        "Children": [],
                    },
                ],
            }
        ],
    }
    body = gzip.compress(json.dumps(payload).encode("utf-8"))

    def opener(request, timeout=0):
        url = request.full_url
        if "127.0.0.1" in url or "localhost" in url:
            raise urllib.error.URLError("bound to LAN only")
        if url == "http://10.0.0.8:8085/data.json":
            return _FakeHttp(body)
        raise urllib.error.URLError(url)

    rows = lhm_http.fetch_lhm_http_rows(
        opener=opener,
        now=1.0,
        config_text='<add key="listenerIp" value="10.0.0.8" /><add key="listenerPort" value="8085" />',
        force=True,
    )
    picked = cpu_sensors.pick_cpu_package(rows)
    assert picked == {"temperature": 64.0, "power": 91.0}


def test_fetch_lhm_http_falls_back_to_metrics() -> None:
    import urllib.error

    from irswitch.system import lhm_http

    _reset_lhm_http(lhm_http)
    metrics = (
        'lhm_cpu_temperature_celsius {"sensorName"="CPU Package", '
        '"hardwareId"="/intelcpu/0", "sensorId"="/temperature/0"} 55\n'
        'lhm_cpu_power_watts {"sensorName"="Package", '
        '"hardwareId"="/intelcpu/0", "sensorId"="/power/0"} 42\n'
    )

    def opener(request, timeout=0):
        if request.full_url.endswith("/data.json"):
            raise urllib.error.HTTPError(request.full_url, 404, "missing", hdrs={}, fp=None)
        if request.full_url.endswith("/metrics"):
            return _FakeHttp(metrics)
        raise urllib.error.URLError(request.full_url)

    rows = lhm_http.fetch_lhm_http_rows(opener=opener, now=2.0, config_text="", force=True)
    assert cpu_sensors.pick_cpu_package(rows) == {"temperature": 55.0, "power": 42.0}


def test_read_cpu_package_sensors_stops_after_http_hit(monkeypatch) -> None:
    monkeypatch.setattr(cpu_sensors, "_read_psutil_cpu_sensors", lambda: {})
    monkeypatch.setattr(cpu_sensors, "_read_rapl_power", lambda: {})
    monkeypatch.setattr(cpu_sensors, "_read_pdh_thermal", lambda: {})
    monkeypatch.setattr(cpu_sensors, "_read_lhm_http", lambda: {"temperature": 50.0, "power": 80.0})
    wmi_called = {"n": 0}

    def _wmi() -> dict[str, float | None]:
        wmi_called["n"] += 1
        return {"temperature": 1.0, "power": 1.0}

    monkeypatch.setattr(cpu_sensors, "_read_hardware_monitor_wmi", _wmi)
    monkeypatch.setattr(cpu_sensors, "_read_lhm", lambda _path: {"temperature": 2.0, "power": 2.0})
    picked = cpu_sensors.read_cpu_package_sensors(None)
    assert picked == {"temperature": 50.0, "power": 80.0}
    assert wmi_called["n"] == 0


class _FakeHttp:
    def __init__(self, body: bytes | str) -> None:
        self._body = body.encode("utf-8") if isinstance(body, str) else body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeHttp:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _reset_lhm_http(module: object) -> None:
    module._CACHED_ROWS = None  # type: ignore[attr-defined]
    module._CACHED_BASE = None  # type: ignore[attr-defined]
    module._CACHED_CONFIG = None  # type: ignore[attr-defined]
    module._LHM_HTTP_LOGGED = False  # type: ignore[attr-defined]
    module._LHM_HTTP_OK_LOGGED = False  # type: ignore[attr-defined]


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
