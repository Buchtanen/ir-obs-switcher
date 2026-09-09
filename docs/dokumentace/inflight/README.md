# In-flight documentation — `codex/commentary-story-flow-spec`

**Status:** v2 narrative runtime Wave A–B (#235–#246) and Wave C [#247](https://github.com/Buchtanen/ir-obs-switcher/issues/247)–[#256](https://github.com/Buchtanen/ir-obs-switcher/issues/256) remain implemented; Wave D [#257](https://github.com/Buchtanen/ir-obs-switcher/issues/257)–[#262](https://github.com/Buchtanen/ir-obs-switcher/issues/262) plus [#263](https://github.com/Buchtanen/ir-obs-switcher/issues/263) and [#283](https://github.com/Buchtanen/ir-obs-switcher/issues/283) are **closed** on this branch; [#264](https://github.com/Buchtanen/ir-obs-switcher/issues/264) is **closed**; [#265](https://github.com/Buchtanen/ir-obs-switcher/issues/265) is **closed**; [#266](https://github.com/Buchtanen/ir-obs-switcher/issues/266) is **closed**; [#267](https://github.com/Buchtanen/ir-obs-switcher/issues/267) is **closed**; [#268](https://github.com/Buchtanen/ir-obs-switcher/issues/268) is **closed**; **not shipped on `master`**. Next implementation package is [#269](https://github.com/Buchtanen/ir-obs-switcher/issues/269) (do not start unless a human says so).

## Where to look on this branch

| Need | Authority on this branch | Not shipped here |
| --- | --- | --- |
| Issue index, waves, dependencies | [docs/v2.0.0/README.md](../../v2.0.0/README.md) | `domeny/commentary.md` as master truth |
| Resume identity, closing SHAs, scope boundaries | [docs/v2.0.0/implementation-handover.md](../../v2.0.0/implementation-handover.md) | Public CONFIG/API/README product contracts (unchanged for #239–#268) |
| DTO/tape/schema freeze | [docs/v2.0.0/schema-contracts.md](../../v2.0.0/schema-contracts.md), [machine/](../../v2.0.0/machine/README.md) | Rewriting `machine/` hashes |
| Master domain pages (`domeny/*.md`, `architektura.md`, `mapa-souboru.md`, `stav.md`) | See `master` — **absent on this branch by design** | Copying master pages as if v2 were shipped |

## Implementation lookup (#239–#268, branch-only)

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
| #261 immutable BeatPlan / just-in-time planner | events | `src/irswitch/events/beat_plan.py` — [§ lookup](#261-immutable-beatplan-lookup) | `tests/test_beat_plan.py` (**14**) |
| #263 ExposureStore / base-2 fatigue | events | `src/irswitch/events/exposure_store.py` — [§ lookup](#263-exposure-store-lookup) | `tests/test_exposure_store.py` (**13**) |
| #283 expiring EventOpportunity queue | events | `src/irswitch/events/opportunity_queue.py` — [§ lookup](#283-expiring-event-opportunities-lookup) | `tests/test_opportunity_queue.py` (**15**) |
| #262 StoryDirector eligibility / scoring | events | `src/irswitch/events/story_director.py` — [§ lookup](#262-storydirector-eligibility-lookup) | `tests/test_story_director.py` (**11**) |
| #264 single in-flight speech lane | events | `src/irswitch/events/speech_lane.py` — [§ lookup](#264-speech-lane-lookup) | `tests/test_speech_lane.py` (**14**) |
| #265 freshness commit gate | events | `src/irswitch/events/freshness_commit.py` — [§ lookup](#265-freshness-commit-lookup) | `tests/test_freshness_commit.py` (**14**) |
| #266 EN-only RealizationCatalog | contracts | `src/irswitch/contracts/realization_catalog.py` — [§ lookup](#266-realization-catalog-lookup) | `tests/test_realization_catalog.py` (**13**) |
| #267 authored critical/lifecycle pack | contracts | `src/irswitch/contracts/authored_pack.py` — [§ lookup](#267-authored-pack-lookup) | `tests/test_authored_pack.py` (**11**) |
| #268 compiled PromptOptions / prompt profiles | events | `src/irswitch/events/prompt_compiler.py` — [§ lookup](#268-prompt-compiler-lookup) | `tests/test_prompt_compiler.py` (**12**) |

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
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import narrative-actor, overlay tape or commentary; not live-wired. No eval/exec/compile. #260 fillers are implemented separately; does not implement NarrativeRuntime.
- **Tests:** `tests/test_episode_retention.py` (**9**). First implementation SHA `af72b73ddc36281be3e8b7088189738409ede659`. Related regression: episode_retention + episode_registry + catalog_loader + session_occurrence + fact_ledger **85** passed.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #260 long-silence lifecycle lookup

- **Clock (`events/silence_clock.py`):** `SilenceClock`, `SilenceImpulse`, `ClockStep`, `evaluate_filler`, `FillerContext`, `FillerFact`, `FillerOpportunity`. Default interval `LONG_SILENCE_MS=33_000` (`commentary.director.long_silence_s=33.0`, already frozen). One current generation; fire at `now >= deadline`; stale generation is a no-op.
- **Arm / rearm:** after lifecycle candidates, or at speech terminal / audience resume, arm `g+1` at `now + interval` when the audience window is open and no playback is accepted. Playback accepted cancels without credit; terminal/resume re-arm. Building/committed and race events do not move the origin. Changing the interval does not move an already armed deadline.
- **Audience window:** `runtime status=ready|degraded`, `commentary_enabled=true`, `narrative_run_active=true`, OBS `active`. OBS unknown/inactive **pauses** (no elapsed credit); resume rearms a full interval. Disable / stream end / shutdown cancel without credit.
- **Elapsed:** one-shot `LONG_SILENCE_ELAPSED` `{generation, deadlineMonoMs}`; if no playback is accepted, rearm exactly `now + interval` (no shorter retry). Busy lane `building|committed|speaking|stopping` selects no filler and still rearms.
- **Filler guards:** pre-session (no SessionRef) admits only stream-scope `filler.lobby` with fresh stream `context.track_identity`. Phase fillers need fresh `vehicle.phase` plus exactly one fresh `W_filler_phase` companion; garage/lobby/on_track need matching `broadcast.context` plus exactly one fresh `W_filler_off_track` or `W_quiet_track` fact. Empty allowlist, forecast weather, and invented race predicates (`position.passed`) fail `source_guard`. A live race opportunity returns `no_candidate` (director may pick silence). Race candidates replace an uncommitted filler without moving the silence origin. Story id `filler_single`.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import commentary or overlay; not live-wired. No EventOpportunity queue / utterance emit. Does not activate NarrativeRuntime.
- **Tests:** `tests/test_silence_clock.py` (**14**). First implementation SHA `754f21e7a4ec54d3cc61726f4bf8f70854a6de50`. Related regression: silence_clock + episode_retention + episode_registry + catalog_loader + session_occurrence + fact_ledger **99** passed.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #261 immutable BeatPlan lookup

- **Planner (`events/beat_plan.py`):** `BeatPlanner`, `BeatPlan`, `PlanIntent`, `PlanStep`, `BoundClaim`, `PromptOptions`, `FunnelLink`, `CandidateOrder`, `tight_prompt_options`. Schemas `beat-plan/2` + `prompt-options/2`. `BeatPlanner.plan(intent, lane=..., planning_cycle_id=...)` → `PlanStep(reason, plan, opportunity_consumed=False)`.
- **Reasons:** `planned` / `lane_busy` / `source_guard_failed` / `future_successor_forbidden` / `ledger_dump_forbidden` / `consecutive_cap` / `not_self_contained` / `deduped` / `planning_cycle_exhausted`. Busy lanes `building|committed|speaking|stopping` → no plan.
- **Dedup:** key `(beat_id, episode_id, episode_revision)` merges source refs. Same `planningCycleId`: ordinal `1|2` then `planning_cycle_exhausted`. `candidateOrder={reducerSequence,sourceOrdinal}` is the stable age/tie-break authority.
- **Expiry:** half-open `plannedMonoMs <= now < expiresMonoMs`. Null occurrence/lineage only for `stream.started` and stream-scope `filler.lobby`.
- **PromptOptions baseline:** `tight_prompt_options` — freedom `tight`, patternChoice `fixed`, optionalClaimLimit 0, maxSentences 1, temperature 0.15, topP 0.75; seed from `deterministic_planning_seed(PlanningSeedMaterial)`. First production catalog `promotedMaxFreedom=tight` — no widen documented.
- **Role map:** catalog `result`→`outcome`, `single`→`filler`. Self-contained after speech: closing / critical / catalog policy `critical|result`. Consecutive cap: min(public `GLOBAL_CONSECUTIVE_CAP=3`, story `max_consecutive_non_closing_beats`); closing/critical spared.
- **Guards:** ledger dump forbidden — `selected_fact_ids` must equal the claim-fact union (no extra ledger dump). Future successor plans forbidden (`future_beat_ids` nonempty → reject). Every selected claim has fact/evidence refs; empty `fact_ids` → `source_guard_failed`. G0 forbidden claim types attached on the plan. Language constant `en`.
- **Replay fixtures:** `tests/fixtures/beat_plan/{transition,counterfactual_identity,expiry}.json`.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import `irswitch.commentary`, `irswitch.overlay`, or NarrativeRuntime; not live-wired. No eval/exec/compile. Does not consume the source opportunity; does not emit utterance. Does not implement RealizationBundle.
- **Tests:** `tests/test_beat_plan.py` (**14**). First implementation SHA `fef616aeb34fb35631c327438a99ad6b41c7170a`. Related regression: beat_plan + silence_clock + episode_retention + episode_registry + catalog_loader + session_occurrence + fact_ledger + contract_primitives **175** passed.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #263 exposure-store lookup

- **Store (`events/exposure_store.py`):** `ExposureStore`, `ExposureIntent`, `SpokenExposure`, `FatigueView`, `ChannelPressureView`, `CadenceAudit`, `ExposureStep`, `EmbeddingAdapter`, `half_life_decay`, `content_tokens`, `lexical_tail`, `jaccard`. Schema `exposure-view/2`. Decay `0.5 ** (age/half_life)` = `2^(-(t-spoken_at)/half_life)`; rejects `exp(-age/half_life)`. No `eval`/`exec`/`compile`/`math.exp`.
- **Record gate:** only `phase=speaking` + `source_kind=narrative`; planned/rejected/stale/building/committed/manual add no fatigue. Weight 1.0 at PLAYBACK_ACCEPTED / SPEAKING. Semantic half-life 90_000 ms; pattern 180_000 ms (F23 goldens from `docs/v2.0.0/machine/vertical-slice-fixtures.json`).
- **Channel pressure:** `6 * min(3, Σ decay)` on accepted exposures of that `tape_channel`. `event_penalty = policy.penalty_coefficient * channel_pressure`. `cadence_half_life = max(global_min_interval 4s, numeric profile cadence)`; null cadence uses TTL; filler uses `LONG_SILENCE_MS=33_000` not TTL.
- **Lexical:** EN-stopword Jaccard on content tokens; lexical-tail MVP = last 4 content tokens. Embedding adapter optional; `embedding_is_gate` always False. Family/role/filler histories are cadence/guard audit only (`cadence_audit`), not score terms.
- **Capacity:** default 128 (`commentary.director.decision_capacity`, already frozen); evict oldest `(acceptedMonoMs, utteranceId)`; stream reset clears.
- **Replay fixtures:** `tests/fixtures/exposure_store/{transition,counterfactual_identity,expiry}.json`.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import commentary, overlay, or NarrativeRuntime; not live-wired. One-way read of immutable `ChannelPressureView` from `ExposureStore`.
- **Tests:** `tests/test_exposure_store.py` (**13**). First implementation SHA `8b610e1848f7b8ac17e6844664bb72d47b8d8c4c`. Related regression: exposure_store + beat_plan + silence_clock + episode_retention + episode_registry + catalog_loader + session_occurrence + fact_ledger + contract_primitives **188** passed.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #283 expiring event opportunities lookup

- **Queue (`events/opportunity_queue.py`):** `OpportunityQueue`, `EventOpportunity`, `OpportunityIntent`, `ArbitrationContext`, `ArbitrationDecision`, `SelectedCandidate`, `EpisodeBeatRef`, `OpportunityStep`, `ChannelCounters`. Schema `event-opportunity/2`. Immutable `EventOpportunity`: identity + snapshot TTL/priority/urgency/penalty, one `tape_channel`, `candidateOrder`, no text/prompt/BeatPlan.
- **TTL / validity:** half-open `createdMonoMs <= now < expiresMonoMs`. Capacity default **128** (`commentary.director.opportunity_capacity`, already frozen). Overflow evicts oldest pending by `candidateOrder`; fail-soft `queue_overflow` when no pending slot. `updates`/`resolves` supersede same episode+correlation at `<= materialRevision` (`superseded_revision`).
- **Consume / reserve:** consume only on `SPEECH_STARTED` (`consumed_playback_accepted`); `reject_attempt` releases reservation (failed beat ≠ consume). Terminal reasons: `consumed_playback_accepted` / `expired_ttl` / `superseded_revision` / `invalidated_*` / `evicted_capacity`.
- **Relations:** `opens|updates|resolves|conflicts|independent` → frozen director IDs (`opens_episode`, `updates_active_episode`, …). Routing uses `can_create_event_opportunity`; aliases/visual never admit.
- **Arbitration:** natural successors from last spoken beat + catalog edges; score `58 + 6` same-story + edge bonus + `6` material − `penaltyCoefficient * channel_pressure`. Event score: `basePriority − penaltyCoefficient * channel_pressure`. Switch: higher urgency always; equal/lower needs inclusive `switch_margin` **8**. No event/successor → `SILENCE` (`no_candidate`); filler only on silence impulse. Selection threshold **35**.
- **Cadence:** six policy profiles + scopes from [event-beat-disposition.md](../../v2.0.0/event-beat-disposition.md) (`semantic_revision`, `semantic`, `episode`, `tape_channel`, `silence_impulse`). Global min interval **4 s**. Expiry cancels reserved preaccept work; never starts a fallback impulse.
- **Counters:** per-`tape_channel` kick/queued/selected/consumed/expired/superseded/spoken/evicted.
- **Replay fixtures:** `tests/fixtures/opportunity_queue/{transition,counterfactual_identity,expiry}.json`.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Reads immutable `ChannelPressureView` from `ExposureStore` one-way (no import cycle). Does not import commentary, overlay, or NarrativeRuntime; not live-wired.
- **Tests:** `tests/test_opportunity_queue.py` (**15**). First implementation SHA `3d29a82691023d4e57d8a27982accc02e9d634ac`. Related regression: opportunity_queue + exposure_store + beat_plan + silence_clock + episode_retention + episode_registry + catalog_loader + session_occurrence + fact_ledger + contract_primitives **203** passed.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #262 StoryDirector eligibility lookup

- **Director (`events/story_director.py`):** `StoryDirector`, `DirectorCandidate`, `DirectorWorld`, `EligibilityGates`, `FatigueTerms`, `ScoreTerms`, `CandidateRecord`, `DirectorDecision`, `score_terms`, `effective_score`. Schema `director-decision/2` (internal decision; full tape prompt/speech/commit is later wiring).
- **Hard gates before score:** conjunction from spec §23.3 (`phase_allowed` … `audience_allowed`) plus `source_guard`, half-open snapshot window `createdMonoMs <= now < expiresMonoMs`, consecutive non-closing successor cap `min(3, story_consecutive_cap)`, and `(beat_id, episode_revision)` attempt suppression. Score cannot override an invalid fact or lineage.
- **Scores (§9.2):** named terms only — continuity +6, preferred +6 / closure edge +8, unspoken outcome +12, material 0/3/6/10, filler silence 12 (+ up to +8), semantic `8×min(3,F)`, pattern `5×min(2,F)`, lexical `8×Jaccard`, staleness `10×clamp(age/TTL,0,1)`, replacement `8+8×clamp(elapsed/timeout,0,1)` on building replace only. EventScore = Score − `penalty_coefficient × channel_pressure`. ContinuationScore uses `continuation_base` (live_story 58). EffectiveScore: event → EventScore; successor → ContinuationScore; else Score. No family/role/filler hidden terms. V4 `wire_priority` is stored and unused.
- **Select (§23.3 H-then-M):** `P` = best focused continuation (successor or event `updates`/`resolves`); `H` = higher urgency; `M` = urgency ≤ P and score ≥ P + inclusive `switch_margin=8`. Filler only when no story choice. Below `selection_threshold=35` → SILENCE (`below_threshold`). Stable tail `(candidateOrder, episodeId, beatId)`.
- **Building replace:** only `impulse=accepted_event` + `from_accepted_event` after `replacement_cost`; higher urgency or score ≥ incumbent + margin. Successor/filler/timer cannot replace (`incumbent_held`). Winning replace closes the old cycle as `replaced_precommit` and starts attempt 1 of a new cycle.
- **Planning cycle:** at most two distinct BeatPlans per impulse. Attempt 2 only after `note_failure` of a different beat. Second failure → `planning_cycle_exhausted` + SILENCE.
- **Frozen knobs (already public):** `selection_threshold=35`, `switch_margin=8`, `max_consecutive_story_beats=3`, `decision_capacity=128`, `long_silence_s=33`.
- **Replay fixtures:** `tests/fixtures/story_director/{transition,counterfactual_identity,expiry}.json`.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Composes #283 snapshots and #263 `FatigueTerms`; does not reimplement queue admit/TTL. Does not import commentary or overlay packages; not live-wired. No eval/exec/compile/`math.exp`. Does not implement RealizationBundle.
- **Tests:** `tests/test_story_director.py` (**11**). First implementation SHA `0aca193e4ebef2aa3defdb79c638129549a00699`. Related regression: story_director + opportunity_queue + exposure_store + beat_plan + silence_clock + episode_retention + episode_registry + catalog_loader + session_occurrence + fact_ledger + contract_primitives **214** passed.
- **Docs impact:** branch-only `inflight/` + `docs/v2.0.0/` (`README`, `catalog-behavior`, `event-beat-disposition`, `implementation-handover`, `jak-cist`); no public CONFIG/API/README change; `machine/` hashes unchanged. First SHA `0aca193`; docs checkpoint `fdd75df`; close `0b4d098`; feat CI [34340873454](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34340873454) green.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #264 speech-lane lookup

- **Lane (`events/speech_lane.py`):** `SpeechLane`, `SpeechIntent`, `TtsUtterance`, `TtsCallback`, `LaneStep`, `resolve_backend`. Schemas `tts-utterance/2` + `tts-callback/2`. States `idle|building|committed|speaking|stopping`. Busy `try_start` is `lane_busy` and never stores a prepared waiter (`pending_count=0`).
- **Admission:** narrative `idle→building` then explicit `commit` → `committed`. Manual skips building (`idle→committed`) and creates no opportunity/exposure. `auto` backend resolves once per generation in SAPI→eSpeak order; SuperTonic is explicit-only. Pending/failed/quarantined generation rejects new admission; in-flight utterances stay snapshotted.
- **Accept / consume:** `acknowledge` posts `PLAYBACK_ACCEPTED` mapped to public `SPEECH_STARTED` only at the frozen adapter boundary (SAPI async Speak stream / `waveOutWrite`, eSpeak owned spawn+probe, SuperTonic play-accepted). Synthesis/duck/worker entry do not consume. Consume `EventOpportunity` via `consume_speech_started` exactly once. Pre-accept `failed` releases; post-accept failure/interrupt keeps consumed.
- **Non-preempt:** race events on `committed|speaking` are `race_ignored`. Allowed cancel: stream/occurrence/run reset, commentary disable, truth invalidation, shutdown. Disable/reset cancel narrative only; shutdown cancels both; disable does not cancel manual.
- **Watchdogs:** `start_timeout_s=5` in committed; `stop_timeout_s=1` after cancel; playback uses `max_utterance_s=14`. Stop timeout quarantines that backend generation; restore only from `ready` health with a strictly newer generation.
- **Manual latch:** process-local `pending|actor_claimed|caller_abandoned`. Abandoned request cannot later speak. Timeout constant `MANUAL_LATCH_TIMEOUT_MS=1000`.
- **Replay fixtures:** `tests/fixtures/speech_lane/{transition,counterfactual_identity,expiry}.json`.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Optional one-way `OpportunityQueue` for reserve/consume/release. Does not import commentary or overlay packages; not live-wired. No eval/exec/compile. No live SAPI/eSpeak/SuperTonic process. Does not implement RealizationBundle.
- **Tests:** `tests/test_speech_lane.py` (**14**). First implementation SHA `330fd45188b17aad7cd4e30856ac1b309ee509f1`. Related regression **228** passed.
- **Docs impact:** branch-only `inflight/` + `docs/v2.0.0/` (`README`, `catalog-behavior`, `event-beat-disposition`, `implementation-handover`, `jak-cist`); no public CONFIG/API/README change (TTS knobs already frozen); `machine/` hashes unchanged. First SHA `330fd45`; docs checkpoint `2a90b81`; close `9d40800`; pin `3b66f0f`; handover audit `30824ae`; feat CI [34342772096](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34342772096) green.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #265 freshness-commit lookup

- **Gate (`events/freshness_commit.py`):** `FreshnessGate`, `CommitToken`, `CommitWorld`, `BoundFactCopy`, `CommitStep`. Schema `commit-token/2`. Verdicts `current|freshness_stale|invalidated|not_reached`.
- **Token:** immutable snapshot of plan/episode/occurrence/lineage/target plus frozen selected-fact copies and optional reservation. Newer FactView revisions may pass when selected copies stay canonical-equal and current.
- **Fail closed:** old lineage / changed target / dead episode / critical conflict → `invalidated`. Missing, superseded, changed, expired facts, or invalid/expired/superseded reservation → `freshness_stale`. Wrong lane → `not_reached` (no suppress, no release).
- **Effects:** failure suppresses `(beat_id, episode_revision)` so the same revision cannot retry; optional `OpportunityQueue.reject_attempt` releases the reservation. `rebuilt_surfaces` is always false; newer G2 never rebuilds the 1.4-second surfaces.
- **Replay fixtures:** `tests/fixtures/freshness_commit/{transition,counterfactual_identity,expiry}.json`.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Optional one-way queue release. Does not import commentary or overlay packages; not live-wired. No eval/exec/compile. Does not implement RealizationBundle or SemanticVerifier.
- **Tests:** `tests/test_freshness_commit.py` (**14**). First implementation SHA `63674e33638b59d7fb2db897b8be09b59a1cd794`. Related regression **242** passed.
- **Docs impact:** branch-only `inflight/` + `docs/v2.0.0/` (`README`, `catalog-behavior`, `event-beat-disposition`, `implementation-handover`, `jak-cist`); no public CONFIG/API/README change; `machine/` hashes unchanged. First SHA `63674e3`; docs checkpoint `7bb4fce`; close `0029a5b`; pin `3ba61ea`; feat CI [34344295746](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34344295746) green.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, V4 overlay tape. #266 RealizationCatalog is implemented separately.

### #266 realization-catalog lookup

- **Catalog (`src/irswitch/contracts/realization_catalog.py`):** `load_realization_catalog`, `inventory_legacy_variants`, `migrate_legacy_graph`, `RealizationCatalog`, `PatternCard`, `MigrationClassifier`, `LegacyVariant`, `Classification`, `MigrationReport`. Schema `realization-catalog/2`. Re-exported from `contracts/__init__.py` as `irswitch.contracts.realization_catalog`.
- **Frozen cards:** composes `#256` `audit_coverage_matrix` and `#257` `load_narrative_catalog`. 64 beats, 37 families, **256** enabled EN `tight` cards (4 per beat). `pattern_count` and `beat_count` are separate reported fields and are never conflated. Catalog hash = `canonical_sha256` of packaged `realization-pattern-cards.json`. Each card annotates required claims, `forbiddenAddition`, and `globalForbiddenClaimTypes` from the beat catalog. Balanced/loose stay disabled.
- **Classifier:** reads raw sequence-graph JSON (no commentary package import). Inventories **2,128 EN** and **2,128 CS** variants with source provenance `legacy:{nodeId}:{locale}:{bucket}:{ordinal}`. Dispositions `audited_pattern|authored_line|style_fragment|reject|cs_excluded` are **proposed** (`accepted=False`) until `accept()` or an explicit accept-set. CS is `cs_excluded` and cannot enter v2 routing. Exact card-pattern text → `audited_pattern`; unsafe legacy (question, first person, emotion, multi-sentence) → `reject`. `v2_reachable` only for accepted EN `audited_pattern`/`authored_line` with mapped beats.
- **Fixture:** `tests/fixtures/realization_catalog/legacy_graph.json`.
- **Exports / boundaries:** re-exported from `contracts/__init__.py`; **not** from `events/__init__.py`. Does not import NarrativeRuntime, overlay, commentary, or events; not live-wired. No `eval`/`exec`/`compile`. The #267 authored pack consumes a frozen bundle; this catalog does not compile live surfaces.
- **Tests:** `tests/test_realization_catalog.py` (**13**). First implementation SHA `10e5b70cff8f8a2d738c30b0d40ebd79798d9b97`. Related regression **270** passed.
- **Docs impact:** branch-only `inflight/` + `docs/v2.0.0/` (`README`, `catalog-behavior`, `event-beat-disposition`, `implementation-handover`, `jak-cist`); no public CONFIG/API/README change; `machine/` hashes unchanged. First SHA `10e5b70`; docs checkpoint `8df6da4`; index follow-up `6892ac6`; close `371f1ed`; pin `fd8a04b`; feat CI [34346027549](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34346027549) green.
- **Still out of scope:** live RealizationBundle compiler from current facts/roster, live EventManager/NarrativeRuntime wiring, V4 overlay tape. #267 authored pack is implemented separately.

### #267 authored-pack lookup

- **Pack (`src/irswitch/contracts/authored_pack.py`):** `load_authored_pack`, `authored_bundle`, `render_surface_forms`, `AuthoredPack`, `AuthoredLine`, `AuthoredRealizer`, `AuthoredStep`, `RealizationBundle`, `SurfaceLexicon`. Schema `authored-pack/2`. Bundle schema `realization-bundle/2`. Re-exported from `contracts/__init__.py` as `irswitch.contracts.authored_pack`.
- **Selection:** every beat whose catalog `realization.backend == "authored"` (33 critical/result/lifecycle beats) and that beat's four enabled EN tight cards (**132** lines). Does not re-derive the authored rule. `pack.beat_ids` order matches the narrative catalog.
- **Realizer:** consumes only a frozen `realization-bundle/2`. `authored_bundle(...)` is a pure constructor for tests/fixtures — it does not compile surfaces from a live ledger, roster or config. `used_live_view` / `used_roster` / `used_config` stay false. Authored mode is chosen before generation; `fallback=True` is `authored_fallback_forbidden`. Qwen backend is `authored_backend_required`. Timeout/cancel fail closed. Stale hash, leftover slots, non-en, missing subject/claim → `realization_input_invalid`. Unknown Qwen beat → `unknown_authored_beat`. Cause/color/prediction tokens → `forbidden_claim`. TTS `max_chars` → `realization_output_oversize`.
- **Surface lexicon:** `render_surface_forms` is the shared finite EN number/unit/ordinal/band helper. Spoken numbers come from the bundle lexicon, never live telemetry.
- **Anti-repeat:** among the four cards for the beat, unused first; requested `pattern_id` preferred when unused; if all spoken, reuse the requested card. Does not invent a fifth line.
- **Fixtures:** `tests/fixtures/authored_pack/{transition,counterfactual_identity,expiry}.json`.
- **Exports / boundaries:** re-exported from `contracts/__init__.py`; **not** from `events/__init__.py`. Does not import NarrativeRuntime, overlay or events; not live-wired. No `eval`/`exec`/`compile`. Does not implement the live RealizationBundle compiler from current facts/roster, Qwen transport (#269), or SemanticVerifier (#270). PromptOptions compilation is #268.
- **Tests:** `tests/test_authored_pack.py` (**11**). First implementation SHA `6886d83b7a4093156a3d80604f035f297d57faed`. Related regression **281** passed.
- **Docs impact:** branch-only `inflight/` + `docs/v2.0.0/` (`README`, `catalog-behavior`, `event-beat-disposition`, `implementation-handover`, `jak-cist`); no public CONFIG/API/README change; `machine/` hashes unchanged. First SHA `6886d83`; docs checkpoint `815ef46`; docs-keeper audit `a31840f`; close `f326cb0`; pin `ef51557`; feat CI [34347147521](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34347147521) green.
- **Still out of scope:** live RealizationBundle compiler from current facts/roster, #269 Qwen transport, #270 SemanticVerifier, live EventManager/NarrativeRuntime wiring, V4 overlay tape.

### #268 prompt-compiler lookup

- **Compiler (`src/irswitch/events/prompt_compiler.py`):** `prompt_options_for`, `PromptCompiler.realize`, `PromptWorld`, `CompiledPrompt`, `PromptStep`. Reuses `#261` `PromptOptions` (`prompt-options/2`) from `events/beat_plan.py` — does not duplicate the type. Compiled prompt schema `compiled-prompt/2`. Lives in `events/` because contracts must not import `irswitch.events`. **Not** exported from `events/__init__.py`; **not** re-exported from `contracts/__init__.py`.
- **Closed tuples (`PROFILES`):** `tight` = `(tight, fixed, 0, false, 1, 0.15, 0.75)`; `balanced` = `(balanced, family_pool, 1, false, 1, 0.35, 0.85)`; `loose` = `(loose, family_pool, 2, true, 2, 0.55, 0.90)`. Fields are not freely combinable.
- **Clamp:** least permissive of `operator_max_profile` (`commentary.llm.max_profile`), BeatDefinition `maxFreedom`, family `promotedMaxFreedom`, family `preferredFreedom`. Further cap to **tight** when policy is `critical`, mapped role is `outcome|transition`, `history_complete=False`, or `min_selected_fact_confidence < 0.90`. Default `enabled_profiles={"tight"}` hard-disables balanced/loose for the first production slice. `widen_for_repetition` / `widen_for_failure` never widen (force tight). Family-pool with fewer than two enabled cards is `realization_input_invalid` (not silently converted to fixed).
- **Prompt text:** `realize()` compiles only the controlled-EN SurfaceLexicon and family grammar. Tight is one sentence. Contract `qwen-surface-en-tight/1` is legal only for tight. System text order: literal BASE block + `FAMILY GRAMMAR` + canonical family JSON + `PATTERN CARD` + one card + OUTPUT LIMITS. Family grammar is built from packaged `beat-catalog.json` `realizationFamilies` (does not load `docs/v2.0.0/machine/realization-contract.json`). userText is `canonical_json` of a frozen DATA projection. Hashes via `canonical_sha256`; `promptId` = `prompt:` + first 32 hex of promptHash. Byte limits: system 12288, user 20480, sum 32768 → `realization_input_invalid`.
- **Seed:** canonical JSON plus SHA-256 first-eight-byte big-endian via existing `deterministic_planning_seed`. Frozen F33 material `{streamEpoch:3, opportunityId:"opp:401", episodeId:"battle-ahead:3:17:22:4", episodeRevision:4, beatId:"battle.approach", cycleAttemptOrdinal:1}` → seed `16041955996680716084`.
- **Realize vs options:** `prompt_options_for` may return a wider closed tuple when overrides allow. `realize()` of the prompt text fails `profile_not_promoted` when realized freedom is not tight (no reviewed contract version for balanced/loose). Method is `realize`, not `compile` — product source must not contain the `compile(` substring (eval/exec/compile ban).
- **Flags:** `used_live_view` / `used_roster` / `used_config` always False. Timeout/cancel fail closed. Stale `expected_catalog_hash` → `realization_input_invalid`. Does not open a Qwen socket.
- **Fixtures:** `tests/fixtures/prompt_compiler/{transition,counterfactual_identity,expiry}.json`.
- **Exports / boundaries:** not exported from `events/__init__.py`; not re-exported from `contracts/__init__.py`. Does not import NarrativeRuntime, overlay, commentary, or `FactView`; not live-wired. No `eval`/`exec`/`compile`. Does not implement Qwen transport (#269) or SemanticVerifier (#270).
- **Tests:** `tests/test_prompt_compiler.py` (**12**). First implementation SHA `a3bab698e2f2732afb6d96e69e1637f2d733bd04`. Related regression **293** passed.
- **Docs impact:** branch-only `inflight/` + `docs/v2.0.0/` (`README`, `catalog-behavior`, `event-beat-disposition`, `implementation-handover`, `jak-cist`); no public CONFIG/API/README change; `machine/` hashes unchanged. First SHA `a3bab69`; docs checkpoint `f4a3cf2`; docs-keeper audit `ccaadbc`; close `633c745`; pin `60ad695`; feat CI [34349254777](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34349254777) green.
- **Still out of scope:** #269 Qwen transport / RealizationRequest / SSE / HTTP, #270 SemanticVerifier, live EventManager/NarrativeRuntime wiring, V4 overlay tape.

`NarrativeRuntime`, live DetectorBank / DirectEdgeBank / LifecycleTriggerBank / ClosingDetector / PressureDetector / TwoFrontDetector / SilenceClock / BeatPlanner / ExposureStore / OpportunityQueue / StoryDirector / SpeechLane / FreshnessGate / RealizationCatalog / AuthoredRealizer / PromptCompiler wiring, and V4 overlay tape remain out of scope until #284 and later issues.

## Index drift note

[docs/dokumentace/README.md](../README.md) mirrors the master lookup table. Rows that link to `domeny/*.md`, `architektura.md`, `stav.md`, or `mapa-souboru.md` **404 on this branch**. For v2 narrative modules, use this page and `docs/v2.0.0/` instead of grepping `src/` or inventing shipped domain pages.
