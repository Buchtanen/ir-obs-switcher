# Architektura

Windows-first dlouho běžící služba: iRacing stav → OBS scény + volitelný overlay HUD + commentary TTS. Vstup: `irswitchd` (`src/irswitch/main.py`). HTTP na `app.http_host`:`app.http_port` (default `127.0.0.1:17321`).

Dva nezávislé pipeline sdílí čtení iRacing a config. **Scene switcher nerozhoduje HUD eventy. Overlay nepřepíná scény.**

## Vrstvy

```text
                    config.ini  →  AppConfig (config.py)
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                    ▼
           IRacingReader         ObsClient            OverlayRuntime
            iracing/               obs/                 overlay/
                 │                    │                    │
                 ▼                    │                    ▼
           DrivingMode                │              TelemetrySnapshot
                 │                    │                    │
                 ▼                    │                    ▼
           StateMachine               │            RaceContextAnalyzer
             logic/                   │                 race/
                 │                    │                    │
                 ▼                    │                    ▼
           Policy (mód→scéna)         │               RaceState
                 │                    │                    │
                 └──── set_scene ─────┘                    ▼
                                                     EventEngine
                                                      events/
                                                           │
                                                           ▼
                                                    EventManager(V2)
                                                           │
                                              ┌────────────┴────────────┐
                                              ▼                         ▼
                                         OverlayBus              CommentaryDirector
                                         WS /ws/overlay            commentary/ TTS
```

Na `master` commentary **není** peer fan-out. `OverlayRuntime._emit_from_race` po arbitraci volá `_observe_commentary` (řetěz). Cílový tvar peer consumers je v [#179](inflight/pr-179-observers-decoupling.md) — **není na master**.

## Dvě smyčky

### 1. Scene switcher — `main_loop` (`main.py`)

Perioda: `1 / iracing.poll_hz`.

Každý tick (zjednodušeně):

1. Hot-reload: `get_app_config()` (po `POST /config/reload`).
2. `reader.read_mode()` → `DrivingMode | None`.
3. Loading: proces `iRacingSim64DX11.exe` běží a SDK ještě ne (thread: `is_process_running`).
4. QUIT / RESTART (stall `SessionTime`, hotkey).
5. `state_machine.tick(...)` → nový `SwitchState` (debounce, cooldown, override, grace po loadu).
6. Pokud `target_scene != current_scene` a smí se přepnout → `obs_client.set_scene`.
7. Auto-start / auto-stop broadcast podle `[switching]`.
8. Stream title / YouTube refresh (OAuth, nesmí shodit loop).
9. Metriky, event log, WS `/ws` broadcast.

Selhání iRacing/OBS se polyká; loop pokračuje.

### 2. Overlay — `OverlayRuntime` (`overlay/runtime.py`)

Vlastní tasky v `TaskRegistry` (race tick, system tick, bio, flush). Hz z `[sampling]` — viz [sampling](domeny/sampling.md).

Race tick:

1. `read_telemetry()` → `TelemetrySnapshot` (nebo mock/replay).
2. `SessionCoordinator` — reset pipeline při změně session/track.
3. Timing crossings (`race/timing`) když jsou T2 flagy.
4. `RaceContextAnalyzer.analyze` → `RaceState`.
5. Sidecar commentary (`InCarDetector`, `SessionBriefsDetector`) mimo EventEngine.
6. `EventEngine.tick` → `CandidateEvent[]`.
7. `EventManager` / `EventManagerV2` — cooldown, duration, pit guard, V4 envelope.
8. Publish na `OverlayBus` (WS) + `_observe_commentary`.

Módy overlay: `live` | `mock` (`--mock`) | `replay` (`--replay JSONL`).

## Sdílený stav (glue)

`server/api.py` drží process-wide holdery (`set_current_state`, `set_obs_client`, …). HTTP handlery **čtou / spouštějí override**, ale mód z telemetrie počítá jen `StateMachine`.

Single-instance: před těžkým initem bind na `http_host:http_port` (`util/single_instance.py`). Druhý start = exit 2.

## Co kam nepatří

| Chování | Patří | Nepatří |
| --- | --- | --- |
| Mód GARAGE vs LOBBY | `iracing/extractors.py` + `logic/state_machine.py` | Overlay eventy |
| Battle HUD karta | `events/battle.py` + overlay WS | `logic/` |
| TTS věta | `commentary/director.py` | `obs/client.py` |
| Volume duck | `commentary/duck.py` přes OBS client API | State machine |
| YouTube titulek | `oauth.py` + `obs/` | Scene policy |

## Související

- [Hranice vrstev](jak-cist.md#hranice-vrstev-neměnit-bez-explicitního-zadání)
- [Runtime](domeny/runtime.md)
- [Stav vs PR](stav.md)
