# #275 Timing family migration (timing + session intros/recaps)

**Status:** Slice 6 — restart/rewind replay cases curated for all inventory wires (all `legacy`; no `FAMILY_ROUTE` flip).  
**Issue:** [#275](https://github.com/Buchtanen/ir-obs-switcher/issues/275)  
**Module:** `src/irswitch/contracts/timing_family_map.py` + `timing_family_replay_cases.py`  
**Tests:** `tests/test_timing_family_map.py` + `tests/test_timing_family_replay_cases.py`  
**Lookup:** [inflight § #275](../dokumentace/inflight/README.md#275-timing-family-map-slice-6-lookup) · [events branch delta](../dokumentace/domeny/events.md#timing-family-migration-map-contractstiming_family_mappy)

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



## EN patterns / TTS slots (Slice 5)

Curated without rewriting frozen `machine/realization-pattern-cards.json` hashes:

| Wire | Beat pattern ids (4× tight) | Claim-surface polarity | Forbidden tokens | TTS slots |
| --- | --- | --- | --- | --- |
| `LAP_COMPLETE` | `timing.lap.completed:tight:1`, `timing.lap.completed:tight:2`, `timing.lap.completed:tight:3`, `timing.lap.completed:tight:4` | completes lap {lapNumber}; crosses the line on lap {lapNumber}… | `wins the race`, `checkered`, `race finish`, `takes the win` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `SECTOR_SPLIT` | `timing.sector.split:tight:1`, `timing.sector.split:tight:2`, `timing.sector.split:tight:3`, `timing.sector.split:tight:4` | splits sector {sectorId}; ticks sector {sectorId}… | `sector best`, `personal best`, `invalid lap` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `SECTOR_BEST` | `timing.sector.best:tight:1`, `timing.sector.best:tight:2`, `timing.sector.best:tight:3`, `timing.sector.best:tight:4` | sets a sector {sectorId} best; improves sector {sectorId}… | `loses time`, `invalid lap`, `race finish` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `PERSONAL_BEST` | `timing.lap.personal_best:tight:1`, `timing.lap.personal_best:tight:2`, `timing.lap.personal_best:tight:3`, `timing.lap.personal_best:tight:4` | sets a personal best; improves the personal best to {lapTime}… | `sector only`, `invalid lap`, `race win` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `GAIN_FOUND` | `timing.pace.gain:tight:1`, `timing.pace.gain:tight:2`, `timing.pace.gain:tight:3`, `timing.pace.gain:tight:4` | finds {delta} against the reference; gains time vs the reference… | `loses time`, `drops time`, `falls back`, `worse than` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `TIME_LOST` | `timing.pace.loss:tight:1`, `timing.pace.loss:tight:2`, `timing.pace.loss:tight:3`, `timing.pace.loss:tight:4` | loses {delta} against the reference; drops time vs the reference… | `finds time`, `gains time`, `improves by`, `picks up` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `HOT_LAP` | `timing.lap.hot:tight:1`, `timing.lap.hot:tight:2`, `timing.lap.hot:tight:3`, `timing.lap.hot:tight:4` | is on a hot lap; starts flying lap {attemptId}… | `completed result`, `race finish`, `invalid lap claimed as valid` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `PROJECTED_LAP` | `timing.lap.projected:tight:1`, `timing.lap.projected:tight:2`, `timing.lap.projected:tight:3`, `timing.lap.projected:tight:4` | projects {projectedTime}; is on for {projectedTime}… | `has completed`, `personal best confirmed`, `checkered` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `INVALID_LAP` | `incident.invalid_lap:tight:1`, `incident.invalid_lap:tight:2`, `incident.invalid_lap:tight:3`, `incident.invalid_lap:tight:4` | invalidates lap {lapNumber}; loses lap {lapNumber} to a track limit… | `race finish`, `wins the race`, `personal best stands` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `SESSION_INTRO_PRACTICE` | `session.intro.practice:tight:1`, `session.intro.practice:tight:2`, `session.intro.practice:tight:3`, `session.intro.practice:tight:4` | opens practice; is into practice… | `qualifying already decided`, `race underway`, `checkered` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `SESSION_INTRO_QUALIFY` | `session.intro.qualifying:tight:1`, `session.intro.qualifying:tight:2`, `session.intro.qualifying:tight:3`, `session.intro.qualifying:tight:4` | opens qualifying; is into qualifying… | `practice only`, `race underway`, `checkered` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `SESSION_INTRO_RACE` | `session.intro.race:tight:1`, `session.intro.race:tight:2`, `session.intro.race:tight:3`, `session.intro.race:tight:4` | opens the race; is into the race… | `practice only`, `qualifying still open as live`, `unofficial win` | `{subjectSurface}`, `{requiredClaimSurface}` |
| `QUALI_RECAP` | `session.qualifying_recap:tight:1`, `session.qualifying_recap:tight:2`, `session.qualifying_recap:tight:3`, `session.qualifying_recap:tight:4` | recaps qualifying in P{position}; brings the quali result of P{position}… | `live sector split`, `projected as final`, `race already won` | `{subjectSurface}`, `{requiredClaimSurface}` |

Helpers: `en_patterns_and_tts_slots_are_curated()`, `restart_rewind_replay_cases_are_complete()`.

## Restart / rewind replay cases (Slice 6)

Closed inventory in `timing_family_replay_cases.py` (no live speech / no `FAMILY_ROUTE` flip):

| Case id | Scenario | Wires | Speakable after | Inherit on active lineage |
| --- | --- | --- | --- | --- |
| `same_ref_restart:lap_sf` | `same_ref_restart` | `LAP_COMPLETE` | `none` | no |
| `same_ref_restart:sector` | `same_ref_restart` | `SECTOR_SPLIT`, `SECTOR_BEST` | `none` | no |
| `same_ref_restart:pace_delta` | `same_ref_restart` | `GAIN_FOUND`, `TIME_LOST` | `none` | no |
| `same_ref_restart:attempt_projection` | `same_ref_restart` | `HOT_LAP`, `PROJECTED_LAP` | `none` | no |
| `same_ref_restart:invalid_lap` | `same_ref_restart` | `INVALID_LAP` | `none` | no |
| `same_ref_restart:session_intro` | `same_ref_restart` | `SESSION_INTRO_PRACTICE`, `SESSION_INTRO_QUALIFY`, `SESSION_INTRO_RACE` | `active_only` | no |
| `rewind_superseded:race_timing` | `rewind_superseded` | `LAP_COMPLETE`, `SECTOR_SPLIT`, `SECTOR_BEST`, `GAIN_FOUND`, `TIME_LOST` | `none` | no |
| `rewind_superseded:quali_result_historical` | `rewind_superseded` | `QUALI_RECAP` | `historical_recap` | no |
| `post_rewind_forward:personal_best_inherits` | `post_rewind_forward` | `PERSONAL_BEST` | `active_only` | yes |
| `post_rewind_forward:quali_recap_active_only` | `post_rewind_forward` | `QUALI_RECAP` | `active_only` | yes |
| `post_rewind_forward:session_intro_race` | `post_rewind_forward` | `SESSION_INTRO_RACE` | `active_only` | no |
| `post_rewind_forward:attempt_on_new_quali` | `post_rewind_forward` | `HOT_LAP`, `PROJECTED_LAP`, `INVALID_LAP` | `active_only` | no |

Helper: `restart_rewind_replay_cases_are_complete()`.

**Remaining legacy disposition:** all 13 timing wires remain `migration_status=legacy` until a dedicated activation slice (shadow + fail-soft + COMMENTARY_ENGINE/CONFIG/API) lands.

## Docs / config

- **Docs:** this page + `docs/v2.0.0/README.md` + `docs/dokumentace/{README,inflight/README,domeny/events}.md`.
- **Docs: `CONFIG.md` / `API.md` unchanged** (inventory-only).
