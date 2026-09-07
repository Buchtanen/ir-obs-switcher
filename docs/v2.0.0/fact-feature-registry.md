# v2.0.0 fact, feature and tape-channel registry freeze

**Status:** design-freeze candidate owned by issues #236, #245, #247 and #256

This branch-only artifact removes placeholder claims such as “one selected fact”. It is the human-readable source for the generated machine registries and 64-beat claim projection under `machine/`.

## Scalar and enum types

| Name | Contract |
| --- | --- |
| `boolean` | JSON boolean; missing is not `false` |
| `id` | non-empty ASCII identifier matching `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$` |
| `text` | trimmed UTF-8 display text, 1..160 code points; never interpreted as an ID |
| `seconds` | finite float, SI seconds |
| `seconds_per_second` | finite signed float; negative gap slope means closing |
| `fraction` | finite float 0..1 |
| `count` | nonnegative integer |
| `signed_count` | signed integer |
| `ordinal` | integer >=1 |
| `lap_number` | integer >=0; claim surface must distinguish current/completed semantics |
| `celsius` | finite float, degrees Celsius |
| `meters_per_second` | finite nonnegative float |
| `beats_per_minute` | integer 20..260 after provider validation |
| `stage` | `practice|qualifying|race` |
| `vehicle_phase` | `garage|pit_lane|out_lap|timed_lap|in_lap|parade_lap|racing|unknown` |
| `broadcast_context` | `on_track|garage|lobby|replay|transition|unknown` |
| `fact_quality` | `measured|derived|estimated|degraded|unknown` |

Missing, malformed, stale or identity-conflicting input produces no active value (or an explicit `status=unknown` record when audit requires it). It is never coerced to zero, false, an empty actor or a previous occurrence value. Any enum literal `unknown` is legal only on such a non-active audit record; it is never eligible as a current claim. Occurrence and lineage identity live only in the common AtomicFact fields unless an attribute explicitly references a different/predecessor occurrence. All `revalidate` predicates in this baseline require a coherent occurrence; transition creates new fact identity/revision under the new occurrence rather than carrying the old fact as current.

## Canonical fact predicates

`Actors` gives ordered subject→object semantics. Attributes not listed are invalid. Evidence refs and confidence remain common AtomicFact fields rather than predicate attributes.

| Predicate ID | Actors | Required attributes (type/unit) | Legal scope | Authoritative producer/input |
| --- | --- | --- | --- | --- |
| `stream.started` | — | `startReason:stream_start_reason` | stream | logic BroadcastClock/StreamTimeline; common fact fields carry both epochs |
| `session.started` | — | `stage:stage`, `startReason:session_start_reason` | occurrence | logic StreamTimeline |
| `session.restarted` | — | `stage:stage`, `predecessorOccurrenceId:id` | occurrence | logic StreamTimeline confirmed same-ref rewind |
| `session.ended` | — | `stage:stage`, `reason:session_end_reason` | historical_only | logic StreamTimeline |
| `session.next_present_stage` | — | `stage:stage`, `sourceSubSessionId:id`, `sourceSessionNum:count` | occurrence | typed SessionInfo.Sessions plan projection |
| `vehicle.entered_car` | hero | `stage:stage` | occurrence | vehicle-phase edge |
| `vehicle.phase` | hero | `phase:vehicle_phase` | occurrence | versioned VehiclePhase classifier |
| `broadcast.context` | — | `context:broadcast_context` | stream | logic SwitchState projection; superseded on normalized context change |
| `timing.lap_completed` | hero | `lap:lap_number`; optional `lapTime:seconds` | occurrence | S/F crossing + completed-lap timing |
| `timing.personal_best` | hero | `lapTime:seconds`, `referenceTime:seconds`, `improvement:seconds` | downstream | completed-lap comparison |
| `timing.delta_improved` | hero | `delta:seconds`, `referenceId:id`, `segmentId:id` | occurrence | timing reference comparison; magnitude normalized positive |
| `timing.delta_worsened` | hero | `delta:seconds`, `referenceId:id`, `segmentId:id` | occurrence | timing reference comparison; magnitude normalized positive |
| `timing.sector_completed` | hero | `sectorId:id`, `segmentTime:seconds`; optional `delta:seconds` | occurrence | sector crossing |
| `timing.sector_best` | hero | `sectorId:id`, `segmentTime:seconds`, `referenceTime:seconds`, `improvement:seconds` | occurrence | sector best store |
| `timing.target_locked` | hero | `targetPosition:ordinal`, `gap:seconds`, `referenceId:id` | occurrence | qualifying/practice target detector |
| `timing.lap_projection` | hero | `projectedTime:seconds`, `estimatorVersion:id`, `quality:fact_quality` | occurrence | versioned lap projection feature |
| `timing.active_attempt` | hero | `attemptId:id` | occurrence | hot/timed-lap lifecycle |
| `timing.position_projection` | hero | `targetPosition:ordinal`, `projectedTime:seconds`, `referenceTime:seconds` | occurrence | qualifying position estimator |
| `timing.clean_lap_streak` | hero | `count:count` | occurrence | consecutive completed valid-lap counter |
| `timing.pace_target` | hero | `targetPosition:ordinal`, `gap:seconds`, `referenceId:id` | occurrence | PACE_HUNT detector |
| `battle.closing` | closer→target | `gap:seconds`, `netClosing:seconds`, `slope:seconds_per_second`, `targetEpoch:id` | occurrence | correlated temporal gap detector |
| `battle.approaching` | closer→target | `materialBand:material_band`, `gap:seconds`, `targetEpoch:id` | occurrence | closing lifecycle band |
| `battle.attack_range` | attacker→target | `gapBand:gap_band`, `gap:seconds`, `targetEpoch:id` | occurrence | attack-range detector |
| `battle.side_by_side` | hero→target | `relationEpoch:id` | occurrence | overlap/composite detector |
| `battle.position_threat` | challenger→defender | `positionAtRisk:ordinal`, `relationEpoch:id` | occurrence | rear-threat detector |
| `battle.outcome` | hero→target | `outcome:battle_outcome`, `relationEpoch:id` | historical_only | correlated battle result |
| `position.passed` | passer→passed | `oldPasserPosition:ordinal`, `newPasserPosition:ordinal`, `oldTargetPosition:ordinal`, `newTargetPosition:ordinal` | historical_only | ordered position transition |
| `position.changed` | hero | `oldPosition:ordinal`, `newPosition:ordinal`, `direction:position_direction` | historical_only | class/overall position transition with declared scope |
| `position.leader_changed` | oldLeader→newLeader | `oldCarId:id`, `newCarId:id` | historical_only | leader identity edge |
| `incident.occurred` | hero | `incidentOrdinal:count`, `incidentDelta:count` | occurrence | incident count/event edge |
| `incident.off_track` | hero | `incidentOrdinal:count`, `surface:surface_band` | occurrence | explicit surface classification |
| `incident.lap_invalid` | hero | `lap:lap_number`, `attemptId:id` | occurrence | invalid-lap edge |
| `incident.state` | hero | `incidentOrdinal:count`, `state:incident_state` | occurrence | aftermath FSM |
| `incident.recovered_motion` | hero | `incidentOrdinal:count`, `heldFor:seconds` | historical_only | aftermath recovery FSM |
| `vehicle.surface` | hero | `surface:surface_band` | occurrence | normalized CarIdxTrackSurface |
| `pit.phase` | hero | `phase:pit_phase`, `cycleOrdinal:count` | occurrence | pit lifecycle FSM |
| `pit.outcome` | hero | `cycleOrdinal:count`, `entryPosition:ordinal`, `exitPosition:ordinal`, `positionDelta:count`, `direction:position_direction` | historical_only | correlated pit entry/exit comparison |
| `race.flag_changed` | — | `flag:flag_state`, `scope:flag_scope` | occurrence | normalized SessionFlags edge |
| `race.checkered_active` | — | — | occurrence | checkered state/edge dedupe |
| `race.final_lap` | hero | `lap:lap_number` | occurrence | final-lap edge |
| `race.hero_finished` | hero | `position:ordinal`; optional `classPosition:ordinal`, `classificationStatus:classification_status` | historical_only | observed player finish; not assumed official |
| `session.qualifying_result` | hero | `position:ordinal`; optional `bestLapTime:seconds` | downstream | completed qualifying occurrence summary |
| `field.strength` | — | `value:count`, `fieldScope:field_scope`, `sampleCount:count`, `official:boolean` | occurrence | iRating roster computation |
| `weather.air_temperature` | — | `value:celsius`, `source:weather_source` | revalidate | weather extractor |
| `weather.track_temperature` | — | `value:celsius`, `source:weather_source` | revalidate | weather extractor |
| `weather.skies` | — | `value:skies_state`, `source:weather_source` | revalidate | weather extractor |
| `weather.wind_speed` | — | `value:meters_per_second`, `source:weather_source` | revalidate | weather extractor |
| `weather.precipitation` | — | `value:fraction`, `source:weather_source` | revalidate | live weather extractor |
| `weather.track_wetness` | — | `value:track_wetness_band`, `source:weather_source` | revalidate | live/declared wetness extractor |
| `weather.changed` | — | `metric:weather_metric`, `oldFactId:id`, `newFactId:id`, `materialRevision:count` | occurrence | material weather comparison |
| `context.hero_position` | hero | `position:ordinal`, `positionScope:position_scope` | occurrence | current RaceState projection |
| `context.field_size` | — | `count:count`, `fieldScope:field_scope` | occurrence | roster/RaceState projection |
| `context.track_identity` | — | `displayName:text`; optional `trackId:id` | stream | SessionContext/WeekendInfo; TrackID is metadata, never SessionRef |
| `context.nearby_gap` | hero→target | `direction:relative_direction`, `gap:seconds`, `targetEpoch:id` | occurrence | current valid gap projection |
| `context.session_progress` | hero | optional `lap:lap_number`, optional `lapsRemaining:count`, optional `timeRemaining:seconds`; at least one required | occurrence | current session projection |
| `context.leader_identity` | leader | `positionScope:position_scope` | occurrence | current leader projection |
| `bio.hr_state` | hero | `band:hr_band`, `bpm:beats_per_minute`, `sampleAge:seconds`, `sensorEpoch:id` | revalidate | BLE provider/band detector |

Enum registries are closed for v2 baseline:

- `stream_start_reason`: `normal|attached_live|process_recovery|enabled_mid_stream`;
- `session_start_reason`: `normal_transition|attached_mid_session|same_ref_restart|rewind_branch|reconnect_classified`;
- `session_end_reason`: `completed|forward_transition|rewind_superseded|same_ref_restart|stream_ended`;
- `material_band`: `none|minor|material|major`;
- `gap_band`: `closing|approach|attack|overlap`;
- `battle_outcome`: `won|held|faded`; none implies a pass;
- `position_direction`: `gained|lost|unchanged`;
- `surface_band`: `on_track|off_track|pit_stall|pit_road|not_in_world|unknown`;
- `incident_state`: `rolling|stalled|towing|unknown`;
- `pit_phase`: `entry|lane|stopped|released|exit`;
- `flag_state`: `green|yellow|checkered`;
- `flag_scope`: `session|local|unknown`;
- `classification_status`: `observed|provisional`; `official` is unsupported until a future schema version binds an explicit official source;
- `field_scope`: `overall|class`;
- `position_scope`: `overall|class`;
- `weather_source`: `live|session`; forecast values are unsupported as v2 factual claims;
- `skies_state`: `clear|partly_cloudy|mostly_cloudy|overcast`;
- `track_wetness_band`: `dry|mostly_dry|very_lightly_wet|lightly_wet|moderately_wet|very_wet|extremely_wet`; raw iRSDK value `0` is unknown and produces no active fact;
- `weather_metric`: `air_temperature|track_temperature|skies|wind_speed|precipitation|track_wetness`;
- `relative_direction`: `ahead|behind`;
- `hr_band`: `calm|focused|pushing|high`; stale, disconnected or unclassifiable input produces no active `bio.hr_state` fact.

## Exact context-claim allowlists

These replace free “one selected fact” wording. The left-hand symbols are closed registry IDs used by BeatDefinition claim signatures:

- `W_weather`: one to three current facts from `weather.air_temperature`, `weather.track_temperature`, `weather.skies`, `weather.wind_speed`, `weather.precipitation`, `weather.track_wetness`; each remains a separate selected claim. Used by `session.weather_brief`.
- `W_field`: exactly one of `context.hero_position`, `context.field_size`, `context.track_identity`, `context.nearby_gap`, `context.session_progress`, `context.leader_identity` or `field.strength`. Used by `session.field_fact`.
- `W_filler_phase`: exactly one fresh fact whose predicate is in the union of `W_field` and `W_weather`, in addition to the beat's exact matching `vehicle.phase`. Used by `filler.out_lap`, `filler.in_lap`, `filler.parade_lap`.
- `W_filler_off_track`: exactly one `context.track_identity`, `context.field_size`, current supported `context.session_progress`, or one predicate admitted by `W_weather`, in addition to the beat's exact matching `broadcast.context`; on-track gaps/actions are forbidden. Used by `filler.garage`, `filler.lobby`. In the stream-scope/no-occurrence form of `filler.lobby`, the selected fact must also be stream-scoped, which currently leaves only `context.track_identity`; if it is absent, the beat is ineligible.
- `W_quiet_track`: exactly one current stable fact from `context.hero_position`, `context.leader_identity`, `context.session_progress`, `field.strength`, `context.field_size`, `context.track_identity` or one predicate admitted by `W_weather`, in addition to `broadcast.context(context=on_track)`. It cannot select a battle/timing projection/result merely to fill silence.
- `session.weather_change`: exactly `weather.changed` plus the referenced new weather fact; the old value may be spoken only if its old fact is present and selected.
- `incident.recovery`: `incident.recovered_motion` plus `vehicle.surface(surface=on_track)`; “known surface” alone is insufficient.

If an allowlist has no fresh fact, the beat fails `source_guard` and the director chooses another beat or silence.

## Canonical feature IDs

Features are immutable values for one frame/correlation. The registry implementation must attach value, unit, observed time, quality, evidence refs, occurrence/lineage and algorithm version.

| Feature ID | Value/unit | Algorithm/source | Unknown/invalidation |
| --- | --- | --- | --- |
| `gap.relation.seconds.estimated_v1` | seconds | fractional lap-distance × valid hero lap reference, keyed closer/target | target swap, wrap ambiguity, lap-down ambiguity, pit/tow/teleport, missing lap reference |
| `gap.relation.seconds.est_time_v1` | seconds | compatible `CarIdxEstTime` difference, keyed closer/target | missing/invalid est time, pit/tow/teleport, target swap |
| `gap.relation.seconds.hybrid_v1` | seconds | choose/compare registered estimators and export quality reason | estimator disagreement outside bound or both invalid |
| `gap.trend.slope` | seconds_per_second | least-squares slope over median time buckets | insufficient duration/coverage or changed target epoch |
| `gap.trend.net_closing` | seconds | first-third median minus last-third median | insufficient buckets/coverage |
| `gap.trend.coverage` | fraction | usable bucket time / requested window | no coercion; detector compares explicitly |
| `gap.trend.confidence` | fraction | deterministic quality composition from estimator/bucket/identity flags | unknown when required component unknown |
| `gap.target_stable` | boolean | same ordered actors and relation epoch for full window | false on target/role change |
| `battle.overlap_active` | boolean | relative order/distance overlap predicate with confirmation | unknown on missing ordered identities |
| `battle.two_front_active` | boolean | valid front closing AND valid rear closing for same hero/occurrence | unknown if either side unknown; false only when known false |
| `vehicle.phase.current` | vehicle_phase | versioned FSM over DrivingMode, SessionState, pit, surface, speed and lap progress | unknown on incoherent/missing evidence |
| `vehicle.motion.speed` | meters_per_second | normalized Speed | missing/stale |
| `vehicle.motion.lap_delta` | fraction | wrap-aware LapDistPct change | teleport/tow or missing sample |
| `timing.segment.delta` | seconds | current versus selected reference segment | reference/segment mismatch |
| `timing.lap.projection` | seconds | registered projection algorithm/version | insufficient completed segments or invalid lap |
| `position.current` | ordinal | class/overall position with explicit scope | missing or scope mismatch |
| `position.transition` | signed_count | previous-current within same occurrence/scope | reconnect baseline, missing sample or occurrence change |
| `incident.motion_state` | incident_state | surface-first aftermath FSM using speed/lap delta/tow | missing incident correlation |
| `weather.material_change` | material_band | per-metric registered delta/band comparison | old/new source or metric mismatch |
| `field.strength` | count | rounded eligible roster mean with sample count | empty/ambiguous roster |
| `bio.hr_band` | hr_band | provider sample plus versioned baseline/freshness bands | disconnected/stale/no baseline |

Only `estimated_v1` is required for the first slice. `est_time_v1`/`hybrid_v1` are later versions, not silent algorithm replacements. Predicate AST compares these named outputs; it cannot embed new arithmetic.

## Tape-channel registry

Every event/opportunity/decision/exposure uses exactly one taxonomy channel from this closed baseline set:

```text
bio.pressure
compat.alias
filler.lifecycle
filler.track_state
race.battle.attack
race.battle.closing
race.battle.outcome
race.battle.pressure
race.battle.side_by_side
race.battle.two_front
race.control.flag
race.incident.aftermath
race.incident.event
race.incident.invalid_lap
race.incident.recovery
race.pit.cycle
race.pit.outcome
race.position.change
race.position.leader
race.position.pass
race.session.final_lap
race.session.finish
race.timing.attempt
race.timing.consistency
race.timing.delta
race.timing.lap
race.timing.sector
race.timing.target
session.context.field
session.context.weather
session.lifecycle
session.qualifying.recap
session.vehicle
stream.lifecycle
system.connectivity
system.thermal
```

`compat.alias`, `system.connectivity` and `system.thermal` are recordable disposition channels but never speech opportunities. `filler.lifecycle` records the silence impulse; selected filler opportunities use `filler.track_state`. Purpose channels remain the separate `flow|llm_eval|detector_tuning` dimension.

## Source availability verdict

- Already present on master in some form: OBS stream edge/debounce; exact raw SessionInfo/SessionNum/SubSessionID; lap/sector/position/pit/flag/incident data; opponent identities/gap inputs; weather; roster/SoF; HR; DrivingMode/broadcast context.
- Requires a new typed owner/projection, not a new external dependency: session plan/lineage, VehiclePhase, FactLedger/FactView, versioned gap/trend features, target relation epochs and context allowlists.
- Intentionally unavailable as baseline truth: physical speaker sample, unrestricted-English semantic proof, driver intent/emotion/cause, guaranteed future outcome and official classification without an explicit source.

An optional unavailable source only suppresses dependent facts/beats. It never blocks the main loop or falls back to generic invented commentary.

## Closure checks

`machine/build_beat_catalog.py` now proves every required beat predicate, attribute, literal enum constraint, repeated-claim cardinality and allowlist reference resolves through this registry. It deliberately does not implement runtime predicate evaluation or successor-graph safety; those remain catalog-loader/graph gates.

Issue #236/#245/#247 cannot close until generated machine registries prove:

- every predicate/attribute/enum/feature/channel ID above is unique and case-exact;
- every attribute has one scalar type/unit and every fact has a legal scope/producer;
- all 64 beat claim signatures resolve only to these predicates and exact allowlists;
- all 60 identifier dispositions resolve to one channel; aliases/visual-only channels cannot create opportunities;
- all detector parameters reference existing feature IDs with compatible units;
- no current/historical/estimated/official status is inferred from an absent field.
