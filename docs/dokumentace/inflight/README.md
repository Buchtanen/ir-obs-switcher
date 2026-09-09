# In-flight documentation — `codex/commentary-story-flow-spec`

**Status:** v2 narrative runtime Wave A–B (#235–#246) and Wave C [#247](https://github.com/Buchtanen/ir-obs-switcher/issues/247)–[#250](https://github.com/Buchtanen/ir-obs-switcher/issues/250) are closed on this branch; **not shipped on `master`**. [#251](https://github.com/Buchtanen/ir-obs-switcher/issues/251) direct lap/sector edges are implemented on this branch (first SHA `5a61be3`).

## Where to look on this branch

| Need | Authority on this branch | Not shipped here |
| --- | --- | --- |
| Issue index, waves, dependencies | [docs/v2.0.0/README.md](../../v2.0.0/README.md) | `domeny/commentary.md` as master truth |
| Resume identity, closing SHAs, scope boundaries | [docs/v2.0.0/implementation-handover.md](../../v2.0.0/implementation-handover.md) | Public CONFIG/API/README product contracts (unchanged for #239–#251) |
| DTO/tape/schema freeze | [docs/v2.0.0/schema-contracts.md](../../v2.0.0/schema-contracts.md), [machine/](../../v2.0.0/machine/README.md) | Rewriting `machine/` hashes |
| Master domain pages (`domeny/*.md`, `architektura.md`, `mapa-souboru.md`, `stav.md`) | See `master` — **absent on this branch by design** | Copying master pages as if v2 were shipped |

## Implementation lookup (#239–#251, branch-only)

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
- **Still out of scope:** live DetectorBank wiring, StoryDefinition loader (#257), NarrativeRuntime activation.

### #250 DetectorBank lookup

- **FSM (`events/detector_bank.py`):** `reduce_lifecycle` matches frozen `reduce_directional` goldens (`inactive|candidate|active|clearing`). `DetectorBank` keys instances by `(detectorId, detectorVersion, streamEpoch, occurrenceId, orderedCorrelationKey)`, evaluates compiled `enter_signal` / `clear` / `immediate` / `material_update` trees, and owns confirm/clear/update holds. Unknown never satisfies enter; unknown/stale clear starts the clear hold. Duplicate or older `frameSequence` is an audited no-op.
- **Emissions:** detector `STARTED`/`UPDATED`/`ENDED` only. Ahead maps to existing V4 `HUNTING`, behind to `HUNTED`. `endedEvent` stays null — no `HUNTING_ENDED`. Material revisions compare to the last emitted net-closing/band and are rate-limited by `update_min_interval_s`. Close expires `battle.closing` as a recorded fact predicate; FactLedger is not called.
- **Scope:** directional catalog detectors only. Band projection (`reduce_band`) and two-front (`reduce_composite` / `BATTLE_FOR_POSITION`) stay #253–#255. `disable_for_run(..., required_capture_lost)` is the narrow capture-loss control; it does not import commentary.
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import NarrativeRuntime, overlay tape or commentary; not wired into the live loop.
- **Tests:** `tests/test_detector_bank.py` (**19**), including the seven directional goldens. First implementation SHA `e41ffb42f5e83236a4db58194dd4c5903fbc0899`; docs checkpoint SHA `0a44978d2468f30bb343100c8b8731bd9850fb9b`.
- **Still out of scope:** live EventManager/NarrativeRuntime wiring, CLOSING/UNDER_PRESSURE product detectors, two-front composite, V4 overlay tape.

### #251 direct lap/sector edges lookup

- **Bank (`events/direct_edges.py`):** `DirectEdgeBank` / `DirectEdgeSample` / `DirectEdgeIdentity`. `sourceClass=direct` (null `detectorObservationId`). Identity is `(kind, streamEpoch, occurrenceId, heroId, lap[, sectorId])`. Duplicate/older `sampleSequence` is an audited no-op. Restart uses a new occurrence so the same lap number is a new identity; a same-occurrence lap reset cannot reuse a prior key.
- **Eligibility:** lap edges (`LAP_COMPLETE` → `timing.lap_completed` / `race.timing.lap`) require `overlay_mode` in `PRACTICE|QUALIFYING|RACE`. Sector edges (`SECTOR_SPLIT` / `SECTOR_BEST`) require `PRACTICE|QUALIFYING` only. `GENERIC`, disconnected, missing occurrence, missing sector metadata, or invalid sector ids emit nothing. `session_finished` / `player_finished` is a completed race, not a lap edge.
- **Current emitters:** `events/lap.py` and `events/sector_split.py` stay on master wiring. This slice characterizes them and does not live-replace them. DetectorBank thresholds are not reused (`tuning.policy=none`).
- **Exports / boundaries:** **not** exported from `events/__init__.py`. Does not import DetectorBank, NarrativeRuntime, overlay tape or commentary; not wired into the live loop.
- **Tests:** `tests/test_direct_edges.py` (**13**). First implementation SHA `5a61be3aae3b8c8b3bac91c1361f6f7c53e10278`.
- **Still out of scope:** live EventManager wiring, stream/session lifecycle edges (#252), lap/sector family migration (#275), NarrativeRuntime.

`NarrativeRuntime`, live DetectorBank / DirectEdgeBank wiring, and V4 overlay tape remain out of scope until #284 and later issues.

## Index drift note

[docs/dokumentace/README.md](../README.md) mirrors the master lookup table. Rows that link to `domeny/*.md`, `architektura.md`, `stav.md`, or `mapa-souboru.md` **404 on this branch**. For v2 narrative modules, use this page and `docs/v2.0.0/` instead of grepping `src/` or inventing shipped domain pages.
