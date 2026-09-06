# Overlay (`src/irswitch/overlay/`)

**Účel:** HUD pipeline — telemetry → RaceState → eventy → WS Browser Source. Volitelně mock/replay/tape.

**Nepatří sem:** OBS scene switch. Commentary je **pozorovatel** envelope (na master řetěz z runtime, ne samostatný server).

## Orchestrace (`runtime.py`)

`OverlayRuntime` vlastní:

- `EventEngine` + `EventManager` / `EventManagerV2`
- `RaceContextAnalyzer`
- `SessionCoordinator` + reset hooky (engine, timing, commentary, in-car)
- `CommentaryDirector` (fail-soft když graph JSON spadne)
- `OverlaySessionTape`
- Sampling tasky: race, system, bio, flush 150 ms

`_emit_from_race` (master):

```text
EventEngine.tick → candidates
    → EventManagerV2.submit / tick
        → bus.publish_event (HUD)
        → _observe_commentary (TTS)
```

Bez `v2_payload`: legacy `EventManager` + `speech_envelope_from_race_event` jen pro malou mapu jmen (`lap_complete`, pit).

Sidecary mimo engine: `InCarDetector`, `SessionBriefsDetector` → rovnou commentary.

Warm-up po reconnect: state se publikuje, semantic emittery ticho.

## Bus a HTTP

- `bus.py` — snapshot race/bio/system, coalesced state, eventy; filtruje secret klíče
- `http.py` — `/overlay`, `/overlay/debug`, `/overlay/demo`, `/overlay/golden`, `/config`, `/ws/overlay`, `/api/overlay/*`, `/api/config`
- Live HUD prázdný když iRacing není (link drop / quit). `?demo=1` to nerespektuje.

Prohlížeč: `web/overlay/` (V3 `display.js`, V4 `display-v4.js`). Témata: [web](web.md).

## Modely (`models.py`)

- `TelemetrySnapshot` — raw extraction (žádná interpretace)
- `RaceState` + `OpponentInfo` — hero, ahead/behind, session_finished, overlay_mode
- `BioState`, `SystemState` — HR a sysinfo karty

Wire: `protocol.py` (`CandidateEvent` z emitteru; manager vlastní duration/cooldown). V4: `events/envelope.py`.

## Tape a replay

JSONL v `recordings/` když `[overlay] session_tape`. Replay: `irswitchd --replay`. Časy: `t_stream` VOD, `t_session`/`t_green` iRacing, `t_mono` delay. Debug tape řádky commentary jen při log level DEBUG.

## Config

`[overlay]`, `[sampling]`, `[battle]`, `[events]`, `[event_engine]`, `[commentary]` — [CONFIG.md](../../../CONFIG.md), `overlay/settings.py`, `overlay/schema.py`.

Spec V4 layout (ne runtime pravda, pokud kód nesedí): `docs/overlay_v4_layout_sizing_motion_spec.md`.

## Testy

`tests/test_overlay_*.py`, `tests/test_golden_v4_*.py`, `tests/test_v4_*.py`, replay fixtures.

## In-flight

#179 mění `runtime.py`: registruje `EventFanout` + `RaceObserver` tick + SpeechScheduler. Po merge přepsat diagram výše. Do té doby **ne** přidávej druhý observer do runtime na master. Viz [pr-179](../inflight/pr-179-observers-decoupling.md).
