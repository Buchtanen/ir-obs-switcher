# Runtime (`main.py`)

**Účel:** nastartovat službu, vlastnit main loop scene switcheru, zapojit HTTP, overlay runtime, OAuth, single-instance.

**Nepatří sem:** interpretace race gapa, HUD eventy, TTS výběr věty. To dělá `OverlayRuntime`.

## Entry

- Konzolový skript: `irswitchd` → `irswitch.main:main` (`pyproject.toml`)
- CLI: `--config` (povinné), `--mock`, `--replay PATH`
- PowerShell: `start_app.ps1` (preferuje `.venv`, čistí `SSLKEYLOGFILE`)

`main()` → parse args → `load_config` → `asyncio.run(run_service(...))`.

## `run_service`

Pořadí (zjednodušeně):

1. Logging (`util/logging.py`)
2. `ensure_single_instance(http_host, http_port)` — fail fast, exit 2
3. i18n jazyk dashboardu
4. Hotkey listener (volitelně, RESTART)
5. `IRacingReader.startup()`, `ObsClient`, `Policy` + `StateMachine`
6. OAuth manager (config nebo env)
7. Event log, metriky, počáteční `SwitchState` (`CONNECTING`, `safe_scene`)
8. OBS connect **non-blocking** (1 retry na startu); validace názvů scén
9. `create_app` + `AppRunner` HTTP
10. Overlay HTTP routes + `OverlayRuntime.start`
11. OAuth flow (browser) pokud je nakonfigurováno
12. `main_loop` dokud shutdown event

Shutdown: API `POST /shutdown` / `POST /restart` (respawn přes `util/process_restart.py`). Overlay duck restore.

## `main_loop`

Jediná smyčka **scene switch**. Detail toku: [architektura.md](../architektura.md).

Další odpovědnosti v loopu (ne v `logic/`):

- Loading tracker a auto-start broadcast (`switching.auto_start_*`)
- Auto-stop po QUIT (`switching.auto_stop_stream`)
- Detekce výběru YouTube streamu v OBS (stabilita 3 čtení)
- Refresh stream info s cache (`STREAM_CACHE_FRESH_MS` / `GRACE_MS`)
- Background tasky jen přes `TaskRegistry` (`loop_background_tasks`)

## `DrivingMode` (`models.py`)

`CONNECTING`, `LOADING`, `LOBBY`, `IDLE` (deprecated alias), `GARAGE`, `RACE`, `REPLAY`, `QUIT`, `RESTART`.

`SwitchState` je frozen dataclass: konektivita, autoswitch, override, mód, scény, reason, session pole, volitelně YouTube extended info.

## Testy

`tests/test_main.py`, `tests/test_main_loop_e2e.py`, `tests/test_single_instance.py`, `tests/test_process_restart.py`.

## In-flight

#181 sahá na `main.py` (stream start / opener kontext). Na master ten hook není. Viz [pr-181](../inflight/pr-181-narrative-observers.md).
