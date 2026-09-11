# #275 Timing family migration (timing + session intros/recaps)

**Status:** Slice 4 — timing inventory + practice→qualifying→race session intros/recaps (all `legacy`; no `FAMILY_ROUTE` flip).  
**Issue:** [#275](https://github.com/Buchtanen/ir-obs-switcher/issues/275)  
**Module:** `src/irswitch/contracts/timing_family_map.py`  
**Tests:** `tests/test_timing_family_map.py`  
**Lookup:** [inflight § #275](../dokumentace/inflight/README.md#275-timing-family-map-slice-4-lookup) · [events branch delta](../dokumentace/domeny/events.md#timing-family-migration-map-contractstiming_family_mappy)

## Guardrails

- Does **not** rewrite frozen `docs/v2.0.0/machine/*` hashes.
- Does **not** flip `FAMILY_ROUTE`.
- Does **not** cut over live `v2` speech.
- Integration-only; no master PR until cutover (#279).

## Slice 1–4 inventory

| Wire id | Legacy node | Beat | Role | Family | Policy / TTL | Tape | Scope | Stage | Lineage | Status |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| `LAP_COMPLETE` | `lap_complete` | `timing.lap.completed` | result | `timing.lap_result` | result / 30s | `race.timing.lap` | `lap_sf` | — | — | legacy |
| `SECTOR_SPLIT` | `sector_split` | `timing.sector.split` | update | `timing.sector` | transient / 6s | `race.timing.sector` | `sector` | — | — | legacy |
| `SECTOR_BEST` | `—` | `timing.sector.best` | result | `timing.sector` | result / 30s | `race.timing.sector` | `sector` | — | — | legacy |
| `PERSONAL_BEST` | `personal_best` | `timing.lap.personal_best` | result | `timing.lap_result` | result / 30s | `race.timing.lap` | `lap_pb` | — | — | legacy |
| `GAIN_FOUND` | `gain_found` | `timing.pace.gain` | update | `timing.delta` | transient / 6s | `race.timing.delta` | `pace_delta` | — | — | legacy |
| `TIME_LOST` | `time_lost` | `timing.pace.loss` | update | `timing.delta` | transient / 6s | `race.timing.delta` | `pace_delta` | — | — | legacy |
| `HOT_LAP` | `hot_lap` | `timing.lap.hot` | opening | `timing.attempt` | live_story / 10s | `race.timing.attempt` | `lap_attempt` | — | — | legacy |
| `PROJECTED_LAP` | `projected_lap` | `timing.lap.projected` | update | `timing.projection` | live_story / 10s | `race.timing.attempt` | `lap_projection` | — | — | legacy |
| `INVALID_LAP` | `invalid_lap` | `incident.invalid_lap` | result | `incident.invalid_lap` | result / 30s | `race.incident.invalid_lap` | `invalid_lap` | — | — | legacy |
| `SESSION_INTRO_PRACTICE` | `session_intro_practice` | `session.intro.practice` | opening | `session.intro` | context / 20s | `session.lifecycle` | `session_intro` | practice | active | legacy |
| `SESSION_INTRO_QUALIFY` | `session_intro_qualify` | `session.intro.qualifying` | opening | `session.intro` | context / 20s | `session.lifecycle` | `session_intro` | qualifying | active | legacy |
| `SESSION_INTRO_RACE` | `session_intro_race` | `session.intro.race` | opening | `session.intro` | context / 20s | `session.lifecycle` | `session_intro` | race | active | legacy |
| `QUALI_RECAP` | `quali_recap` | `session.qualifying_recap` | outcome | `session.recap` | result / 30s | `session.qualifying.recap` | `session_recap` | race | active | legacy |

Helpers: `timing_family_rows()`, `row_for_wire_id()`, `rows_by_migration_status()`, `migration_status_by_wire_id()`, `lap_complete_is_not_race_finish()`, `gain_and_loss_polarities_are_distinct()`, `invalid_lap_scope_is_explicit()`, `session_stage_order_is_monotonic()`, `inherited_facts_use_active_lineage_only()`.

## AC locks

- **Completed lap ≠ completed race** — `lap_complete_is_not_race_finish()`.
- **Gain ≠ loss** — `gain_and_loss_polarities_are_distinct()`.
- **Invalid-lap scope explicit** — modes `['PRACTICE', 'QUALIFYING']`.
- **Inherited facts use active lineage only** — session intros/recaps set `requires_active_lineage=True`; stage order `['practice', 'qualifying', 'race']`; non-recap wires do not silently inherit.

## Later #275 slices

Deferred: EN patterns / TTS slots; restart/rewind replay cases.

## Docs / config

- **Docs:** this page + `docs/v2.0.0/README.md` + `docs/dokumentace/{README,inflight/README,domeny/events}.md`.
- **Docs: `CONFIG.md` / `API.md` unchanged** (inventory-only).
