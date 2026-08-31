# Race interpretation (`src/irswitch/race/`)

**Účel:** z `TelemetrySnapshot` udělat `RaceState` (hero, sousedé, gapy, session fáze) a měřit sektory/lapy.

**Nepatří sem:** iRSDK I/O (to je `iracing/`), HUD render, TTS, OBS.

Na **master** je to tenká vrstva. Tlustý „story observer“ je jen v PR #179/#181.

## Master

### `RaceContextAnalyzer` (`context.py`)

- `analyze(snap) → RaceState`
- Ahead/behind: `opponents.relevant_ahead_behind` (prakticky **1+1** pro HUD battle)
- Gap + closing rate: `GapHistory` (`history.py`)
- `session_finished`: iRacing `SessionState` 5 Checkered / 6 CoolDown
- Disconnect → empty `RaceState`, reset histories

### `opponents.py`

Pozice class/overall, estimated gap ze dist/est time, pit/filter. #179 rozšiřuje o near-field 2+2 (`NearFieldCar`) — **není na master**.

### `timing/`

| Soubor | Role |
| --- | --- |
| `points.py` | Sector/lap body (default + z iRSDK pct) |
| `crossing.py` | CrossingDetector |
| `store.py` | TimingStore (časy) |
| `reference.py` | SegmentReferenceTracker (delta vs reference) |

Použití: `OverlayRuntime._observe_timing` → T2 emittery (`practice`, `quali`, `sector_split`) když jsou flagy.

## In-flight (#179) — nové soubory na větvi

| Soubor | Role |
| --- | --- |
| `observer.py` | `RaceObserver`: session/stream memory, weather/field fillers, 2+2 near field |
| `story.py` | `StreamMemory`, `StoryContext`, `HeroSnapshot` |
| `aftermath.py` | Incident aftermath FSM (stalled/rolling, `BACK_UNDER_WAY`) |
| `narrative.py` | `SESSION_WRAP` / `SESSION_PREVIEW` |

Derived envelope tečou **vedle** EventEngine (pak shared arbitration / fan-out). HUD battle zůstává 1+1.

## In-flight (#181, stacked na #179)

| Soubor | Role |
| --- | --- |
| `flags.py` | `SessionFlagFsm` — race yellow/green/checkered rising edge; start lights ignore; cooldown 12 s; commentary-only `SESSION_FLAG` |
| `timing_hunt.py` | Pace hunt z `CarIdxBestLapTime` (ne DriverInfo) |

Checkered **bit** ≠ `SessionState == 5`. N4 na větvi splitne `session_checkered` / `player_finished` / `mute_field`. Default `race_observer.flags` a `incident_classify` = **false**.

## Testy

Master: `tests/test_race_context.py`, `tests/test_race_timing.py`.  
PR větve: `tests/test_race_observer.py`, `tests/test_incident_aftermath.py`, `tests/test_session_stream_narrative.py`, flag/N5 testy.

## Pravidlo pro agenty

Nový race-story kód **necommituj na master** paralelně s #179. Buď stack na `feat/observers-decoupling-joint-test`, nebo dokumentuj konflikt.
