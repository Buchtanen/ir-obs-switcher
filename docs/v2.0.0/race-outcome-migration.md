# #274 Race-outcome family migration

**Status:** Slice 1 — source map + polarity inventory (all families still `legacy`).  
**Issue:** [#274](https://github.com/Buchtanen/ir-obs-switcher/issues/274)  
**Module:** `src/irswitch/contracts/race_outcome_family_map.py`  
**Tests:** `tests/test_race_outcome_family_map.py`  
**Lookup:** [inflight § #274](../dokumentace/inflight/README.md#274-race-outcome-family-map-slice-1-lookup) · [events branch delta](../dokumentace/domeny/events.md#race-outcome-migration-map-contractsrace_outcome_family_mappy)

## Guardrails

- Does **not** rewrite frozen `docs/v2.0.0/machine/*` hashes.
- Does **not** flip `FAMILY_ROUTE` / shadow → v2 activation.
- Integration-only; no master PR until cutover.

## Inventory (slice 1)

| Wire id | Legacy node | Beat | Predicate | Family | Policy / TTL | Tape | Status |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| `OVERTAKE` | `overtake` | `position.pass` | `position.passed` | `position.pass` | critical / 45s | `race.position.pass` | legacy |
| `POSITION_GAINED` | `position_gained` | `position.gained` | `position.changed (`direction=gained`)` | `position.change` | result / 30s | `race.position.change` | legacy |
| `POSITION_LOST` | `position_lost` | `position.lost` | `position.changed (`direction=lost`)` | `position.change` | result / 30s | `race.position.change` | legacy |
| `LEADER_CHANGE` | `leader_change` | `position.leader_change` | `position.leader_changed` | `position.leader` | result / 30s | `race.position.leader` | legacy |
| `FINISH` | `finish` | `session.hero_finish` | `race.hero_finished` | `session.finish` | critical / 45s | `race.session.finish` | legacy |
| `OVERTAKEN` | `—` | `—` | `—` | `—` | — | `compat.alias` | legacy alias (not creatable) |

`migration_status_by_wire_id()` is the coverage-matrix companion that records every family as migrated/legacy; slice 1 keeps all values at `legacy`.

## Polarity contract (tested)

- `gain` ≠ `loss` beat, direction equals, and adapter mapping (`gain`→`POSITION_GAINED`, `loss`→`POSITION_LOST`).
- Pass keeps passer→passed actor frame (`hero→target`) and passer-then-target ordinal attributes.
- `OVERTAKEN` cannot create an opportunity; migrate later to `POSITION_LOST` + cause fact.
- Speakable outcomes use self-contained policies (`critical` / `result`).

## Emitters / adapters

| Wire | Emitter | Adapter |
| --- | --- | --- |
| `OVERTAKE` | `events.overtake:OvertakeClassifierEmitter` | `adapters.position:position_race_event_to_envelope` |
| `POSITION_*` | `events.position:PositionEmitter` | `adapters.position:_event_type_for_position_change` |
| `LEADER_CHANGE` | `events.leader_change:LeaderChangeEmitter` | `adapters.position:position_race_event_to_envelope` |
| `FINISH` | `events.lifecycle_edges:LifecycleTriggerBank` | `adapters.session:session_race_event_to_envelope` |

## Known later-slice gaps

- Shadow `FAMILY_ROUTE["position"]` still `legacy`; bridge alias drift (`PASS` / `POSITION_GAIN`) vs wire ids above.
- EN pattern curation, verifier minimal pairs, shadow then per-family activation remain open on #274.

## Next slices

2. Story / correlation / outcome TTL contract tests  
3. EN realization patterns  
4. Verifier minimal pairs  
5. Shadow (`position` → `shadow` after routing fix)  
6. Per-family activation (integration-only)
