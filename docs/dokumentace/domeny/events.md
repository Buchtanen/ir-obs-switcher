# Event Engine (`src/irswitch/events/`)

**Účel:** z `RaceState` (+ volitelně `BioState`) vyrobit kandidáty, arbitrací vybrat aktivní příběhy pro HUD (a na master i pro commentary).

**Nepatří sem:** čtení iRSDK, přepínání OBS, výběr TTS věty (to je director).

## Pipeline na master

```text
RaceState
    → EventEngine.tick          # všichni emittery, fail-soft per emitter
    → filter_post_race          # session_finished ztlumí pole
    → EventManager / V2.submit  # cooldown, duration, channels, pit guard
    → RaceEvent + EventEnvelope[]
    → OverlayBus + CommentaryDirector.observe
```

Pořadí emitterů v `engine.py` je **deterministické**. `register()` přidává T2/T4 podle feature flagů (`practice`, `quali_projection`, `pit_story`, `hr_pressure`). `overtake_classifier` nahrazuje `PositionEmitter`. `pit_story` vypíná prostý `PitEmitter`.

## Emittery (master)

| Oblast | Soubory | Typický výstup |
| --- | --- | --- |
| Battle | `battle.py`, `rival_threat.py`, `battle_intensity.py` | HUNTING / HUNTED / intensity |
| Pozice | `position.py`, `overtake.py` | OVERTAKE |
| Lap | `lap.py`, `invalid_lap.py`, `clean_streak.py` | LAP_COMPLETE, … |
| Incident | `incident.py` | INCIDENT (delta incidentů) |
| Pit | `pit.py`, `pit_story.py` | PIT_ENTRY/EXIT, story |
| Session | `session.py`, `session_phase.py` | session / post-race filter |
| Link | `link_drop.py` | disconnect |
| T2 | `practice.py`, `quali.py`, `sector_split.py`, `target_locked.py` | sektory, PB, quali projection |
| T4 | `hr_pressure.py` | HR tlak |

Priority defaulty: `overlay.settings.EventPrioritySettings` / INI `[events]`.

## Manager

- **V1** `manager.py` — active list, cooldown, duration
- **V2** `manager_v2.py` (`event_engine.v2_payload`) — sequence stamp, V4 `EventEnvelope`, `PitCycleGuard`, `DecisionLog`, `adapters/` na envelope
- `envelope.py` — fáze ENTER/ACTIVE/UPDATE/COMPACT/SUSPEND/RESUME/EXIT/RESULT; módy PRACTICE/QUALIFYING/RACE/GENERIC
- `event_catalog.py` — mapování na `web/themes-v4/event_catalog.json`

`CandidateEvent.overlay=true` značí HUD. Commentary-only typy přijdou až s in-flight (graph `COMMENTARY_ONLY`).

## Testy

`tests/test_event_*.py`, `tests/test_*_emitter.py`, `tests/test_overtake_classifier.py`, `tests/test_pit_cycle_guard.py`.

## In-flight

#179: `events/fanout.py` — peer `EventConsumer`; overlay a commentary (a později observer derived) se odpojí od řetězu v runtime.

#181: úpravy `incident.py` (classify off_track/unknown), `session.py` / `session_phase.py` (tři booleany finish), `quali.py` / `battle.py` (pace hunt). Derived `SESSION_FLAG` **není** emitter v engine — je to FSM v `race/flags.py` na větvi #181.

Dokud #179 není v master, **nepřidávej** `fanout.py` na master paralelně.
