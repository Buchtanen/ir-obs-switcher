# P1 live readiness — Event Engine emitters → CommentaryDirector slots

Branch: `cursor/commentary-content-db-plan-8972`  
Source of truth for bindings: `src/irswitch/commentary/director.py` → `slot_bindings()`  
Graph: `src/irswitch/commentary/data/sequence_graph.json`  
Adapters: `src/irswitch/events/adapters/*.py` via `race_event_to_envelope()`  
Overlay hook: `src/irswitch/overlay/runtime.py` (`_observe_commentary`, `_observe_in_car`, `merge_speech_envelopes`)  
Speech bridge: `src/irswitch/commentary/bridge.py` (only `lap_complete` / `pit_entry` / `pit_exit`)

## How `slot_bindings()` reads metrics

| slot | sources (first non-empty wins) |
|------|--------------------------------|
| `position` | metrics `newPosition` \| `position` \| `classPosition`, else `subject.class_position` |
| `old_position` | metrics `oldPosition` |
| `target_name` | `target.display_name`, else metrics `targetName` |
| `lap` | metrics `lap` |
| `lap_time` | metrics `lapTime` |
| `delta` | metrics `delta` \| `deltaToBest` |
| `gap` | metrics `gap` |
| `bpm` | metrics `bpm` |
| `streak` | metrics `streak` |
| `value` | metrics `value` |
| `segment` | metrics `timingPointId` \| `segment` |
| `target_time` | metrics `targetTime` |
| `projected_time` | metrics `projectedTime` |
| `confidence` | metrics `confidence` (envelope top-level `confidence` is **not** used) |
| `emotion` | director HR resolve (not from envelope) |

Silence mode for this matrix: `choose_filled_line()` drops any line still containing `{slot}` leftovers → if every variant in the emotion bucket fails, director returns `None` (**slot_unbound**). Separate failure: no `EventEnvelope` reaches `observe()` (**no envelope**).

`live emitter?` legend:
- **yes** — always-on EventEngine emitter + adapter produces speakable envelope
- **partial** — feature-flagged, speech-bridge-only fallback, dual graph mapping, or adapter drops keys the slots need
- **no** — no path from live tick → V4 envelope that `nodes_for()` can match (or event type never emitted)

Feature flags (`src/irswitch/overlay/settings.py` defaults false; `config/config.example.ini` sets true): `event_engine.practice`, `quali_projection`, `overtake_classifier`, `pit_story`, `hr_pressure`.

---

## Matrix (every `sequence_graph.json` node id)

| node_id | event_types | slots needed | live emitter? (yes/partial/no) | metrics keys typically set | risk of silence (slot_unbound) |
|---------|-------------|--------------|--------------------------------|----------------------------|--------------------------------|
| `lap_complete` | `LAP_COMPLETE` | `lap`, `lap_time` | **yes** — `LapEmitter` (`events/lap.py`) → `adapters/lap.py`; speech-bridge backup in `commentary/bridge.py` | `lap`, `lapTime`, `bestLap`, `deltaToBest` | **low** — several EN variants have no slots |
| `personal_best` | `PERSONAL_BEST` | `lap`, `lap_time`, `delta` | **yes** — same `LapEmitter` / lap adapter (`delta` ← `deltaToBest`) | `lap`, `lapTime`, `bestLap`, `deltaToBest` | **low** — emitter sets lap + time + delta when PB fires |
| `gain_found` | `GAIN_FOUND` | `delta`, `segment` | **partial** — `PracticeEmitter` (`events/practice.py`) behind `event_engine.practice` → `adapters/timing.py` | `timingPointId` (→`segment`), `delta`, `segmentTime`, `lap` | **low** when emitter on (all lines need both; both are set); **n/a / silent** if flag off (no envelope) |
| `time_lost` | `TIME_LOST` | `delta`, `segment` | **partial** — same PracticeEmitter path | `timingPointId`, `delta`, `segmentTime`, `lap` | **low** when on; **n/a** if flag off |
| `target_locked` | `TARGET_LOCKED` | `target_time` | **partial** — `TargetLockedEmitter` (`events/target_locked.py`) + practice flag → timing adapter | `targetTime`, `lap` | **low** when on (every line needs `target_time`; set); **n/a** if flag off |
| `projected_lap` | `PROJECTED_LAP` | `projected_time`, `confidence` | **partial** — `QualiEmitter` (`events/quali.py`) + `quali_projection` → timing adapter | `projectedTime`, `confidence`, `bestLap`, `position` | **low** — all lines need `projected_time` (set); `confidence` optional on some lines |
| `hot_lap` | `HOT_LAP` | `lap` | **partial** — QualiEmitter + flag → timing adapter | `lap`, `hotLapIndex`, `position`, `projectedTime`, `sectorDelta` | **low** — `lap` set; some emotion lines are slot-free |
| `position_attack` | `POSITION_ATTACK` | `position` | **partial** — QualiEmitter + flag → timing adapter | `position`, `projectedTime`, `confidence`, `bestLap`, `targetPosition` | **low** — `position` required and set |
| `clean_streak` | `CLEAN_STREAK` | `streak` | **yes** — `CleanStreakEmitter` (`events/clean_streak.py`) → timing adapter | `streak`, `lap` | **low** — `streak` always set when emitted (≥3) |
| `hunting` | `HUNTING`, `APPROACH` | `gap`, `target_name`, `position` | **yes** — `BattleEmitter` → battle adapter; `targetName` from iRSDK DriverInfo when present | `gap`, `closingRate`, `targetCarIdx`, `targetPosition`, `position`, `targetName` | **low–medium** — name-heavy lines speak when DriverInfo present; gap/position lines cover missing names |
| `hunted` | `HUNTED` | `gap`, `target_name`, `position` | **yes** — BattleEmitter → battle adapter | same battle metrics | **low–medium** — same as hunting |
| `side_by_side` | `SIDE_BY_SIDE`, `BATTLE_FOR_POSITION` | `position`, `target_name` | **yes** — BattleEmitter | `gap`, `position`, `targetCarIdx`, `targetName`, … | **low–medium** |
| `overtake` | `OVERTAKE` | `position`, `target_name` | **partial** — classifier when flagged; adapter keeps `targetName` / target subject | `oldPosition`, `newPosition`, `delta`, `targetName`, … | **low** when name present; position-only lines otherwise |
| `position_gained` | `POSITION_GAINED` | `position`, `old_position` | **yes** — PositionEmitter / classifier non-OT gain → `adapters/position.py` | `direction`, `oldPosition`, `newPosition`, `delta` | **low** — both position slots map from metrics |
| `position_lost` | `POSITION_LOST`, `OVERTAKEN` | `position`, `old_position` | **partial** — `POSITION_LOST` yes via position_change loss; **`OVERTAKEN` never emitted** | `direction`, `oldPosition`, `newPosition`, `delta` | **low** for `POSITION_LOST`; `OVERTAKEN` path **n/a** |
| `rival_threat` | `RIVAL_THREAT` | `gap`, `target_name` | **yes** — `RivalThreatEmitter` → position adapter keeps gap + iRSDK/`P{n}` label | `gap`, `closingRate`, `targetCarIdx`, `rivalPosition`, `targetName` | **low** when emitter fires |
| `battle_won` | `BATTLE_WON` | `position` | **yes** — BattleEmitter peak exit → battle adapter | `position`, `oldPosition`, `newPosition` | **low** — many slot-free lines; `position` usually set |
| `incident` | `INCIDENT` | `value` | **yes** — `IncidentEmitter` → `adapters/exception_extra.py` | `value`, `total` | **low** — slot-free lines exist; `value` set on delta |
| `invalid_lap` | `INVALID_LAP` | `lap` | **yes** — `InvalidLapEmitter` → `adapters/exception_extra.py` | `lap`, `incidentDelta` | **low** — slot-free lines exist; `lap` usually set |
| `final_lap` | `FINAL_LAP` | `position` | **yes** — `SessionEmitter` (+ position/classPosition) → `adapters/session.py` | `lap`, `position`, `classPosition` | **low** — `position` set on emit |
| `finish` | `FINISH` | `position` | **yes** — `SessionEmitter` → session adapter | `position`, `classPosition` | **low** — all lines need `position` (set) |
| `pit_entry` | `PIT_ENTRY` | `position` | **partial** — with `pit_story`: `PitStoryEmitter` → `adapters/pit.py` (`state=entry`); without: legacy `PitEmitter` + speech bridge (`onPitRoad` only) | pit story: `position`, `onPitRoad`, `lapDistPct`, `correlationId`, …; legacy bridge: `onPitRoad` | **low** — neutral lines are all slot-free |
| `back_on_track` | `PIT_EXIT` | `position` | **partial** — pit_story exit → pit adapter; or speech bridge from legacy `pit_exit` | `position`, `onPitRoad`, `entryPosition`/`exitPosition`, … | **low** — neutral lines slot-free; `position` often set on exit |
| `in_car` | `ENTER_CAR` | *(none)* | **yes** — not EventEngine; `InCarDetector` (`commentary/in_car.py`) via `OverlayRuntime._observe_in_car` | `position`, `sessionType` (unused by slots) | **none** — empty slots; all variants slot-free. Unrestricted fallback (warmup / unknown mode). |
| `in_car_practice` / `in_car_qualify` / `in_car_race` | `ENTER_CAR` | *(none)* | **yes** — same detector; N2 mode ladder prefers these over generic `in_car` | same | **none** — N11 wave A; `hr_states: unknown` only |
| `stream_start` | `STREAM_START` | *(none)* | **yes** — commentary-only; OBS rising edge → `notify_obs_stream_started` (`commentary.stream_start`) | none | **none** — slot-free; node `tts.max_seconds` ≥ 15 |
| `pit_outcome` | `PIT_OUTCOME`, `PIT_EXIT` | `position`, `old_position` | **partial** — `PIT_OUTCOME` only via pit_story outcome; also competes with `back_on_track` for `PIT_EXIT` (`nodes_for` priority sort). Adapter sets metrics `position` / `entryPosition` / `exitPosition` but **not** `oldPosition` | `position`, `entryPosition`, `exitPosition`, `positionDelta`, … | **medium** — `old_position` never binds (`entryPosition` ≠ `oldPosition`); slot-free / position-only lines mitigate; focused bucket needs `position` |
| `hr_pressure` | `HR_PRESSURE_RISING` | `bpm` | **partial** — `HrPressureEmitter` (`events/hr_pressure.py`) + `hr_pressure` flag → `adapters/bio.py`; requires live BLE bio | `bpm`, `baselineBpm`, `deltaBpm`, `hrState` | **low** when bio connected (`bpm` set; some lines omit it). Node only allows `pushing`/`high` HR states — calm/unknown → no speak (emotion gate, not slot_unbound) |

---

## Overlay commentary hooks (runtime)

| hook | file | role |
|------|------|------|
| Build/reset director | `overlay/runtime.py` `_build_commentary` / `_reset_commentary` | loads `sequence_graph.json`, applies `CommentarySettings` |
| After manager_v2 accept | `_emit_from_race` → `_observe_commentary(merge_speech_envelopes(...))` | envelopes from adapters + bridge |
| Manager_v2 tick EXIT | `_observe_commentary(envelopes)` | EXIT phases only speak if node lists `EXIT` (`back_on_track`, `pit_outcome`) |
| In-car | `_observe_in_car` → `InCarDetector.tick` | `ENTER_CAR` once per seated stint |
| Legacy manager path | speech_envelope_from_race_event only | subset map; weaker than v2 |

Director speak phases: `ENTER` / `RESULT` / `EXIT` only (`_SPEAK_PHASES`). `UPDATE`/`ACTIVE` are ignored for TTS.

---

## Highest remaining P1 gaps (product)

1. **`pit_outcome.old_position`**: `entryPosition` not aliased to `oldPosition`.
2. **`OVERTAKEN`**: never emitted. **`ATTACK_RANGE`**: graph node `attack_range` (P5). Mid-pit: `pit_stopped` for `PIT_STOPPED` ENTER; lane/released still silent. Observer fillers now authored in-graph: `incident_aftermath` / `back_under_way`, `session_wrap` / `session_preview` / `session_checkered` (gated by `session_briefs`), `field_fact` / `weather_change` (silence fill; suppressed once checkered or after_session). RaceObserver template formatter remains fallback when no node matches.
3. Driver names: live path uses iRSDK `DriverInfo` (`UserName` last token / `AbbrevName`) on `OpponentInfo.display_name` → `targetName`. Missing DriverInfo still falls back to `P{n}` on rival_threat only.

---

## Cite map (emitters → adapters)

| family | emitter module | adapter |
|--------|----------------|---------|
| lap / PB | `events/lap.py` | `adapters/lap.py` |
| practice / quali / streak / target | `practice.py`, `quali.py`, `target_locked.py`, `clean_streak.py` | `adapters/timing.py` |
| battle | `events/battle.py` | `adapters/battle.py` |
| position / OT / rival | `position.py`, `overtake.py`, `rival_threat.py` | `adapters/position.py` |
| pit story | `events/pit_story.py` | `adapters/pit.py` |
| legacy pit | `events/pit.py` | speech bridge only (`bridge.py`) |
| bio | `events/hr_pressure.py` | `adapters/bio.py` |
| invalid lap / incident | `invalid_lap.py`, `incident.py` | `adapters/exception_extra.py` |
| session final/finish | `events/session.py` | `adapters/session.py` |
| driver names | iRSDK `DriverInfo` → `TelemetrySnapshot.car_idx_driver_name` → `OpponentInfo.display_name` | battle / position / rival adapters (`targetName`) |
| in-car | `commentary/in_car.py` | direct envelope |
