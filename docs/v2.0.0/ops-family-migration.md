# #276 Ops family migration (pit / incident / flag / recovery)

**Status:** Slice 1 — pit entry/service/exit/outcome inventory (all `legacy`; no `FAMILY_ROUTE` flip).  
**Issue:** [#276](https://github.com/Buchtanen/ir-obs-switcher/issues/276)  
**Module:** `src/irswitch/contracts/ops_family_map.py`  
**Tests:** `tests/test_ops_family_map.py`  
**Lookup:** [inflight § #276](../dokumentace/inflight/README.md#276-ops-family-map-slice-1-lookup) · [events branch delta](../dokumentace/domeny/events.md#ops-family-migration-map-contractsops_family_mappy)

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

Helpers: `ops_family_rows()`, `row_for_wire_id()`, `rows_by_migration_status()`, `migration_status_by_wire_id()`, `pit_cycle_phase_order_is_monotonic()`, `pit_cycle_stories_have_explicit_terminals()`.

## AC locks (Slice 1)

- **Pit phase order** — `entry → lane → stopped → released → exit → outcome`.
- **Explicit terminals** — only `PIT_EXIT` / `PIT_OUTCOME` carry `terminal_reasons`; every wire has `invalidate_reasons`.

## Later #276 slices

Deferred: incident/excursion/aftermath/recovery; yellow/green/checkered flags; checkered vs hero finish vs session end; unknown/tow/teleport outcomes; EN patterns + adversarial tests; shadow activation.

## Docs / config

- **Docs:** this page + `docs/v2.0.0/README.md` + `docs/dokumentace/{README,inflight/README,domeny/events}.md`.
- **Docs: CONFIG.md / API.md unchanged** (inventory-only).
