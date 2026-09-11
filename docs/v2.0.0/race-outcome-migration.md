# #274 Race-outcome family migration

**Status:** Slice 4 — verifier minimal pairs (still all `legacy`) (all families still `legacy`).  
**Issue:** [#274](https://github.com/Buchtanen/ir-obs-switcher/issues/274)  
**Module:** `src/irswitch/contracts/race_outcome_family_map.py`  
**Tests:** `tests/test_race_outcome_family_map.py`  
**Lookup:** [inflight § #274](../dokumentace/inflight/README.md#274-race-outcome-family-map-slice-3-lookup) · [events branch delta](../dokumentace/domeny/events.md#race-outcome-migration-map-contractsrace_outcome_family_mappy)

## Guardrails

- Does **not** rewrite frozen `docs/v2.0.0/machine/*` hashes.
- Does **not** flip `FAMILY_ROUTE` / shadow → v2 activation.
- Integration-only; no master PR until cutover.

## Inventory

| Wire id | Legacy node | Beat | Role | Predicate | Family | Policy / TTL | Tape | Status |
| --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| `OVERTAKE` | `overtake` | `position.pass` | outcome | `position.passed` | `position.pass` | critical / 45s | `race.position.pass` | legacy |
| `POSITION_GAINED` | `position_gained` | `position.gained` | result | `position.changed (`direction=gained`)` | `position.change` | result / 30s | `race.position.change` | legacy |
| `POSITION_LOST` | `position_lost` | `position.lost` | result | `position.changed (`direction=lost`)` | `position.change` | result / 30s | `race.position.change` | legacy |
| `LEADER_CHANGE` | `leader_change` | `position.leader_change` | result | `position.leader_changed` | `position.leader` | result / 30s | `race.position.leader` | legacy |
| `FINISH` | `finish` | `session.hero_finish` | outcome | `race.hero_finished` | `session.finish` | critical / 45s | `race.session.finish` | legacy |
| `OVERTAKEN` | `—` | `—` | `—` | `—` | `—` | — | `compat.alias` | legacy alias (not creatable) |

`migration_status_by_wire_id()` is the coverage-matrix companion that records every family as migrated/legacy; slices 1–2 keep all values at `legacy`.

## Story / correlation / TTL (slice 2)

| Wire | Correlation kind | Bindings | Closing story routes | Fallback | Adapter prefix |
| --- | --- | --- | --- | --- | --- |
| `OVERTAKE` | `target` | hero, target | `battle_ahead`, `battle_two_front` | `single_result` | `position:` |
| `POSITION_GAINED` | `hero_position` | hero, oldPosition, newPosition, direction | — | `single_result` | `position:` |
| `POSITION_LOST` | `hero_position` | hero, oldPosition, newPosition, direction | `battle_behind`, `battle_two_front` | `single_result` | `position:` |
| `LEADER_CHANGE` | `leader` | oldLeader, newLeader | — | `single_result` | `leader:` |
| `FINISH` | `hero_finish` | occurrence, hero | `session_occurrence` | `single_result` | `session:` |
| `OVERTAKEN` | `none` | — | — | — | — |

Contract locks:

- Closing routes ⊆ beat `storyRoutes`; fallback ∈ `storyRoutes` (creatable rows).
- Beat roles: pass/finish → `outcome`; gain/loss/leader → `result`.
- Outcome TTL comes from policy catalog (`critical` 45s, `result` 30s).
- Speakable policies stay in `SELF_CONTAINED_POLICIES` (`critical` / `result`).

## Polarity contract (tested)

- `gain` ≠ `loss` beat, direction equals, and adapter mapping (`gain`→`POSITION_GAINED`, `loss`→`POSITION_LOST`).
- Pass keeps passer→passed actor frame and passer-then-target ordinal attributes.
- `OVERTAKEN` cannot create an opportunity; migrate later to `POSITION_LOST` + cause fact.

## Emitters / adapters

| Wire | Emitter | Adapter |
| --- | --- | --- |
| `OVERTAKE` | `irswitch.events.overtake:OvertakeClassifierEmitter` | `irswitch.events.adapters.position:position_race_event_to_envelope` |
| `POSITION_GAINED` | `irswitch.events.position:PositionEmitter` | `irswitch.events.adapters.position:_event_type_for_position_change` |
| `POSITION_LOST` | `irswitch.events.position:PositionEmitter` | `irswitch.events.adapters.position:_event_type_for_position_change` |
| `LEADER_CHANGE` | `irswitch.events.leader_change:LeaderChangeEmitter` | `irswitch.events.adapters.position:position_race_event_to_envelope` |
| `FINISH` | `irswitch.events.lifecycle_edges:LifecycleTriggerBank` | `irswitch.events.adapters.session:session_race_event_to_envelope` |

## Known later-slice gaps

- Shadow `FAMILY_ROUTE["position"]` still `legacy`; bridge alias drift vs wire ids above.
- Shadow then per-family activation remain open on #274.
- Deeper speak-path proof for “self-contained if opening unspoken” stays open (policy flag + existing retention regression; not yet live activation).


## EN realization patterns (slice 3)

Curated without rewriting frozen `machine/realization-pattern-cards.json` hashes:

| Wire | Beat pattern ids (4× tight) | Claim-surface polarity | Forbidden tokens |
| --- | --- | --- | --- |
| `OVERTAKE` | `position.pass:tight:1..4` | passer→passed via `{targetSurface}` | `is passed by`, `loses position to`, `drops behind` |
| `POSITION_GAINED` | `position.gained:tight:1..4` | `gains` / `moves up` / `climbs` / `improves` to `P{newPosition}` | `drops`, `slips`, `loses`, `falls back` |
| `POSITION_LOST` | `position.lost:tight:1..4` | `drops` / `slips` / `loses a spot` / `falls back` | `gains`, `climbs`, `moves up`, `improves` |
| `LEADER_CHANGE` | `position.leader_change:tight:1..4` | old→new leader surfaces | `hero wins the race`, `checkered` |
| `FINISH` | `session.hero_finish:tight:1..4` | observed `P{finishPosition}` | provisional / unofficial class language |
| `OVERTAKEN` | — | — | — |

Rows expose `en_pattern_ids`, `en_claim_surfaces`, `en_forbidden_tokens`. Creatable families require ≥4 catalog-backed EN pattern ids whose `beatId`/`family` match the inventory row.


## Verifier minimal pairs (slice 4)

Module: `src/irswitch/contracts/race_outcome_verifier_pairs.py` (tests: `tests/test_race_outcome_verifier_pairs.py`).

Closed accept/reject inventory for each creatable wire, exercised through `SemanticVerifier` without rewriting frozen `machine/realization-corpus.json`:

| Wire | Positive | Reject axes |
| --- | --- | --- |
| `OVERTAKE` | passer→passed claim | actor reverse; inverted “is passed by” |
| `POSITION_GAINED` | gain ordinal claim | loss wording under gain frame |
| `POSITION_LOST` | loss ordinal claim | gain wording under loss frame |
| `LEADER_CHANGE` | new leader claim | actor reverse (old leader as subject) |
| `FINISH` | observed finish position | unsafe negation / polarity mismatch |
| `OVERTAKEN` | — | no pairs (non-creatable alias) |

Cross-check: gain and loss positive utterances cannot both accept when frames are swapped.

## Next slices

3. ~~EN realization patterns~~ (this slice)
4. ~~Verifier minimal pairs~~ (landed)  
5. Shadow (`position` → `shadow` after routing fix)  
6. Per-family activation (integration-only)
