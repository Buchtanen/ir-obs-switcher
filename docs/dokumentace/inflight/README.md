# In-flight documentation — `codex/commentary-story-flow-spec`

**Status:** v2 narrative runtime Wave A–B (#235–#246) and Wave C [#247](https://github.com/Buchtanen/ir-obs-switcher/issues/247)–[#248](https://github.com/Buchtanen/ir-obs-switcher/issues/248) are closed on this branch; **not shipped on `master`**. [#249](https://github.com/Buchtanen/ir-obs-switcher/issues/249) predicate AST is implemented on this branch (not closed until diary + close-gate).

## Where to look on this branch

| Need | Authority on this branch | Not shipped here |
| --- | --- | --- |
| Issue index, waves, dependencies | [docs/v2.0.0/README.md](../../v2.0.0/README.md) | `domeny/commentary.md` as master truth |
| Resume identity, closing SHAs, scope boundaries | [docs/v2.0.0/implementation-handover.md](../../v2.0.0/implementation-handover.md) | Public CONFIG/API/README product contracts (unchanged for #239–#249) |
| DTO/tape/schema freeze | [docs/v2.0.0/schema-contracts.md](../../v2.0.0/schema-contracts.md), [machine/](../../v2.0.0/machine/README.md) | Rewriting `machine/` hashes |
| Master domain pages (`domeny/*.md`, `architektura.md`, `mapa-souboru.md`, `stav.md`) | See `master` — **absent on this branch by design** | Copying master pages as if v2 were shipped |

## Implementation lookup (#239–#249, branch-only)

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
- **Still out of scope:** DetectorBank / NarrativeRuntime / `gap.trend.confidence` / `gap.target_stable` live wiring.

### #249 predicate AST lookup

- **Compile (`contracts/predicate.py`):** `compile_detector_catalog` / `load_compiled_detector_catalog` turn packaged `detector-catalog.json` named atoms + frozen invariant strings into `all`/`any`/`not`/compare/`held_for` trees. `compile_predicate` also accepts structured nodes (`changed`, `changed_by`, `crossed`, `rising_edge`, `falling_edge`, `within`, `since`, `count`, `sequence`, `unknown`, `unusable`). Compile caps: `MAX_DEPTH=16`, `MAX_NODES=128`; evaluation cap `MAX_EVAL_STEPS=512`. Catalog `definition` / invariant prose is never executed (`eval`/`exec`/`compile` forbidden).
- **Atoms:** directional enter/clear/immediate/material IDs plus two-front atoms from `detector-catalog-freeze.md`. Unknown atom or invariant string fails catalog load. `unknownSatisfies` must be `false`. Undeclared feature/parameter or incompatible units fail compile.
- **Evaluate (`events/predicate_ast.py`):** `PredicateEvaluator` returns `PredicateResult` (`verdict` + reason tree; `satisfies` is false for unknown on enter/`held_for`). Missing/`quality=unknown` feature values are unknown; `feature_stale_or_unknown` is true on clear when the gap feature is missing or unusable.
- **Exports / boundaries:** compile/result DTOs re-exported from `contracts/__init__.py`; evaluator **not** exported from `events/__init__.py`. Does not import NarrativeRuntime, DetectorBank, overlay tape or commentary; not wired into the live loop.
- **Tests:** `tests/test_predicate_ast.py` (**14**). First implementation SHA `b24e3da0297b027a1d6b3399b2f8584fb70bbe4c`.
- **Still out of scope:** DetectorBank FSM (#250), StoryDefinition loader (#257), NarrativeRuntime activation.

`NarrativeRuntime`, live `DetectorBank` wiring, and V4 overlay tape remain out of scope until #284 and later issues.

## Index drift note

[docs/dokumentace/README.md](../README.md) mirrors the master lookup table. Rows that link to `domeny/*.md`, `architektura.md`, `stav.md`, or `mapa-souboru.md` **404 on this branch**. For v2 narrative modules, use this page and `docs/v2.0.0/` instead of grepping `src/` or inventing shipped domain pages.
