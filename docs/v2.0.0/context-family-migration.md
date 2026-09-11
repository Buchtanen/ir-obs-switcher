# #277 Context family migration (session / filler / weather / field / bio)

**Status:** Slice 4 — session leftovers + filler + weather/field + bio style (`STREAM_START`, `SESSION_PREVIEW`, `ENTER_CAR`, `FINAL_LAP`, `PARADE_PAD`, `WEATHER_BRIEF`, `WEATHER_CHANGE`, `FIELD_FACT`, `SOF_BRIEF`, `HR_PRESSURE_RISING`; all `legacy`; no `FAMILY_ROUTE` flip).
**Issue:** [#277](https://github.com/Buchtanen/ir-obs-switcher/issues/277)  
**Module:** `src/irswitch/contracts/context_family_map.py`  
**Tests:** `tests/test_context_family_map.py` (**13**)
**Lookup:** [inflight § #277 slice 4](../dokumentace/inflight/README.md#277-context-family-map-slice-4-lookup) · [events branch delta](../dokumentace/domeny/events.md#context-family-migration-map-contractscontext_family_mappy)

## Guardrails

- Does **not** rewrite frozen `docs/v2.0.0/machine/*` hashes.
- Does **not** flip `FAMILY_ROUTE` (session leftovers stay `legacy`; `bio` remains `legacy`).
- Does **not** cut over live `v2` speech.
- Does **not** duplicate wires already inventoried by timing (`SESSION_INTRO_*`, `QUALI_RECAP`) or ops (`SESSION_WRAP`, `SESSION_FLAG`, `SESSION_CHECKERED`, `FINISH`).
- Integration-only; no master PR until cutover (#279).

## Slice 1 inventory — session/stream leftovers

| Wire id | Legacy node | Beat | Role | Family | Policy / TTL | Tape | Scope | Phase | Status |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| `STREAM_START` | `stream_start` | `stream.started` | opening | `stream.lifecycle` | critical / 45s | `stream.lifecycle` | `stream_lifecycle` | stream_start | legacy |
| `SESSION_PREVIEW` | `session_preview` | `session.preview.next` | bridge | `session.preview` | context / 20s | `session.lifecycle` | `session_preview` | preview | legacy |
| `ENTER_CAR` | `enter_car` | `session.enter_car.practice` | vehicle | `session.vehicle` | context / 20s | `session.vehicle` | `enter_car` | enter_car | legacy |
| `FINAL_LAP` | `final_lap` | `session.final_lap` | escalation | `session.final_lap` | critical / 45s | `race.session.final_lap` | `final_lap` | final_lap | legacy |

**ENTER_CAR branch beats:** primary `session.enter_car.practice`; registry also binds `session.enter_car.qualifying` and `session.enter_car.race`.

**Owned elsewhere (documented, not duplicated):**

| Wire id | Owner map |
| --- | --- |
| `SESSION_INTRO_PRACTICE` / `QUALIFY` / `RACE` | `timing_family_map` |
| `QUALI_RECAP` | `timing_family_map` |
| `SESSION_WRAP` / `SESSION_FLAG` / `SESSION_CHECKERED` | `ops_family_map` |
| `FINISH` | `ops_family_map` / `race_outcome_family_map` |

**Emitters / adapters (Slice 1):**

| Wire | Emitter | Adapter |
| --- | --- | --- |
| `STREAM_START` | `irswitch.events.lifecycle_edges:LifecycleTriggerBank` | LifecycleTriggerBank direct |
| `SESSION_PREVIEW` | `irswitch.race.narrative:StreamNarrativeFsm` | FSM direct |
| `ENTER_CAR` | `irswitch.commentary.opener:OpenerMutex` | `session_race_event_to_envelope` |
| `FINAL_LAP` | `irswitch.events.session:SessionEmitter` | `session_race_event_to_envelope` |

**`CONTEXT_WIRE_IDS`:** **10** wires (session **4** + filler **1** + weather/field **4** + bio style **1**).

## AC locks (Slice 1)

- **Phase order** — `stream_start → preview → enter_car → final_lap`.
- **Explicit invalidation** — every leftover wire carries `invalidate_reasons`; `FINAL_LAP` also carries terminal `final_lap_observed`.
- **ENTER_CAR branches** — primary practice + qualifying/race documented.
- **No overlap** — inventory disjoint from timing + ops wire sets; owned-elsewhere table documents intros/wrap/finish.
- **Unknown not invented** — preview/final-lap notes forbid inventing next session type / checkered / hero finish.

Helpers (Slice 1): `Any()`, `ContractViolation()`, `LifecyclePhase()`, `Literal()`, `MigrationStatus()`, `ScopeKind()`, `can_create_event_opportunity()`, `context_family_rows()`, `context_session_phase_order_is_monotonic()`, `context_session_stories_have_explicit_invalidation()`, `dataclass()`, `enter_car_branch_beats_are_documented()`, `migration_status_by_wire_id()`, `owned_elsewhere_session_wires_are_documented()`, `packaged_schema_bytes()`, `row_for_wire_id()`, `rows_by_migration_status()`.


## Slice 2 inventory — outlap / inlap / parade / garage filler

| Wire id | Legacy node | Beat | Role | Family | Policy / TTL | Tape | Scope | Phase | Status |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| `PARADE_PAD` | `parade_pad` | `filler.parade_lap` | `single` | `filler.track_state` | `filler` / 12s | `filler.track_state` | `filler_parade` | — | legacy |

**Emitter / adapter:** `irswitch.race.grid_story:GridStoryFsm` (same adapter path).

**Invalidate reasons:** `stream_ended`, `session_reset`, `green_or_racing`, `parade_cap`.

**Beat-only fillers (no freeze wire):** `filler.out_lap`, `filler.in_lap`, `filler.garage`, `filler.lobby`, `filler.quiet_track` — selected by silence clock or fail soft to silence / no-candidate / source-guard; **never invent** wires for them.

**All filler beats:** `filler.out_lap`, `filler.in_lap`, `filler.parade_lap`, `filler.garage`, `filler.lobby`, `filler.quiet_track`.

**AC locks (Slice 2):**
- Parade pad is the **only** filler freeze wire (`CONTEXT_FILLER_WIRE_IDS == ("PARADE_PAD",)`).
- Filler inventory may resolve to **silence** (`filler_may_resolve_to_silence()`); notes forbid forcing generic filler speech.
- Beat-only set stays outside `CONTEXT_WIRE_IDS`.

Helpers (add): `filler_beats_are_documented()`, `filler_may_resolve_to_silence()`.


## Slice 3 inventory — weather + field (with revalidation)

| Wire id | Legacy node | Beat | Role | Family | Policy / TTL | Tape | Scope | Phase | Status |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| `WEATHER_BRIEF` | `weather_brief` | `session.weather_brief` | `context` | `session.weather` | `context` / 20s | `session.context.weather` | `weather_brief` | — | legacy |
| `WEATHER_CHANGE` | `weather_change` | `session.weather_change` | `update` | `session.weather` | `context` / 20s | `session.context.weather` | `weather_change` | — | legacy |
| `FIELD_FACT` | `field_fact` | `session.field_fact` | `context` | `session.context` | `context` / 20s | `session.context.field` | `field_fact` | — | legacy |
| `SOF_BRIEF` | `sof_brief` | `session.sof_brief` | `context` | `session.context` | `context` / 20s | `session.context.field` | `sof_brief` | — | legacy |

**Emitters / adapters (Slice 3):**

| Wire | Emitter | Adapter |
| --- | --- | --- |
| `WEATHER_BRIEF` | `irswitch.commentary.session_briefs:SessionBriefsDetector` | same |
| `WEATHER_CHANGE` | `irswitch.race.observer:RaceObserver` | same |
| `FIELD_FACT` | `irswitch.race.observer:RaceObserver` | same |
| `SOF_BRIEF` | `irswitch.commentary.session_briefs:SessionBriefsDetector` | same |

**AC locks (Slice 3):**
- Weather/field currency is explicit **current** vs **historical** (`weather_and_field_currency_is_explicit()`).
- Forecast weather is **not speakable** (notes + silence-clock source guard).
- Field/SoF must not invent race outcomes or extrapolate beyond the selected fact.
- Revalidation invalidate reasons include stale/superseded/roster_reset/forecast_rejected.

Helpers (add): `weather_and_field_wires_are_documented()`, `weather_and_field_currency_is_explicit()`.


## Slice 4 inventory — HR emotion as optional style fact

| Wire id | Legacy node | Beat | Role | Family | Policy / TTL | Tape | Scope | Phase | Status |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| `HR_PRESSURE_RISING` | `hr_pressure_rising` | `bio.pressure` | `context` | `bio.context` | `context` / 20s | `bio.pressure` | `bio_style` | — | legacy |

**Emitter / adapter:** `irswitch.events.hr_pressure:HrPressureEmitter` / `irswitch.events.adapters.bio:bio_race_event_to_envelope`.

**Alias (not speakable inventory):** `HEART_RATE` → `compatibility_alias/not_speakable` (owned-elsewhere; outside `CONTEXT_WIRE_IDS`).

**AC locks (Slice 4):**
- HR/bio is **optional style only** (`bio_style_wires_are_documented()`).
- Must **not** invent sport truth, medical claims, emotion causes, or performance claims (`bio_cannot_invent_sport_truth()`).
- Stale/missing sensor → suppress style (`style_suppressed` / `sensor_stale`); do not invent pressure.
- No `FAMILY_ROUTE["bio"]` flip (stays `legacy` observational owner elsewhere).

Helpers (add): `bio_style_wires_are_documented()`, `bio_cannot_invent_sport_truth()`.

## Later #277 slices

Deferred: long-silence eligibility/fatigue; EN-only curation + remove generic forced filler; shadow activation.

## Docs / config

- **Docs:** this page + `docs/v2.0.0/README.md` + `docs/dokumentace/{README,inflight/README,domeny/events}.md`.
- **Docs: CONFIG.md / API.md / COMMENTARY_ENGINE.md unchanged** (inventory-only).
