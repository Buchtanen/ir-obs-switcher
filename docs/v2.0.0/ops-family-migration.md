# #276 Ops family migration (pit / incident / flag / recovery)

**Status:** Slice 2 — pit + incident/aftermath/recovery inventory (Slices 1–2; all `legacy`; no `FAMILY_ROUTE` flip).  
**Issue:** [#276](https://github.com/Buchtanen/ir-obs-switcher/issues/276)  
**Module:** `src/irswitch/contracts/ops_family_map.py`  
**Tests:** `tests/test_ops_family_map.py` (**12**)  
**Lookup:** [inflight § #276 slice 1](../dokumentace/inflight/README.md#276-ops-family-map-slice-1-lookup) · [inflight § #276 slice 2](../dokumentace/inflight/README.md#276-ops-family-map-slice-2-lookup) · [events branch delta](../dokumentace/domeny/events.md#ops-family-migration-map-contractsops_family_mappy)

## Guardrails

- Does **not** rewrite frozen `docs/v2.0.0/machine/*` hashes.
- Does **not** flip `FAMILY_ROUTE` (pit/incident remain `legacy`).
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

Helpers: `ops_family_rows()`, `row_for_wire_id()`, `rows_by_migration_status()`, `migration_status_by_wire_id()`, `pit_cycle_phase_order_is_monotonic()`, `pit_cycle_stories_have_explicit_terminals()`, `incident_cycle_phase_order_is_monotonic()`, `incident_stories_have_explicit_terminals()`, `incident_branch_beats_are_documented()`.

## AC locks (Slices 1–2)

- **Pit phase order** — `entry → lane → stopped → released → exit → outcome`.
- **Pit explicit terminals** — only `PIT_EXIT` / `PIT_OUTCOME` carry `terminal_reasons`; every pit wire has `invalidate_reasons`.
- **Incident phase order** — `event → aftermath → recovery`.
- **Incident explicit terminals** — only `BACK_UNDER_WAY` carries `terminal_reasons`; every incident wire has `invalidate_reasons`.
- **INCIDENT branch beats** — primary `incident.off_track`; branch list `incident.off_track`, `incident.unclassified` documented in row notes.

## Later #276 slices

Deferred: yellow/green/checkered flags; checkered vs hero finish vs session end; unknown/tow/teleport outcomes; EN patterns + adversarial tests; shadow activation.

## Docs / config

- **Docs:** this page + `docs/v2.0.0/README.md` + `docs/dokumentace/{README,inflight/README,domeny/events}.md`.
- **Docs: CONFIG.md / API.md unchanged** (inventory-only).
