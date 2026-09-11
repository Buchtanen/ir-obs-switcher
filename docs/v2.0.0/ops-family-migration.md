# #276 Ops family migration (pit / incident / flag / recovery)

**Status:** Slice 4 — pit + incident/aftermath/recovery + `SESSION_FLAG` + checkered / hero finish / session wrap inventory (Slices 1–4; all `legacy`; no `FAMILY_ROUTE` flip).  
**Issue:** [#276](https://github.com/Buchtanen/ir-obs-switcher/issues/276)  
**Module:** `src/irswitch/contracts/ops_family_map.py`  
**Tests:** `tests/test_ops_family_map.py` (**15**)  
**Lookup:** [inflight § #276 slice 1](../dokumentace/inflight/README.md#276-ops-family-map-slice-1-lookup) · [inflight § #276 slice 2](../dokumentace/inflight/README.md#276-ops-family-map-slice-2-lookup) · [inflight § #276 slice 3](../dokumentace/inflight/README.md#276-ops-family-map-slice-3-lookup) · [inflight § #276 slice 4](../dokumentace/inflight/README.md#276-ops-family-map-slice-4-lookup) · [events branch delta](../dokumentace/domeny/events.md#ops-family-migration-map-contractsops_family_mappy)

## Guardrails

- Does **not** rewrite frozen `docs/v2.0.0/machine/*` hashes.
- Does **not** flip `FAMILY_ROUTE` (pit/incident/flag remain `legacy`).
- Does **not** cut over live `v2` speech.
- Integration-only; no master PR until cutover (#279).

## Slice 1 inventory — pit cycle

| Wire id | Legacy node | Beat | Role | Family | Policy / TTL | Tape | Scope | Phase | Status |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| `PIT_ENTRY` | `pit_entry` | `pit.entry` | opening | `pit.lifecycle` | live_story / 10s | `race.pit.cycle` | `pit_cycle` | entry | legacy |
| `PIT_LANE` | — | `pit.lane` | update | `pit.lifecycle` | live_story / 10s | `race.pit.cycle` | `pit_cycle` | lane | legacy |
| `PIT_STOPPED` | `pit_stopped` | `pit.stopped` | update | `pit.lifecycle` | live_story / 10s | `race.pit.cycle` | `pit_cycle` | stopped | legacy |
| `PIT_RELEASED` | — | `pit.released` | update | `pit.lifecycle` | live_story / 10s | `race.pit.cycle` | `pit_cycle` | released | legacy |
| `PIT_EXIT` | — | `pit.exit` | closure | `pit.lifecycle` | result / 30s | `race.pit.cycle` | `pit_cycle` | exit | legacy |
| `PIT_OUTCOME` | `pit_outcome` | `pit.outcome` | outcome | `pit.outcome` | result / 30s | `race.pit.outcome` | `pit_outcome` | outcome | legacy |

## Slice 2 inventory — incident / aftermath / recovery

| Wire id | Legacy node | Beat | Role | Family | Policy / TTL | Tape | Scope | Phase | Status |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| `INCIDENT` | `incident` | `incident.off_track` | opening | `incident.event` | result / 30s | `race.incident.event` | `incident_event` | event | legacy |
| `INCIDENT_AFTERMATH` | `incident_aftermath` | `incident.aftermath` | update | `incident.aftermath` | context / 20s | `race.incident.aftermath` | `incident_aftermath` | aftermath | legacy |
| `BACK_UNDER_WAY` | `back_under_way` | `incident.recovery` | closure | `incident.recovery` | result / 30s | `race.incident.recovery` | `incident_recovery` | recovery | legacy |

**INCIDENT branch beats:** primary `incident.off_track`; registry also binds `incident.unclassified` for unknown/off-surface classification (`classify_incident_branch` → off_track \| unknown). Missing surface evidence stays unclassified — never invent contact or damage.

**Emitters / adapters (Slice 2):**

| Wire | Emitter | Adapter |
| --- | --- | --- |
| `INCIDENT` | `irswitch.events.incident:IncidentEmitter` | `irswitch.events.adapters.exception_extra:incident_race_event_to_envelope` |
| `INCIDENT_AFTERMATH` | `irswitch.race.aftermath:IncidentAftermathFsm` | FSM direct (same module) |
| `BACK_UNDER_WAY` | `irswitch.race.aftermath:IncidentAftermathFsm` | FSM direct (same module) |

## Slice 3 inventory — session flag (yellow / green / checkered)

| Wire id | Legacy node | Beat | Role | Family | Policy / TTL | Tape | Scope | Status |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| `SESSION_FLAG` | `session_flag_yellow` | `session.flag.yellow` | control | `session.flag` | critical / 45s | `race.control.flag` | `flag_control` | legacy |

**SESSION_FLAG branch beats:** primary `session.flag.yellow`; registry also binds `session.flag.green` and `session.checkered` (`SESSION_FLAG_BRANCH_BEAT_IDS`, `SESSION_FLAG_PRIMARY_BEAT_ID`). `SessionFlagFsm` rising-edge kinds `yellow|green|checkered` map onto those beats; start lights are ignored.

**Notes lock:** checkered branch ≠ hero finish / session wrap (those stay separate stories). Missing/unclear flag evidence stays unknown — never invent yellow/green/checkered.

**Emitters / adapters (Slice 3):**

| Wire | Emitter | Adapter |
| --- | --- | --- |
| `SESSION_FLAG` | `irswitch.race.flags:SessionFlagFsm` | FSM direct (same module) |

## Slice 4 inventory — checkered clock / hero finish / session wrap

| Wire id | Legacy node | Beat | Role | Family | Policy / TTL | Tape | Scope | Status |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| `SESSION_CHECKERED` | `session_checkered` | `session.checkered` | outcome | `session.flag` | critical / 45s | `race.control.flag` | `session_checkered` | legacy |
| `FINISH` | `finish` | `session.hero_finish` | outcome | `session.finish` | critical / 45s | `race.session.finish` | `hero_finish` | legacy |
| `SESSION_WRAP` | `session_wrap` | `session.wrap.practice` | closure | `session.wrap` | result / 30s | `session.lifecycle` | `session_wrap` | legacy |

**SESSION_WRAP branch beats:** primary `session.wrap.practice`; registry also binds `session.wrap.qualifying` and `session.wrap.race` (`SESSION_WRAP_BRANCH_BEAT_IDS`, `SESSION_WRAP_PRIMARY_BEAT_ID`).

**Separation AC:** distinct scopes (`session_checkered` / `hero_finish` / `session_wrap`) and families (`session.flag` / `session.finish` / `session.wrap`); `FINISH` tape ≠ checkered; `SESSION_WRAP` tape ≠ `FINISH`; each row's notes cross-reference the other two story kinds. `SESSION_FLAG` still owns the flag checkered *branch* separately from the `SESSION_CHECKERED` wire.

**Emitters / adapters (Slice 4):**

| Wire | Emitter | Adapter |
| --- | --- | --- |
| `SESSION_CHECKERED` | `irswitch.events.lifecycle_edges:LifecycleTriggerBank` | LifecycleTriggerBank direct |
| `FINISH` | `irswitch.events.lifecycle_edges:LifecycleTriggerBank` | LifecycleTriggerBank direct |
| `SESSION_WRAP` | `irswitch.race.narrative:StreamNarrativeFsm` | FSM direct (same module) |

**`OPS_WIRE_IDS`:** **13** wires (6 pit + 3 incident + 1 flag + 3 closeout).

Helpers: `ops_family_rows()`, `row_for_wire_id()`, `rows_by_migration_status()`, `migration_status_by_wire_id()`, `pit_cycle_phase_order_is_monotonic()`, `pit_cycle_stories_have_explicit_terminals()`, `incident_cycle_phase_order_is_monotonic()`, `incident_stories_have_explicit_terminals()`, `incident_branch_beats_are_documented()`, `session_flag_branch_beats_are_documented()`, `session_wrap_branch_beats_are_documented()`, `closeout_stories_are_separated()`.

## AC locks (Slices 1–4)

- **Pit phase order** — `entry → lane → stopped → released → exit → outcome`.
- **Pit explicit terminals** — only `PIT_EXIT` / `PIT_OUTCOME` carry `terminal_reasons`; every pit wire has `invalidate_reasons`.
- **Incident phase order** — `event → aftermath → recovery`.
- **Incident explicit terminals** — only `BACK_UNDER_WAY` carries `terminal_reasons`; every incident wire has `invalidate_reasons`.
- **INCIDENT branch beats** — primary `incident.off_track`; branch list `incident.off_track`, `incident.unclassified` documented in row notes.
- **SESSION_FLAG branch beats** — primary `session.flag.yellow`; branch list `session.flag.yellow`, `session.flag.green`, `session.checkered` documented in row notes; checkered ≠ hero finish / session wrap; unknown not invented.
- **Closeout separation** — `SESSION_CHECKERED` / `FINISH` / `SESSION_WRAP` keep distinct scopes + families; finish tape ≠ checkered; wrap tape ≠ finish; notes cross-reference; flag checkered branch remains on `SESSION_FLAG`.
- **SESSION_WRAP branch beats** — primary `session.wrap.practice`; branch list `session.wrap.practice`, `session.wrap.qualifying`, `session.wrap.race` documented in row notes.

## Later #276 slices

Deferred: tow/teleport outcomes; EN patterns + adversarial tests; shadow activation.

## Docs / config

- **Docs:** this page + `docs/v2.0.0/README.md` + `docs/dokumentace/{README,inflight/README,domeny/events}.md`.
- **Docs: CONFIG.md / API.md unchanged** (inventory-only).
