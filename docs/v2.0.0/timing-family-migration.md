# #275 Timing family migration (lap / SF / sector / PB / pace / quali / invalid)

**Status:** Slice 3 — lap/SF + sector + PB/pace + hot/projected/invalid lap inventory (all `legacy`; no `FAMILY_ROUTE` flip).  
**Issue:** [#275](https://github.com/Buchtanen/ir-obs-switcher/issues/275)  
**Module:** `src/irswitch/contracts/timing_family_map.py`  
**Tests:** `tests/test_timing_family_map.py`  
**Lookup:** [inflight § #275](../dokumentace/inflight/README.md#275-timing-family-map-slice-3-lookup) · [events branch delta](../dokumentace/domeny/events.md#timing-family-migration-map-contractstiming_family_mappy)

## Guardrails

- Does **not** rewrite frozen `docs/v2.0.0/machine/*` hashes.
- Does **not** flip `FAMILY_ROUTE`.
- Does **not** cut over live `v2` speech.
- Integration-only; no master PR until cutover (#279).

## Slice 1–3 inventory

| Wire id | Legacy node | Beat | Role | Predicate | Family | Policy / TTL | Tape | Scope | Status |
| --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| `LAP_COMPLETE` | `lap_complete` | `timing.lap.completed` | result | `timing.lap_completed` | `timing.lap_result` | result / 30s | `race.timing.lap` | `lap_sf` | legacy |
| `SECTOR_SPLIT` | `sector_split` | `timing.sector.split` | update | `timing.sector_completed` | `timing.sector` | transient / 6s | `race.timing.sector` | `sector` | legacy |
| `SECTOR_BEST` | `—` | `timing.sector.best` | result | `timing.sector_best` | `timing.sector` | result / 30s | `race.timing.sector` | `sector` | legacy |
| `PERSONAL_BEST` | `personal_best` | `timing.lap.personal_best` | result | `timing.personal_best` | `timing.lap_result` | result / 30s | `race.timing.lap` | `lap_pb` | legacy |
| `GAIN_FOUND` | `gain_found` | `timing.pace.gain` | update | `timing.delta_improved` | `timing.delta` | transient / 6s | `race.timing.delta` | `pace_delta` | legacy |
| `TIME_LOST` | `time_lost` | `timing.pace.loss` | update | `timing.delta_worsened` | `timing.delta` | transient / 6s | `race.timing.delta` | `pace_delta` | legacy |
| `HOT_LAP` | `hot_lap` | `timing.lap.hot` | opening | `timing.active_attempt` | `timing.attempt` | live_story / 10s | `race.timing.attempt` | `lap_attempt` | legacy |
| `PROJECTED_LAP` | `projected_lap` | `timing.lap.projected` | update | `timing.lap_projection` | `timing.projection` | live_story / 10s | `race.timing.attempt` | `lap_projection` | legacy |
| `INVALID_LAP` | `invalid_lap` | `incident.invalid_lap` | result | `incident.lap_invalid` | `incident.invalid_lap` | result / 30s | `race.incident.invalid_lap` | `invalid_lap` | legacy |

Helpers: `timing_family_rows()`, `row_for_wire_id()`, `rows_by_migration_status()`, `migration_status_by_wire_id()`, `lap_complete_is_not_race_finish()`, `gain_and_loss_polarities_are_distinct()`, `invalid_lap_scope_is_explicit()`.

## AC locks

- **Completed lap ≠ completed race:** `LAP_COMPLETE` stays on `lap_sf` / `timing.lap.completed` / `timing.lap_result` — never `session.finish` / wire `FINISH`.
- **Gain ≠ loss:** `GAIN_FOUND` / `TIME_LOST` opposite polarities under `pace_delta`.
- **Invalid-lap scope explicit:** `INVALID_LAP` uses `scope_kind=invalid_lap`, family `incident.invalid_lap`, session modes `['PRACTICE', 'QUALIFYING']` only (not RACE).
- Helpers: `lap_complete_is_not_race_finish()`, `gain_and_loss_polarities_are_distinct()`, `invalid_lap_scope_is_explicit()`.

## Emitters / adapters

| Wire | Emitter | Adapter |
| --- | --- | --- |
| `LAP_COMPLETE` | `irswitch.events.direct_edges:DirectEdgeBank` | `irswitch.events.adapters.lap:lap_race_event_to_envelope` |
| `SECTOR_SPLIT` | `irswitch.events.direct_edges:DirectEdgeBank` | `irswitch.events.adapters.timing:timing_race_event_to_envelope` |
| `SECTOR_BEST` | `irswitch.events.direct_edges:DirectEdgeBank` | `irswitch.events.adapters.timing:timing_race_event_to_envelope` |
| `PERSONAL_BEST` | `irswitch.events.lap:LapEmitter` | `irswitch.events.adapters.lap:lap_race_event_to_envelope` |
| `GAIN_FOUND` | `irswitch.events.practice:PracticeEmitter` | `irswitch.events.adapters.timing:timing_race_event_to_envelope` |
| `TIME_LOST` | `irswitch.events.practice:PracticeEmitter` | `irswitch.events.adapters.timing:timing_race_event_to_envelope` |
| `HOT_LAP` | `irswitch.events.quali:QualiEmitter` | `irswitch.events.adapters.timing:timing_race_event_to_envelope` |
| `PROJECTED_LAP` | `irswitch.events.quali:QualiEmitter` | `irswitch.events.adapters.timing:timing_race_event_to_envelope` |
| `INVALID_LAP` | `irswitch.events.invalid_lap:InvalidLapEmitter` | `irswitch.events.adapters.exception_extra:invalid_lap_race_event_to_envelope` |

## Later #275 slices (not in this map yet)

Deferred: practice→quali→race recaps (`QUALI_RECAP` / session intros), EN patterns / TTS slots, restart/rewind replay cases.

## Docs / config

- **Docs:** this page + `docs/v2.0.0/README.md` + `docs/dokumentace/{README,inflight/README,domeny/events}.md`.
- **Docs: `CONFIG.md` / `API.md` unchanged** (inventory-only; no public contract).
