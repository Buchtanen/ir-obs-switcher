# Architektura

Windows-first dlouho běžící služba: iRacing stav → OBS scény + overlay HUD + commentary TTS. Vstup: `irswitchd` (`src/irswitch/main.py`). HTTP `app.http_host`:`app.http_port` (default `127.0.0.1:17321`).

Dva nezávislé pipeline sdílí čtení iRacing a config. **Scene switcher nerozhoduje HUD eventy. Overlay nepřepíná scény.**

## Vrstvy

```text
                    config.ini  →  AppConfig (config.py)
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                    ▼
           IRacingReader         ObsClient           Race composition
            iracing/               obs/              race/runtime.py
                 │                    │                    │
                 ▼                    │                    ▼
           DrivingMode                │              TelemetrySnapshot
                 │                    │                    │
                 ▼                    │                    ▼
           StateMachine               │              RaceState + observer
             logic/                   │                 race/
                 │                    │                    │
                 ▼                    │                    ▼
           Policy (mód→scéna)         │               EventEngine
                 │                    │                 events/
                 └──── set_scene ─────┘                    │
                                                           ▼
                                                    EventManager(V2)
                                                           │
                                                    AsyncEventFanout
                                                           │
                                              ┌────────────┴────────────┐
                                              ▼                         ▼
                                       OverlayConsumer           CommentaryConsumer
                                       OverlayBus / HUD            director + TTS
```

Na `master` jsou overlay a commentary **peer consumery** (N12: `events/async_fanout.py`, `race/runtime.py`). Ne řetěz jen přes `OverlayRuntime._observe_commentary`.

## Dvě smyčky

### 1. Scene switcher — `main_loop` (`main.py`)

Perioda: `1 / iracing.poll_hz`.

1. Hot-reload `get_app_config()`.
2. `reader.read_mode()` → `DrivingMode | None`.
3. Loading / QUIT / RESTART.
4. `state_machine.tick` → `SwitchState`.
5. `obs_client.set_scene` když se smí přepnout.
6. Auto-start / auto-stop broadcast.
7. YouTube title refresh (nesmí shodit loop).
8. Metriky, event log, WS `/ws`.

Selhání iRacing/OBS se polyká.

### 2. Overlay + commentary — `race/runtime.py`

Vlastní tasky (`TaskRegistry`). Hz z `[sampling]`.

1. `read_telemetry()` → `TelemetrySnapshot` (nebo mock/replay).
2. Session reset, timing crossings, `RaceContextAnalyzer` / observer.
3. Sidecar (`InCarDetector`, `SessionBriefsDetector`).
4. `EventEngine.tick` → kandidáti → manager → accepted batch.
5. `AsyncEventFanout` → `OverlayConsumer` + `CommentaryConsumer`.

Módy overlay: `live` | `mock` | `replay`.

## Operator UI

- `/gr-status` — switcher controls
- `/admin` — extensions / activity
- `/overlay/` — HUD (OBS Browser Source)
- `/commentary` — TTS test page

Není TUI. Není `/vr-status`.

## Co kam nepatří

| Chování | Patří | Nepatří |
| --- | --- | --- |
| GARAGE vs LOBBY | `iracing/extractors.py` + `logic/` | Overlay eventy |
| Battle karta | `events/battle.py` + overlay WS | `logic/` |
| TTS | `commentary/director.py` | `obs/client.py` policy |
| Volume duck | `commentary/duck.py` přes OBS API | State machine |
| YouTube titulek | `oauth.py` + `obs/` | Scene policy |
