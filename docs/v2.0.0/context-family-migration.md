# #277 Context family migration (session / filler / weather / field / bio)

**Status:** Slice 1 — session/stream leftover inventory (`STREAM_START`, `SESSION_PREVIEW`, `ENTER_CAR`, `FINAL_LAP`; all `legacy`; no `FAMILY_ROUTE` flip).  
**Issue:** [#277](https://github.com/Buchtanen/ir-obs-switcher/issues/277)  
**Module:** `src/irswitch/contracts/context_family_map.py`  
**Tests:** `tests/test_context_family_map.py` (**10**)  
**Lookup:** [inflight § #277 slice 1](../dokumentace/inflight/README.md#277-context-family-map-slice-1-lookup) · [events branch delta](../dokumentace/domeny/events.md#context-family-migration-map-contractscontext_family_mappy)

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

**`CONTEXT_WIRE_IDS`:** **4** wires (session/stream leftovers only).

## AC locks (Slice 1)

- **Phase order** — `stream_start → preview → enter_car → final_lap`.
- **Explicit invalidation** — every leftover wire carries `invalidate_reasons`; `FINAL_LAP` also carries terminal `final_lap_observed`.
- **ENTER_CAR branches** — primary practice + qualifying/race documented.
- **No overlap** — inventory disjoint from timing + ops wire sets; owned-elsewhere table documents intros/wrap/finish.
- **Unknown not invented** — preview/final-lap notes forbid inventing next session type / checkered / hero finish.

Helpers: `Any()`, `ContractViolation()`, `LifecyclePhase()`, `Literal()`, `MigrationStatus()`, `ScopeKind()`, `can_create_event_opportunity()`, `context_family_rows()`, `context_session_phase_order_is_monotonic()`, `context_session_stories_have_explicit_invalidation()`, `dataclass()`, `enter_car_branch_beats_are_documented()`, `migration_status_by_wire_id()`, `owned_elsewhere_session_wires_are_documented()`, `packaged_schema_bytes()`, `row_for_wire_id()`, `rows_by_migration_status()`.

## Later #277 slices

Deferred: outlap/inlap/parade/garage filler; weather + field revalidation; HR emotion as optional style fact; long-silence eligibility/fatigue; EN-only curation + remove generic forced filler; shadow activation.

## Docs / config

- **Docs:** this page + `docs/v2.0.0/README.md` + `docs/dokumentace/{README,inflight/README,domeny/events}.md`.
- **Docs: CONFIG.md / API.md / COMMENTARY_ENGINE.md unchanged** (inventory-only).
