# iRacing (`src/irswitch/iracing/`)

**Účel:** číst shared memory (`pyirsdk`) a **extrahovat** hodnoty. Žádné rozhodování scén, žádné battle/HUD.

**Nepatří sem:** debounce, mapování na OBS scénu, TTS, overlay arbitration.

SDK sémantika (neuhádnout flagy): `.cursor/rules/iracing-sdk-semantics.mdc` a skill `iracing-sdk-display-format`.

## `IRacingReader` (`reader.py`)

- `startup()` / connect k `irsdk.IRSDK()`
- `read_mode()` → `DrivingMode | None` (disconnected = `None`, ne exception)
- `read_telemetry()` → `TelemetrySnapshot`
- `is_connected()`, `is_process_running()` (Windows `tasklist`, cache 1 s; z async kódu přes `asyncio.to_thread`)
- QUIT: `SessionTime` se nehýbe `quit_stall_seconds` (config `[iracing]`)

Main loop používá process+SDK k detekci **LOADING** (proces běží, SDK ještě ne).

## Mód (`extractors.py`)

Priorita: **GARAGE > REPLAY > RACE > LOBBY**.

- GARAGE = `IsGarageVisible` (garage **UI**). `IsInGarage` / `PlayerCarInGarage` = auto ve stání — to je i lobby po loadu, **samo o sobě to není GARAGE**.
- Fallback stall+ne-session-screen jen když `IsGarageVisible` chybí.
- `IDLE` je deprecated; aktivní hra bez on-track je `LOBBY`.

Po LOADING/CONNECTING state machine drží **LOBBY i GARAGE** v grace 3000 ms. Neobcházej to v extractoru.

Další extractory: session type/name/num, total sessions — pro dashboard a kapitoly, ne pro HUD battle.

## Telemetrie (`telemetry.py`, `overlay.models.TelemetrySnapshot`)

Raw pole: pozice, lapy, gapy dist, `CarIdx*` tuple, session flags, pit, FPS, …  
`data_quality`: `ok` / `degraded` / `stale`. Disconnect snapshot: `TelemetrySnapshot.disconnected()`.

Jednotky a sentinely (`-1`, `32767`, `604800`): `sdk_units.py` + skill display format. Overlay formátuje časy; WS `metrics` zůstávají čísla.

## Další soubory

| Soubor | Co |
| --- | --- |
| `drivers.py` | Display name z DriverInfo |
| `sectors.py` | `sector_start_pcts` → body pro timing |
| `session_context.py` | track / subsession |
| `sof.py` | SoF |
| `weather.py` | teplota, vítr, srážky (overlay + budoucí observer) |
| `trk_loc.py` | track location |

## Config

`[iracing] poll_hz`, `quit_stall_seconds` — [CONFIG.md](../../../CONFIG.md).

## Testy

`tests/test_reader.py`, `tests/test_extractors.py`, `tests/test_sdk_units.py`, `tests/test_irsdk_*.py`, `tests/test_iracing_weather.py`, `tests/test_sof.py`, `tests/test_session_context.py`.

## In-flight

#181 přidává `iracing/session_flags.py` (decode `irsdk_Flags`, **jen extraction**) a rozšiřuje telemetry o Speed, `CarIdxBestLapTime`, flag bits na `RaceState`. Na master tyto soubory/pole nejsou komplet. Viz [pr-181](../inflight/pr-181-narrative-observers.md).
