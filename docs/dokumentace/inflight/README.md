# In-flight documentation — `codex/commentary-story-flow-spec`

**Status:** v2 narrative runtime Wave A–B (#235–#246) and Wave C [#247](https://github.com/Buchtanen/ir-obs-switcher/issues/247)–[#256](https://github.com/Buchtanen/ir-obs-switcher/issues/256) remain implemented; Wave D [#257](https://github.com/Buchtanen/ir-obs-switcher/issues/257)–[#260](https://github.com/Buchtanen/ir-obs-switcher/issues/260) is **closed** on this branch; **not shipped on `master`**. Next implementation package is [#261](https://github.com/Buchtanen/ir-obs-switcher/issues/261) (do not start unless a human says so).

## Where to look on this branch

| Need | Authority on this branch | Not shipped here |
| --- | --- | --- |
| Issue index, waves, dependencies | [docs/v2.0.0/README.md](../../v2.0.0/README.md) | `domeny/commentary.md` as master truth |
| Resume identity, closing SHAs, scope boundaries | [docs/v2.0.0/implementation-handover.md](../../v2.0.0/implementation-handover.md) | Public CONFIG/API/README product contracts (unchanged for #239–#257) |
| DTO/tape/schema freeze | [docs/v2.0.0/schema-contracts.md](../../v2.0.0/schema-contracts.md), [machine/](../../v2.0.0/machine/README.md) | Rewriting `machine/` hashes |
| Master domain pages (`domeny/*.md`, `architektura.md`, `mapa-souboru.md`, `stav.md`) | See `master` — **absent on this branch by design** | Copying master pages as if v2 were shipped |

## Implementation lookup (#239–#260, branch-only)

| Issue | Module placement | Key files | Tests |
| --- | --- | --- | --- |
| #239 NarrativeTape schema | contracts / DTO freeze (no writer) | `src/irswitch/contracts/schemas/v2/dto-contracts.schema.json`, `docs/v2.0.0/schema-contracts.md` | `tests/test_narrative_tape_schema.py` |
| #240 Tape writer | commentary | `commentary/tape_writer.py`, `commentary/tape_queue.py` | `tests/test_narrative_tape_queue.py`, `tests/test_narrative_tape_writer.py` |
| #241 CapturePlan | commentary | `commentary/capture_plan.py`, `capture_safety.py`, `tape_safety.py` | `tests/test_narrative_capture_plan.py`, `tests/test_narrative_capture_safety.py` |
| #242 Replay / labels | commentary | `commentary/tape_replay.py` | `tests/test_narrative_tape_replay.py` |
| #243 StreamTimeline | logic | `logic/stream_timeline.py`, `contracts/session.py` (SessionPlan) | `tests/test_stream_timeline.py` |
| #244 SessionOccurrence | logic + contracts + events | `contracts/session.py` (SessionOccurrence), `logic/stream_timeline.py`, `events/timeline_facts.py` | `tests/test_session_occurrence.py`, `tests/test_timeline_facts.py` |
| #245 AtomicFact ledger | events | `events/fact_ledger.py`, `events/timeline_facts.py` | `tests/test_fact_ledger.py`, `tests/test_timeline_facts.py` |
| #246 inheritance / summaries | events FactLedger | `events/fact_ledger.py` (`inherited_facts`, `historical`, `occurrence_summary`, `compactedSummaryRefs`) | `tests/test_fact_inheritance.py` |
| #247 FeatureEngine | contracts + events | `contracts/feature.py`, `events/feature_engine.py` — detail below | `tests/test_feature_engine.py` (**10**) |
| #248 gap estimators | events | `events/gap_estimators.py`, `events/feature_engine.py` (integration) — detail below | `tests/test_gap_estimators.py` (**13**) + `tests/test_feature_engine.py` (**10**) |
| #249 predicate AST | contracts + events | `contracts/predicate.py`, `events/predicate_ast.py` — detail below | `tests/test_predicate_ast.py` (**14**) |
| #250 DetectorBank FSM | events | `events/detector_bank.py` — detail below | `tests/test_detector_bank.py` (**19**) |
| #251 direct lap/sector edges | events | `events/direct_edges.py` — detail below | `tests/test_direct_edges.py` (**13**) |
| #252 stream/session lifecycle edges | events | `events/lifecycle_edges.py` — detail below | `tests/test_lifecycle_edges.py` (**13**) |
| #253 CLOSING temporal detector | events | `events/closing.py` — detail below | `tests/test_closing.py` (**19**) |
| #254 UNDER_PRESSURE temporal detector | events | `events/pressure.py` — detail below | `tests/test_pressure.py` (**14**) |
| #255 composite two-front battle detector | events | `events/two_front.py` — detail below | `tests/test_two_front.py` (**18**) |
| #256 event-family coverage matrix | contracts | `src/irswitch/contracts/coverage_matrix.py` — [§ lookup](#256-event-family-coverage-matrix-lookup) | `tests/test_coverage_matrix.py` (**15**) |
| #257 StoryDefinition catalog loader | contracts | `src/irswitch/contracts/catalog_loader.py` — [§ lookup](#257-storydefinition-catalog-loader-lookup) | `tests/test_catalog_loader.py` (**29**) |
| #258 lineage-aware EpisodeRegistry | events | `src/irswitch/events/episode_registry.py` — [§ lookup](#258-lineage-aware-episoderegistry-lookup) | `tests/test_episode_registry.py` (**13**) |
| #259 resolved-episode retention | events | `src/irswitch/events/episode_retention.py` — [§ lookup](#259-resolved-episode-retention-lookup) | `tests/test_episode_retention.py` (**9**) |
| #260 long-silence / filler opportunities | events | `src/irswitch/events/silence_clock.py` — [§ lookup](#260-long-silence-lifecycle-lookup) | `tests/test_silence_clock.py` (**14**) |

### #247 FeatureEngine lookup

- **Registry (`contracts/feature.py`):** `FeatureDefinition`, `FeatureRegistry`, `FeatureValue`, `FeatureFrame` (`feature-frame/2`); `FIRST_SLICE_FEATURE_ID`; `load_feature_registry()` reads packaged `freeze-registry.json` (21 frozen IDs; catalog `definition` strings are not evaluated); `validate_detector_feature_units()` cross-checks `detector-catalog.json` parameter units.
- **Engine (`events/feature_engine.py`):** `FeatureEngine`, `FeatureSample`, `FeatureStep`; per-correlation windows **32** / **64**; process-global monotonic `frameSequence`; duplicate or stale samples are audited no-ops.
- **Closed scope (#247):** first slice published `gap.relation.seconds.estimated_v1` only. #248 extended the same engine — see below; do not treat `est_time_v1` / `hybrid_v1` as silent replacements.
- **Exports / boundaries:** re-exported from `contracts/__init__.py`; **not** from `events/__init__.py`. Does not import NarrativeRuntime, DetectorBank, overlay tape or commentary; not wired into the live loop. Scope prose: [handover § #247](../../v2.0.0/implementation-handover.md).
- **Evidence:** first implementation SHA `62402838432dc8676be79b6c295b2e73513c6d6d`; lookup SHA `40ae7f63257cf70e94684a74c414c1e5f97cc129`; verifier GREEN (33 passed).

### #248 gap estimators lookup

- **Algorithms (`events/gap_estimators.py`):** `estimate_distance_v1`, `estimate_est_time_v1`, `choose_hybrid_v1`, `compute_trend`, helpers `forward_gap_fraction`, `wrap_ambiguous`, `wrap_aware_seconds`, `evidence()`. Catalog `definition` strings are never evaluated.
- **Feature IDs:** `gap.relation.seconds.estimated_v1`, `est_time_v1`, `hybrid_v1`; trend `gap.trend.coverage`, `gap.trend.slope`, `gap.trend.net_closing`. Hybrid emits only when both gap estimators agree within `HYBRID_MAX_DISAGREEMENT_S` (0.5 s); disagreement is unknown, never a silent substitution.
- **FeatureEngine integration (`events/feature_engine.py`):** each accepted sample runs all three gap estimators; trend is computed from per-window `estimated_v1` gap history. New `FeatureSample` fields: `closer_est_time_s`, `target_est_time_s`, `closer_lap`, `target_lap`, `in_world` (default `True`). Trend tunables on `FeatureEngine`: `sample_interval_s=0.25`, `bucket_s=1.0`, `trend_window_s=12.0`, `min_coverage=0.80`. Hard-invalid samples (`not_in_world`, pit, tow, teleport) evict the correlation window before trend.
- **Validity:** explicit unknown for wrap ambiguity, lap-down, pit/tow/teleport/`not_in_world`, target swap, missing lap reference / est time. S/F wrap (closer 0.98 / target 0.02) is valid. `est_time_v1` is omitted when neither est-time field is provided; it never replaces `estimated_v1`.
- **Evidence:** each `FeatureValue` includes its algorithm/feature ID in `evidenceRefs`; hybrid cites both parent estimator IDs.
- **Trend:** duration per bucket capped at `sample_interval_s`; a lone sample cannot fill a bucket. Slope/net-closing require three usable bucket medians; coverage is summed bucket duration / `trend_window_s` (capped at 1.0). Target swap clears usable trend history for the correlation.
- **Tests:** `tests/test_gap_estimators.py` (**13**); existing `tests/test_feature_engine.py` (**10**, first sample still only `estimated_v1`). First implementation SHA `4aa2e680ef76b6aa37ce993cbc37bef32e93db46`; docs checkpoint SHA `72067e31e66f3a2d39fc51cf47d7e5138ee3a500`.
- **Still out of scope:** live DetectorBank / NarrativeRuntime wiring; `gap.trend.confidence` / `gap.target_stable` remain registry-only.

### #249 predicate AST lookup

- **Compile (`contracts/predicate.py`):** `compile_detector_catalog` / `load_compiled_detector_catalog` turn packaged `detector-catalog.json` named atoms + frozen invariant strings into `all`/`any`/`not`/compare/`held_for` trees. `compile_predicate` also accepts structured nodes (`changed`, `changed_by`, `crossed`, `rising_edge`, `falling_edge`, `within`, `since`, `count`, `sequence`, `unknown`, `unusable`). Compile caps: `MAX_DEPTH=16`, `MAX_NODES=128`; evaluation cap `MAX_EVAL_STEPS=512`. Catalog `definition` / invariant prose is never executed (`eval`/`exec`/`compile` forbidden).
- **Atoms:** directional enter/clear/immediate/material IDs plus two-front atoms from `detector-catalog-freeze.md`. Unknown atom or invariant string fails catalog load. `unknownSatisfies` must be `false`. Undeclared feature/parameter or incompatible units fail compile.
- **Evaluate (`events/predicate_ast.py`):** `PredicateEvaluator` returns `PredicateResult` (`verdict` + reason tree; `satisfies` is false for unknown on enter/`held_for`). Missing/`quality=unknown` feature values are unknown; `feature_stale_or_unknown` is true on clear when the gap feature is missing or unusable.
- **Exports / boundaries:** compile/result DTOs re-exported from `contracts/__init__.py`; evaluator **not** exported from `events/__init__.py`. Does not import NarrativeRuntime, DetectorBank, overlay tape or commentary; not wired into the live loop.
- **Tests:** `tests/test_predicate_ast.py` (**14**). First implementation SHA `b24e3da0297b027a1d6b3399b2f8584fb70bbe4c`; docs checkpoint SHA `83a12eb3a0cc1e3f74c75d87d48a1fde9c22c924`; close docs SHA `4bdb0dd874d83d851b48ba77b1702789d9b75dc0`.
- **Still out of scope:** live DetectorBank wiring, NarrativeRuntime activation.

### #250 DetectorBank lookup

- **FSM (`events/detector_bank.py`):** `reduce_lifecycle` matches frozen `reduce_directional` goldens (`inactive|candidate|active|clearing`). `DetectorBank` keys instances by `(detectorId, detectorVersion, streamEpoch, occurrenceId, orderedCorrelationKey)`, evaluates compiled `enter_signal` / `clear` / `immediate` / `material_update` trees, and owns confirm/clear/update holds. Unknown never satisfies enter; unknown/stale clear starts the clear hold. Duplicate or older `frameSequence` is an audited no-op.
- **Emissions:** detector `STARTED`/`UPDATED`/`ENDED` only. Ahead maps to existing V4 `HUNTING`, behind to `HUNTED`. `endedEvent` stays null — no `HUNTING_ENDED`. Material revisions compare to the last emitted net-closing/band and are rate-limited by `update_min_interval_s`. Close expires `battle.closing` as a recorded fact predicate; FactLedger is not called.
- **Scope:** directional catalog detectors only. Band projection (`reduce_band`) is implemented in #253; two-front composite (`reduce_composite` / `BATTLE_FOR_POSITION`) is #255. `disable_for_run(..., required_capture_lost)` is the narrow capture-loss control; it does not import commentary.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import NarrativeRuntime, overlay tape or commentary; not wired into the live loop.
- **Tests:** `tests/test_detector_bank.py` (**19**), including the seven directional goldens. First implementation SHA `e41ffb42f5e83236a4db58194dd4c5903fbc0899`; docs checkpoint SHA `0a44978d2468f30bb343100c8b8731bd9850fb9b`.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #251 direct lap/sector edges lookup

- **Bank (`events/direct_edges.py`):** `DirectEdgeBank` / `DirectEdgeSample` / `DirectEdgeIdentity`. `sourceClass=direct` (null `detectorObservationId`). Identity is `(kind, streamEpoch, occurrenceId, heroId, lap[, sectorId])`. Duplicate/older `sampleSequence` is an audited no-op. Restart uses a new occurrence so the same lap number is a new identity; a same-occurrence lap reset cannot reuse a prior key.
- **Eligibility:** lap edges (`LAP_COMPLETE` → `timing.lap_completed` / `race.timing.lap`) require `overlay_mode` in `PRACTICE|QUALIFYING|RACE`. Sector edges (`SECTOR_SPLIT` / `SECTOR_BEST`) require `PRACTICE|QUALIFYING` only. `GENERIC`, disconnected, missing occurrence, missing sector metadata, or invalid sector ids emit nothing. `session_finished` / `player_finished` is a completed race, not a lap edge.
- **Current emitters:** `events/lap.py` and `events/sector_split.py` stay on master wiring. This slice characterizes them and does not live-replace them. DetectorBank thresholds are not reused (`tuning.policy=none`).
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import DetectorBank, NarrativeRuntime, overlay tape or commentary; not wired into the live loop.
- **Tests:** `tests/test_direct_edges.py` (**13**). First implementation SHA `5a61be3aae3b8c8b3bac91c1361f6f7c53e10278`; docs checkpoint SHA `f8eb07f`.
- **Still out of scope:** live EventManager wiring, lap/sector family migration (#275), NarrativeRuntime.

### #252 stream/session lifecycle edges lookup

- **Bank (`events/lifecycle_edges.py`):** `LifecycleTriggerBank` / `LifecycleSample` / `LifecycleCommand` / `LifecycleIdentity` / `LifecycleCandidate` / `LifecycleStep`. `sourceClass=lifecycle` (null `detectorObservationId`). Canonical kinds: `STREAM_STARTED`, `STREAM_ENDED`, `SESSION_STARTED`, `SESSION_ENDED`, `SESSION_RESTARTED`, `SESSION_CHECKERED`, `FINISH`. `STREAM_START` is rejected (`legacy_stream_start_rejected`), never aliased. `RESET` / `SESSION_REWOUND` are not narrative kinds.
- **Identity:** `(kind, streamEpoch[, occurrenceId][, heroId])`; `candidate_id` `lifecycle:{kind}:{streamEpoch}[:occurrence][:hero]`. Exact-once per confirmed transition; duplicate/stale `timelineRevision` is an audited no-op.
- **Distinct edges:** checkered, session end, and hero finish are separate. `SESSION_CHECKERED` / `FINISH` only for race occurrences. Same-step order: `SESSION_ENDED`, `SESSION_CHECKERED`, `FINISH`, `STREAM_ENDED`, `STREAM_STARTED`, `SESSION_STARTED`, `SESSION_RESTARTED`. Stream-end follows session invalidation; `invalidate_speech` on `STREAM_ENDED`.
- **Reason codes:** `attached_live` / `process_recovery` / `enabled_mid_stream` are `STREAM_STARTED` reason codes, not extra events. `broadcast_unknown` / `broadcast_resumed` without commands emit nothing. Previous/current occurrence+lineage attached on candidates.
- **Live paths unchanged:** live `STREAM_START` commentary path, `SessionEndTracker`, and V4 overlay wire stay on master wiring. Does not import StreamTimeline, DetectorBank, DirectEdgeBank, NarrativeRuntime, overlay tape or commentary.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Not wired into the live loop.
- **Tests:** `tests/test_lifecycle_edges.py` (**13**). First implementation SHA `c4688a40a43e40d47e2698114bcb06a245b97914`; docs checkpoint SHA `d3c1934c90e7f920059672c12e2eeb9a3c5193f6`.
- **Still out of scope:** live EventManager wiring, NarrativeRuntime (#284).

### #253 CLOSING temporal detector lookup

- **Band reducer (`events/closing.py`):** `reduce_band` matches frozen machine `bandBoundaries` goldens (`closing|approach|attack|overlap`). Hysteretic enter/exit thresholds from catalog defaults (`approach_enter_s` … `overlap_confirm_s`).
- **Product detector:** `ClosingDetector` / `ClosingTrace` / `ClosingCandidate` / `ClosingStep`. Uses `DetectorBank` for `battle_ahead_v1` FSM only; does not drive `battle_two_front_v1` or `reduce_composite` (#255). UNDER_PRESSURE / `battle_behind_v1` is #254.
- **V4 mapping:** `closing`→`HUNTING`, `approach`→`APPROACH`, `attack`→`ATTACK_RANGE`, `overlap`→`SIDE_BY_SIDE`. Close expires `battle.closing` plus band facts; no new V4 `*_ENDED`. One spike cannot activate (confirm hold). At most one latest band candidate per step. Decision trace exposes effective thresholds and evidence refs.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import NarrativeRuntime, overlay tape or commentary; not wired into the live loop.
- **Tests:** `tests/test_closing.py` (**19**), including eight `bandBoundaries` goldens. First implementation SHA `5362c3375ca40b80b75b9fc1ad13df1f3b80ca06`; docs checkpoint SHA `630bd19aa4400e38d10ef75b2b1b5f1228641854`.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #254 UNDER_PRESSURE temporal detector lookup

- **Band reducer:** reuses `reduce_band` from `events/closing.py` (matches frozen `bandBoundaries` goldens; no duplicate goldens in `tests/test_pressure.py`).
- **Product detector:** `PressureDetector` / `PressureTrace` / `PressureCandidate` / `PressureStep`. Uses `DetectorBank` for `battle_behind_v1` only (`detector_ids=("battle_behind_v1",)`); does not drive `battle_two_front_v1` or `reduce_composite` (#255).
- **V4 mapping:** `closing`→`HUNTED` / `battle.pressure_behind` / `race.battle.pressure`; inward bands `approach|attack|overlap`→`RIVAL_THREAT` / `battle.rival_threat` / `race.battle.pressure`. Facts: catalog `battle.closing` on the FSM; inward bands publish registered `battle.position_threat` (do not invent `battle.pressure_behind.band`, `UNDER_PRESSURE` V4 id / boolean / `*_ENDED`). Close expires `battle.closing` plus `battle.position_threat`; no new V4 end type. One spike cannot activate (confirm hold). At most one latest band candidate per step. Decision trace exposes effective thresholds and evidence refs.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import NarrativeRuntime, overlay tape or commentary; not wired into the live loop.
- **Tests:** `tests/test_pressure.py` (**14**); related regression `tests/test_pressure.py` + `tests/test_closing.py` + `tests/test_detector_bank.py` = **52** passed. First implementation SHA `13e01ef94481420e06be0859c76b7d0f427ae212`; docs checkpoint SHA `9f69d9110afdccdd39ae97863f9729c79009b0ad`.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #255 composite two-front battle detector lookup

- **Composite reducer (`events/two_front.py`):** `reduce_composite` matches frozen machine `compositeScenarios` goldens in `docs/v2.0.0/machine/detector-catalog-goldens.json`.
- **Product detector:** `TwoFrontDetector` / `TwoFrontTrace` / `TwoFrontCandidate` / `TwoFrontStep`. Uses compiled `battle_two_front_v1` predicates plus `reduce_lifecycle` from `events/detector_bank.py`; does **not** extend `DetectorBank` (bank stays directional-only; `detector_ids=("battle_two_front_v1",)` still emits nothing).
- **Correlation key:** `(streamEpoch, occurrenceId, frontRelationEpoch, rearRelationEpoch)` — target/epoch replacement force-closes the old instance under a new key; the old key is never mutated.
- **Open guards:** both parent relations active, same hero/occurrence, distinct targets, **and** both parent `battle.closing` truths supplied via `front_closing` / `rear_closing`. Composite never invents missing parent facts.
- **V4 mapping:** `BATTLE_FOR_POSITION` / `battle.two_front` / `race.battle.two_front` **once on confirmed entry only** (no UPDATED). Target/epoch replacement force-closes without a V4 end.
- **Features/facts:** publishes registered `battle.two_front_active` on STARTED; clears on ENDED. Catalog `factPredicate` is null — no two-front AtomicFact, no `*_ENDED`. One-side loss starts `two_front_clear_s`; restore of the same epochs cancels clearing without a new STARTED; remaining parent facts are not expired.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import NarrativeRuntime, overlay tape or commentary; not live-wired.
- **Tests:** `tests/test_two_front.py` (**18**), including six `compositeScenarios` goldens; related regression `tests/test_two_front.py` + `tests/test_closing.py` + `tests/test_pressure.py` + `tests/test_detector_bank.py` = **70** passed. First implementation SHA `ad9d092778e07982e3377fcc911a60de55b48990`; docs checkpoint SHA `5bb48f30f43e0d05ac257b7ee810f70bd6dbd5d3`.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #256 event-family coverage matrix lookup

- **Auditor (`src/irswitch/contracts/coverage_matrix.py`):** `audit_coverage_matrix` / `load_coverage_matrix` / `can_create_event_opportunity`. Re-exported from `contracts/__init__.py` as `irswitch.contracts.coverage_matrix`. Reads packaged `freeze-registry.json`, `beat-catalog.json`, `successor-graph.json`, `realization-pattern-cards.json`, `detector-catalog.json` and `coverage-matrix-replay-refs.json`. Catalog `definition` strings are never evaluated (`eval`/`exec`/`compile` forbidden).
- **Frozen proof:** 60 identifiers (52 speakable / 4 visual / 4 alias), 64 beats, 37 families, 6 policies, 36 channels, 256 EN cards, 50 successor edges, 11 stories, DAG SCC (28 nonterminal). Speakable rows resolve to beats; aliases and visual-only never create EventOpportunity. Replaced `STREAM_START` / `SESSION_INTRO_*` / `SESSION_WRAP` cannot be triggers. Stage/context/vehicle axes use normalized enums only.
- **Replay refs:** transition F01/F02/F03/F04/F22/F25; identity F17/F31/F43; expiry F08/F15/F24; counterfactual F09/F15/F33/F37. Pointers only — no NarrativeRuntime.
- **Review:** [fact-feature-registry.md](../../v2.0.0/fact-feature-registry.md) and [detector-catalog-freeze.md](../../v2.0.0/detector-catalog-freeze.md) match the packaged catalogs. `machine/` hashes were not rewritten. Behavior projection: [catalog-behavior.md](../../v2.0.0/catalog-behavior.md).
- **Exports / boundaries:** re-exported from `contracts/__init__.py`; **not** from `events/__init__.py`. Does not import NarrativeRuntime, overlay tape, commentary or events; not live-wired. Complements the StoryDefinition catalog loader (#257); does not load typed beats/stories itself.
- **Tests:** `tests/test_coverage_matrix.py` (**15**). First implementation SHA `b061ba2499a73d0a215ed2277ea6dd66a161211d`.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #257 StoryDefinition catalog loader lookup

- **Loader (`src/irswitch/contracts/catalog_loader.py`):** `load_narrative_catalog` / `apply_catalog_mutation` / `NarrativeCatalog` / `StoryDefinition` / `BeatDefinition` / `CatalogLoadResult` / `CatalogLoadFailure`. Re-exported from `contracts/__init__.py` as `irswitch.contracts.catalog_loader`. Reads packaged `freeze-registry.json`, `beat-catalog.json`, `successor-graph.json`, `detector-catalog.json`, `config-contract.json` plus schemas `beat-catalog.schema.json`, `successor-graph.schema.json`, `catalog-loader-contract.json` (byte-equal copies under `contracts/schemas/v2/`). Catalog `definition` strings are never evaluated (`eval`/`exec`/`compile` forbidden).
- **Fail-soft contract:** invalid catalog returns `outcome=commentary_disabled` + `CatalogLoadFailure` (`commentaryEnabled=false`, `mainLoopRaises=false`, `partialCatalogPublished=false`, `reason=catalog_invalid`, `runtimeStatus=disabled`). Never raises into the main loop.
- **Frozen load:** 64 beats, 11 stories, 50 edges, 37 families, 6 policies, 60 events, 5 lifecycle events, 3 detectors. Schema version `narrative-catalog/2`. Catalog hash = `canonical_sha256(beat_doc)`. Executes all 7 beat + 8 graph `x-irswitch-invariants` and all 12 `mandatoryChecks`.
- **Event routing:** `LAP_COMPLETE` → beat `timing.lap.completed`, stories `timing_attempt`+`single_result`, channel `race.timing.lap`. Aliases/visual (`BATTLE_LOST`, `BLE_LOST`) and legacy `STREAM_START` / `SESSION_INTRO_*` / `SESSION_WRAP` do not create routes. Same-beat authored fallback is forbidden (`same_beat_authored_fallback=False`). No sequence-graph v1 fallback (`sequence_graph_fallback=False`).
- **Detector IDs:** stay on the catalog (`battle_ahead_v1`, `battle_behind_v1`, `battle_two_front_v1`); beats have `detector_id=None`.
- **Review:** complements [#256 coverage matrix](#256-event-family-coverage-matrix-lookup). Behavior projection: [catalog-behavior.md](../../v2.0.0/catalog-behavior.md). `machine/` hashes were not rewritten.
- **Exports / boundaries:** re-exported from `contracts/__init__.py`; **not** from `events/__init__.py`. Does not import NarrativeRuntime, overlay tape, commentary or events; not live-wired.
- **Tests:** `tests/test_catalog_loader.py` (**29**: 6 packaged artifacts + 8 named + 15 invalid goldens). First implementation SHA `3fd54d21363d2bf971e6d60fdd1e841f5a1dc7eb`.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #258 lineage-aware EpisodeRegistry lookup

- **Registry (`events/episode_registry.py`):** `EpisodeRegistry`, `Episode`, `EpisodeIntent`, `EpisodeStep`, `EpisodeTransition`, `MaterialOrder`. Owns runtime episode instances independently of speech; opening/resolving works with empty `spokenBeatIds`. Schema `episode/2`. States: `candidate|active|suspended|resolved|invalidated`; dormant is absence.
- **Scope:** `stream|occurrence`. Stream-only `stream_lifecycle` (and optional stream `filler_single`) may omit occurrence/lineage; occurrence scope requires both (validated via `validate_occurrence_lineage`).
- **Semantic identity:** locates/updates one live instance (`material_revision`++). Distinct identities run concurrently. Exclusive group `battle` (`battle_ahead` / `battle_behind` / `battle_two_front`) with overlapping `correlationIds` suspends the other live instance (`target_changed`).
- **Reset:** `reset_occurrences` invalidates only episodes whose `occurrenceId` is in the affected set; other occurrences and stream-scoped episodes stay.
- **Transitions:** every transition carries `reason` + `source_refs`.
- **Capacity:** defaults `active_capacity=64`, `resolved_capacity=256` (match frozen public contract). Eviction order: stale/unpinned suspended (oldest), then candidate (oldest), then lowest `continuationPriority` active; ties `materialOrder` then `episodeId`. Terminal reason `capacity_evicted`. Pin kinds `reserved|building|committed|speaking`. If all current instances are pinned, new open returns `decision=episode_capacity_rejected` and does not create an episode (accepted facts/events stay recorded — registry never writes FactLedger). Resolved overflow drops oldest `(resolvedMonoMs, episodeId)` and latches `historyComplete=false`.
- **Definition IDs:** must be frozen StoryDefinition ids from #257 catalog (`load_narrative_catalog`).
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import narrative-actor, overlay tape or commentary; not live-wired. Complements #259 `EpisodeRetention`; does not implement NarrativeRuntime.
- **Tests:** `tests/test_episode_registry.py` (**13**). First implementation SHA `dc4ef4079d9cbcd2cb417ba7fb2cb4747d9e69f4`. Related regression: episode + catalog_loader + session_occurrence + fact_ledger **76** passed.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #259 resolved-episode retention lookup

- **Retention (`events/episode_retention.py`):** `EpisodeRetention`, `RetentionIntent`, `RetentionRecord`, `RetentionDecision`, `RetentionStep`. Schema `episode-retention/2`. Bounded resolved-outcome store; no prepared-speech queue, no BeatPlan / TtsUtterance storage.
- **Policy TTL/salience:** frozen catalog policy families — `critical` 45s/90, `result` 30s/78, `live_story` 10s/64, `transient` 6s/56, `context` 20s/46, `filler` 12s/24. `speakable_until_ms = resolvedMonoMs + ttlMs`; half-open validity `now < speakable_until`.
- **Self-contained families:** `critical` + `result` (pass/finish). Intermediate (`live_story`/`transient`) supersede same `(occurrenceId, definitionId, semanticIdentity)` and are `skipped` after speech complete (not narrated later).
- **`on_speech_complete`:** re-evaluates `expired_ttl` / `skipped` / remaining self-contained; selection order `(-salience, speakable_until_ms, episodeId)`. No prepared-speech queue.
- **Capacity:** default `resolved_capacity=256` (same frozen public contract as #258). Overflow drops oldest `(resolvedMonoMs, episodeId)`.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import narrative-actor, overlay tape or commentary; not live-wired. No eval/exec/compile. #260 fillers are implemented separately; does not implement #261 BeatPlan or NarrativeRuntime.
- **Tests:** `tests/test_episode_retention.py` (**9**). First implementation SHA `af72b73ddc36281be3e8b7088189738409ede659`. Related regression: episode_retention + episode_registry + catalog_loader + session_occurrence + fact_ledger **85** passed.
- **Still out of scope:** #261 BeatPlan, live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #260 long-silence lifecycle lookup

- **Clock (`events/silence_clock.py`):** `SilenceClock`, `SilenceImpulse`, `ClockStep`, `evaluate_filler`, `FillerContext`, `FillerFact`, `FillerOpportunity`. Default interval `LONG_SILENCE_MS=33_000` (`commentary.director.long_silence_s=33.0`, already frozen). One current generation; fire at `now >= deadline`; stale generation is a no-op.
- **Arm / rearm:** after lifecycle candidates, or at speech terminal / audience resume, arm `g+1` at `now + interval` when the audience window is open and no playback is accepted. Playback accepted cancels without credit; terminal/resume re-arm. Building/committed and race events do not move the origin. Changing the interval does not move an already armed deadline.
- **Audience window:** `runtime status=ready|degraded`, `commentary_enabled=true`, `narrative_run_active=true`, OBS `active`. OBS unknown/inactive **pauses** (no elapsed credit); resume rearms a full interval. Disable / stream end / shutdown cancel without credit.
- **Elapsed:** one-shot `LONG_SILENCE_ELAPSED` `{generation, deadlineMonoMs}`; if no playback is accepted, rearm exactly `now + interval` (no shorter retry). Busy lane `building|committed|speaking|stopping` selects no filler and still rearms.
- **Filler guards:** pre-session (no SessionRef) admits only stream-scope `filler.lobby` with fresh stream `context.track_identity`. Phase fillers need fresh `vehicle.phase` plus exactly one fresh `W_filler_phase` companion; garage/lobby/on_track need matching `broadcast.context` plus exactly one fresh `W_filler_off_track` or `W_quiet_track` fact. Empty allowlist, forecast weather, and invented race predicates (`position.passed`) fail `source_guard`. A live race opportunity returns `no_candidate` (director may pick silence). Race candidates replace an uncommitted filler without moving the silence origin. Story id `filler_single`.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import commentary or overlay; not live-wired. No BeatPlan / EventOpportunity queue / utterance emit. Does not implement #261 or #283, or activate NarrativeRuntime.
- **Tests:** `tests/test_silence_clock.py` (**14**). First implementation SHA `754f21e7a4ec54d3cc61726f4bf8f70854a6de50`. Related regression: silence_clock + episode_retention + episode_registry + catalog_loader + session_occurrence + fact_ledger **99** passed.
- **Still out of scope:** #261 BeatPlan, #283 opportunity TTL/arbitration, live EventManager/NarrativeRuntime wiring, V4 overlay tape.

`NarrativeRuntime`, live DetectorBank / DirectEdgeBank / LifecycleTriggerBank / ClosingDetector / PressureDetector / TwoFrontDetector / SilenceClock wiring, and V4 overlay tape remain out of scope until #284 and later issues.

## Index drift note

[docs/dokumentace/README.md](../README.md) mirrors the master lookup table. Rows that link to `domeny/*.md`, `architektura.md`, `stav.md`, or `mapa-souboru.md` **404 on this branch**. For v2 narrative modules, use this page and `docs/v2.0.0/` instead of grepping `src/` or inventing shipped domain pages.
