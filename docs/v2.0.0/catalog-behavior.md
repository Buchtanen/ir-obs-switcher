# v2 catalog behavior (implementation projection)

**Status:** generated from the packaged catalogs by [#256](https://github.com/Buchtanen/ir-obs-switcher/issues/256); typed loader by [#257](https://github.com/Buchtanen/ir-obs-switcher/issues/257); lineage-aware EpisodeRegistry by [#258](https://github.com/Buchtanen/ir-obs-switcher/issues/258); resolved-episode retention by [#259](https://github.com/Buchtanen/ir-obs-switcher/issues/259) (closed); long-silence clock by [#260](https://github.com/Buchtanen/ir-obs-switcher/issues/260) (closed); immutable BeatPlan by [#261](https://github.com/Buchtanen/ir-obs-switcher/issues/261) (closed); ExposureStore by [#263](https://github.com/Buchtanen/ir-obs-switcher/issues/263) (closed); EventOpportunity queue by [#283](https://github.com/Buchtanen/ir-obs-switcher/issues/283) (closed); StoryDirector by [#262](https://github.com/Buchtanen/ir-obs-switcher/issues/262) (implemented; close pending); branch-only, not shipped to `master`.
**Auditor:** `irswitch.contracts.coverage_matrix.audit_coverage_matrix`
**Loader:** `irswitch.contracts.catalog_loader.load_narrative_catalog`
**Registry:** `irswitch.events.episode_registry.EpisodeRegistry`
**Retention:** `irswitch.events.episode_retention.EpisodeRetention`
**Silence:** `irswitch.events.silence_clock.SilenceClock`
**Planner:** `irswitch.events.beat_plan.BeatPlanner`
**Exposure:** `irswitch.events.exposure_store.ExposureStore`
**Opportunity:** `irswitch.events.opportunity_queue.OpportunityQueue`
**Director:** `irswitch.events.story_director.StoryDirector`
**Tests:** `tests/test_catalog_loader.py` (**29**) + `tests/test_coverage_matrix.py` (**15**) + `tests/test_episode_registry.py` (**13**) + `tests/test_episode_retention.py` (**9**) + `tests/test_silence_clock.py` (**14**) + `tests/test_beat_plan.py` (**14**) + `tests/test_exposure_store.py` (**13**) + `tests/test_opportunity_queue.py` (**15**) + `tests/test_story_director.py` (**11**)

This page is the implementation-time behavior contract for the frozen event-family matrix. Human design prose stays in [event-beat-disposition.md](event-beat-disposition.md), [fact-feature-registry.md](fact-feature-registry.md) and [detector-catalog-freeze.md](detector-catalog-freeze.md). Machine hashes under `machine/` were reviewed and left unchanged.

## Frozen counts

| Item | Count |
| --- | ---: |
| Current identifiers | 60 |
| Speakable | 52 |
| Visual / operator-only | 4 |
| Compatibility alias | 4 |
| BeatDefinitions | 64 |
| Realization families | 37 |
| Policy profiles | 6 |
| `tape_channel` values | 36 |
| Enabled EN pattern cards | 256 (4 per beat) |
| Successor edges | 50 |
| Story routes | 11 |
| Fact predicates | 57 |
| Features | 21 |
| Detectors | 3 (all `experimental`, `tuning.policy=required`) |

Released detectors must not keep `tuning.required`. The three current detectors remain experimental calibration entries.

## EventOpportunity rule

- `eventClass=speakable` may later create an EventOpportunity.
- `visual_only` and `compatibility_alias` never create speech. Extra beat pointers on those rows are ignored.
- `UNDER_PRESSURE` is not a current identifier.
- Replaced lifecycle identifiers (`STREAM_START`, `SESSION_INTRO_*`, `SESSION_WRAP`) cannot appear as v2 beat triggers. Canonical kinds are `STREAM_STARTED`, `SESSION_STARTED` and `SESSION_ENDED`.

## Beat resolution

Every BeatDefinition resolves all of:

- at least one ordered story route from the 11-route successor graph
- one realization family and one of the six policy profiles
- one registered `tape_channel`
- enabled freedom `tight` only (not above the family `promotedMaxFreedom`)
- at least four enabled audited EN pattern cards

Stage / broadcast / vehicle axes use the normalized enums only. Raw OBS scene names are rejected.

## Successor graph and SCC

`successor-graph.json` is a 64-node / 50-edge DAG (`strongComponentCount=64`, no cyclic component). 28 nonterminal beats expand only through explicit guarded edges; terminals use `no_implicit_continuation`. Every story carries a cadence floor and consecutive-cap; selection keeps `materialRevisionBonus=6`.

## Replay fixture references

Packaged `coverage-matrix-replay-refs.json` points at existing F01–F44 fixtures. It does not add a NarrativeRuntime:

| Claim family | Fixtures |
| --- | --- |
| transition | F01, F02, F03, F04, F22, F25 |
| identity | F17, F31, F43 |
| expiry | F08, F15, F24 |
| counterfactual | F09, F15, F33, F37 |

## Review before catalog generation

#256 re-read [fact-feature-registry.md](fact-feature-registry.md) and [detector-catalog-freeze.md](detector-catalog-freeze.md) against the packaged freeze registry, beat catalog, successor graph, pattern cards and detector catalog. Counts and references match. No `machine/` hash was rewritten.

## Loader fail-soft contract (#257)

Invalid packaged catalogs disable commentary without raising: `outcome=commentary_disabled`, `CatalogLoadFailure` with `commentaryEnabled=false`, `mainLoopRaises=false`, `partialCatalogPublished=false`, `reason=catalog_invalid`, `runtimeStatus=disabled`. Same-beat authored fallback is forbidden (`same_beat_authored_fallback=False`). No sequence-graph v1 fallback.

## EpisodeRegistry (#258)

`EpisodeRegistry` owns runtime episode instances independently of speech. Schema `episode/2`; states `candidate|active|suspended|resolved|invalidated`. Occurrence scope requires occurrence + lineage; stream-only `stream_lifecycle` (and optional stream `filler_single`) may omit both. Semantic identity locates one live instance; distinct identities run concurrently. Exclusive battle group suspends overlapping live instances. Capacity defaults `active_capacity=64`, `resolved_capacity=256` match the frozen public contract. Not exported from `events/__init__.py`; not live-wired. Module lookup: [inflight § #258](../dokumentace/inflight/README.md#258-lineage-aware-episoderegistry-lookup).

## EpisodeRetention (#259)

`EpisodeRetention` stores bounded resolved-outcome metadata without a prepared-speech queue. Schema `episode-retention/2`. Policy TTL/salience come from frozen catalog families (`critical` 45s/90, `result` 30s/78, `live_story` 10s/64, `transient` 6s/56, `context` 20s/46, `filler` 12s/24). `speakable_until_ms = resolvedMonoMs + ttlMs`; half-open validity `now < speakable_until`. Self-contained `critical`/`result` outcomes remain selectable after speech complete; intermediate `live_story`/`transient` revisions supersede same `(occurrenceId, definitionId, semanticIdentity)` and are `skipped` after speech. `on_speech_complete` re-evaluates `expired_ttl` / `skipped` / remaining self-contained by `(-salience, speakable_until_ms, episodeId)`. Default `resolved_capacity=256` matches the frozen public contract. No BeatPlan / TtsUtterance storage. Not exported from `events/__init__.py`; not live-wired. Module lookup: [inflight § #259](../dokumentace/inflight/README.md#259-resolved-episode-retention-lookup).

## SilenceClock (#260)

`SilenceClock` owns the one-shot audience silence deadline and fact-grounded filler selection via `evaluate_filler`. Default interval `LONG_SILENCE_MS=33_000` (`commentary.director.long_silence_s`, already frozen). Fire at `now >= deadline`; stale generation is a no-op; rearm is exactly `now + interval` when no playback is accepted. Playback accepted cancels without credit. Building/committed and race events do not move the origin. Busy lane `building|committed|speaking|stopping` selects no filler and still rearms. OBS unknown pauses without elapsed credit; disable/shutdown cancel. Pre-session admits only stream-scope `filler.lobby` plus fresh stream `context.track_identity`. Phase fillers need fresh `vehicle.phase` plus one `W_filler_phase` companion; other occurrence fillers need matching context plus one `W_filler_off_track` or `W_quiet_track` fact. Empty allowlist, forecast weather and invented race predicates fail `source_guard`; a live race opportunity yields `no_candidate`; race candidates replace an uncommitted filler without moving the origin. Story id `filler_single`. Not exported from `events/__init__.py`; not live-wired. Module lookup: [inflight § #260](../dokumentace/inflight/README.md#260-long-silence-lifecycle-lookup).

## BeatPlan (#261)

`BeatPlanner` owns immutable just-in-time planning when the speech lane is idle. Schemas `beat-plan/2` + `prompt-options/2`. Types: `BeatPlan`, `BeatPlanner`, `PlanIntent`, `PlanStep`, `BoundClaim`, `PromptOptions`, `FunnelLink`, `CandidateOrder`, `tight_prompt_options`. `BeatPlanner.plan(intent, lane=..., planning_cycle_id=...)` → `PlanStep(reason, plan, opportunity_consumed=False)`.

Reasons: `planned` / `lane_busy` / `source_guard_failed` / `future_successor_forbidden` / `ledger_dump_forbidden` / `consecutive_cap` / `not_self_contained` / `deduped` / `planning_cycle_exhausted`. Busy lanes `building|committed|speaking|stopping` → no plan. Dedup key `(beat_id, episode_id, episode_revision)` merges source refs. Same `planningCycleId`: ordinal `1|2` then `planning_cycle_exhausted`. `candidateOrder={reducerSequence,sourceOrdinal}` is the stable age/tie-break authority. Half-open expiry: `plannedMonoMs <= now < expiresMonoMs`. Null occurrence/lineage only for `stream.started` and stream-scope `filler.lobby`.

Tight baseline PromptOptions: freedom `tight`, patternChoice `fixed`, optionalClaimLimit 0, maxSentences 1, temperature 0.15, topP 0.75; seed from `deterministic_planning_seed(PlanningSeedMaterial)`. First production catalog `promotedMaxFreedom=tight` — no widen. Role map: catalog `result`→`outcome`, `single`→`filler`. Self-contained after speech: closing / critical / catalog policy `critical|result`. Consecutive cap: min(public `GLOBAL_CONSECUTIVE_CAP=3`, story `max_consecutive_non_closing_beats`); closing/critical spared. Ledger dump forbidden: `selected_fact_ids` must equal the claim-fact union. Future successor plans forbidden (`future_beat_ids` nonempty → reject). Every selected claim has fact/evidence refs; empty `fact_ids` → `source_guard_failed`. G0 forbidden claim types attached on the plan. Language constant `en`. Does not consume opportunity; does not emit utterance. Replay fixtures: `tests/fixtures/beat_plan/{transition,counterfactual_identity,expiry}.json`. Not exported from `events/__init__.py`; not live-wired. Module lookup: [inflight § #261](../dokumentace/inflight/README.md#261-immutable-beatplan-lookup).

## ExposureStore (#263)

`ExposureStore` records playback-accepted speech and exposes decaying fatigue views. Schema `exposure-view/2`. Types: `ExposureStore`, `ExposureIntent`, `SpokenExposure`, `FatigueView`, `ChannelPressureView`, `CadenceAudit`, `ExposureStep`, `EmbeddingAdapter`, `half_life_decay`, `content_tokens`.

Record gate: only `phase=speaking` + `source_kind=narrative`; planned/rejected/stale/building/committed/manual add no fatigue. Weight 1.0 at PLAYBACK_ACCEPTED / SPEAKING. Decay `0.5 ** (age/half_life)` = `2^(-(t-spoken_at)/half_life)`; rejects `exp(-age/half_life)`. Semantic half-life 90_000 ms; pattern 180_000 ms (F23 goldens from `machine/vertical-slice-fixtures.json`). Channel pressure `6 * min(3, Σ decay)` on accepted exposures of that `tape_channel`. `event_penalty = policy.penalty_coefficient * channel_pressure`. `cadence_half_life = max(global_min_interval 4s, numeric profile cadence)`; null cadence uses TTL; filler uses `LONG_SILENCE_MS=33_000` not TTL.

Lexical Jaccard on EN-stopword content tokens; lexical-tail MVP = last 4 content tokens. Embedding adapter optional; `embedding_is_gate` always False. Family/role/filler histories are cadence/guard audit only (`cadence_audit`), not score terms. Capacity default 128 (`commentary.director.decision_capacity`, already frozen); evict oldest `(acceptedMonoMs, utteranceId)`; stream reset clears. Replay fixtures: `tests/fixtures/exposure_store/{transition,counterfactual_identity,expiry}.json`. Not exported from `events/__init__.py`; not live-wired. Does not implement #264 speech lane. Module lookup: [inflight § #263](../dokumentace/inflight/README.md#263-exposure-store-lookup).

## EventOpportunityQueue (#283)

`OpportunityQueue` owns bounded expiring speakable metadata and one-pass post-beat event-versus-successor arbitration. Schema `event-opportunity/2`. Types: `OpportunityQueue`, `EventOpportunity`, `OpportunityIntent`, `ArbitrationContext`, `ArbitrationDecision`, `SelectedCandidate`, `EpisodeBeatRef`, `OpportunityStep`, `ChannelCounters`.

Immutable `EventOpportunity`: identity + snapshot TTL/priority/urgency/penalty, one `tape_channel`, `candidateOrder`, no text/prompt/BeatPlan. Half-open validity `createdMonoMs <= now < expiresMonoMs`. Consume only on `SPEECH_STARTED` (`consumed_playback_accepted`); `reject_attempt` releases reservation (failed beat ≠ consume). Terminal reasons: `consumed_playback_accepted` / `expired_ttl` / `superseded_revision` / `invalidated_*` / `evicted_capacity`. Relations `opens|updates|resolves|conflicts|independent` map to frozen director IDs.

Natural successors from last spoken beat + catalog edges; score `58 + 6` same-story + edge bonus + `6` material − `penaltyCoefficient * channel_pressure`. Event score: `basePriority − penaltyCoefficient * channel_pressure`. Switch: higher urgency always; equal/lower needs inclusive `switch_margin` **8** (frozen). No event/successor → `SILENCE` (`no_candidate`); filler only on silence impulse. Overflow evicts oldest pending by `candidateOrder`; fail-soft. Per-`tape_channel` counters: kick/queued/selected/consumed/expired/superseded/spoken/evicted. Six policy profiles + cadence scopes from [event-beat-disposition.md](event-beat-disposition.md). Expiry cancels reserved preaccept work; never starts a fallback impulse.

Frozen knobs (already in public contract): `opportunity_capacity` **128**, `switch_margin` **8**, `selection_threshold` **35**. Reads immutable `ChannelPressureView` from `ExposureStore` one-way. Replay fixtures: `tests/fixtures/opportunity_queue/{transition,counterfactual_identity,expiry}.json`. Not exported from `events/__init__.py`; not live-wired. Does not implement #264 speech lane. Module lookup: [inflight § #283](../dokumentace/inflight/README.md#283-expiring-event-opportunities-lookup).

## StoryDirector (#262)

`StoryDirector` owns hard eligibility before scoring and one deterministic H-then-M pass over event, successor and filler candidates. Schema `director-decision/2` (internal decision; full tape record is later wiring). Types: `StoryDirector`, `DirectorCandidate`, `DirectorWorld`, `EligibilityGates`, `FatigueTerms`, `ScoreTerms`, `CandidateRecord`, `DirectorDecision`.

Hard conjunction from spec §23.3 plus `source_guard`, half-open snapshot TTL, consecutive non-closing successor cap `min(3, story cap)`, and `(beat_id, episode_revision)` suppression. Score cannot revive an invalid fact or lineage. Named §9.2 terms only; V4 `wire_priority` never enters the score; no family/role hidden penalties. EffectiveScore is EventScore / ContinuationScore / Score by source. `P` is the focused continuation; higher urgency switches immediately; equal/lower needs inclusive `switch_margin=8`. Filler only when no story choice. Below `selection_threshold=35` → SILENCE. Building replace only from a newly accepted event after `replacement_cost`; winner starts attempt 1 of a new cycle. Attempt 2 is a distinct beat after `note_failure`; second failure exhausts the cycle.

Frozen knobs (already in public contract): `selection_threshold` **35**, `switch_margin` **8**, `max_consecutive_story_beats` **3**, `decision_capacity` **128**, `long_silence_s` **33**. Replay fixtures: `tests/fixtures/story_director/{transition,counterfactual_identity,expiry}.json`. Not exported from `events/__init__.py`; not live-wired. Does not implement #264 speech lane. Module lookup: [inflight § #262](../dokumentace/inflight/README.md#262-storydirector-eligibility-lookup).

## Out of scope

- #264 speech lane and RealizationBundle (next; not started)
- live EventManager / NarrativeRuntime / V4 overlay tape
- public CONFIG / API / README product contracts
