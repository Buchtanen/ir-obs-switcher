# System info (`src/irswitch/system/`)

**Účel:** CPU/GPU/RAM/FPS karty overlay. Blocking I/O v worker thread. Chybějící psutil/NVML/LHM = prázdná pole, ne pád.

## Provider (`provider.py`)

Skládá `SystemState`: `CPUState`, `GPUState`, `MemoryState`, `PerformanceState` + `SystemHistory` (sparklines).

- **psutil** — CPU load, RAM
- **NVML** (`nvidia-ml-py`) — GPU util/temp/power
- **CPU package power/temp** — `cpu_sensors.py`: Libre Hardware Monitor HTTP (`lhm_http.py`) nebo legacy WMI; stock Windows package power nemá
- **FPS/frametime** — z iRacing telemetrie v overlay ticku, ne z LHM; mimo 3D prázdné
- PDH thermal helper: `pdh_thermal.py`

LHM 0.9.5+ zrušil WMI. Overlay čte `http://127.0.0.1:8085/data.json`. Když LHM bindne jen LAN IP, čte se `LibreHardwareMonitor.config`. Admin Extended karta: běží LHM HTTP?

Plán plného sysinfo přes LHM (nemusí být hotový): `docs/sysinfo_lhm_upgrade_spec.md`.

## Config

`[sysinfo]`, `[sampling] system.hz` — [CONFIG.md](../../../CONFIG.md). Extra: `sysinfo-lhm` (pythonnet) v pyproject — jen alias, HTTP cesta je default.

## Testy

`tests/test_system_info.py`, `tests/test_lhm_probe.py`.
