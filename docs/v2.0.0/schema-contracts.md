# v2.0.0 narrative schemas, IDs and reason registry freeze

**Status:** design-freeze candidate owned by issues #235–#239, #245 and #261

This branch-only artifact freezes the semantic DTO boundary. Field names below are the canonical lower-camel-case JSON/tape representation; Python may use snake_case internally but round-trips must be lossless. Actual JSON Schema files and golden fixtures remain required before runtime edits.

## Global encoding rules

- UTF-8 JSON, objects only at each record root, duplicate keys rejected.
- Numbers must be finite; NaN and infinities are invalid. Integer timestamps and revisions are nonnegative and fit signed 64-bit.
- Unknown fields are rejected in config, commands, catalog objects, public writes and replay input. Public read clients may ignore additive fields only after a future schema-version change explicitly permits them.
- IDs use ASCII `[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}` unless a narrower registry applies. Human text is normalized Unicode with control characters rejected.
- Arrays preserve semantic order and have unique entries unless explicitly described as a sample sequence.
- Hashes are `sha256:` plus lower-case hex over canonical UTF-8 JSON: recursively sorted object keys, original array order, no insignificant whitespace and no NaN/infinity.
- Monotonic times are process-local. Each tape manifest records `processStartedAtUtc`, `processMonotonicOriginMs=0` and a unique `processInstanceId`; values from different process instances are never subtracted.
- UTC exists only for operator correlation/manifest boundaries. Eligibility, TTL, cadence, debounce and latency use monotonic milliseconds.

## Frozen version strings

| Artifact | `schemaVersion` |
| --- | --- |
| unchanged overlay EventEnvelope wire | `1.0` |
| narrative command | `narrative-command/2` |
| internal narrative event | `narrative-event/2` |
| detector observation | `detector-observation/2` |
| atomic fact | `atomic-fact/2` |
| fact view | `fact-view/2` |
| episode instance/summary | `episode/2` |
| event opportunity | `event-opportunity/2` |
| beat plan | `beat-plan/2` |
| prompt options | `prompt-options/2` |
| narrative catalog | `narrative-catalog/2` |
| tape manifest | `narrative-tape-manifest/2` |
| tape record | `narrative-tape-record/2` |
| public commentary HTTP | `commentary-runtime/2` |

Changing a field's meaning, unit, nullability, enum, identity semantics or required status requires a new schema version. Tuning a catalog value within its already declared type/unit/range does not.

## V4 wire compatibility boundary

`src/irswitch/events/envelope.py::EventEnvelope.to_dict()` remains byte-for-structure compatible with master schema `1.0`: no `tapeChannel`, fact IDs, narrative policy, occurrence identity or reducer sequence is added. The final fixture must serialize every current top-level and nested field, compare its canonical hash with the master fixture and prove overlay freeze/thaw is unchanged.

The narrative adapter may read the immutable frozen envelope plus upstream projection, but it must not reinterpret `priority` as speech priority or `expiresAt` as EventOpportunity TTL. It resolves narrative kind, facts, policy and `tapeChannel` from versioned registries.

## Shared identities

| ID | Construction | Scope |
| --- | --- | --- |
| `processInstanceId` | random UUID at process start | one process |
| `broadcastEpoch` | positive debounced BroadcastClock output epoch; 0 means no observed output yet | one observed OBS output run in this process |
| `streamEpoch` | positive StreamTimeline narrative-run epoch, allocated on commentary admission to an active `broadcastEpoch`; 0 means none has yet been allocated in this process | one uninterrupted automatic-commentary run |
| `sessionRef` | exact `{subSessionId: string, sessionNum: int}` | iRacing session row |
| `occurrenceId` | stable encoded stream epoch + stage + occurrence ordinal | one run of one session ref |
| `lineageId` | ordered active ancestor occurrence IDs joined/encoded losslessly | active session branch |
| `eventId` | upstream accepted ID or deterministic internal lifecycle ID | stream |
| `episodeId` | story definition + occurrence + correlation identity + episode ordinal | stream |
| `opportunityId` | deterministic event/revision/route ID | stream |
| `planId` | opportunity-or-episode revision + beat + attempt ordinal | stream |
| worker `token` | plan/manual ID + monotonically increasing dispatch generation | process |

Display names are never identities. A target change creates a new correlation/relation epoch rather than mutating an old identity.

## NarrativeEvent

Exactly these fields are required unless marked nullable:

| Field | Type/bound | Meaning |
| --- | --- | --- |
| `schemaVersion` | const `narrative-event/2` | version |
| `eventId` | ID | accepted/lifecycle event identity |
| `kind` | registered event-kind ID | semantic type, not free text |
| `phase` | `started|updated|ended|result|impulse` | truth lifecycle |
| `sourceEnvelope` | `{sessionId,eventId,sequence,eventType}` or null | unchanged V4 provenance |
| `sourceOrder` | `{fanoutStreamSequence,sourceOrdinal}` or null | external accepted order |
| `occurredMonoMs` | int | observation time |
| `broadcastEpoch` | int | parent OBS output identity |
| `streamEpoch` | int | stream identity |
| `sessionRef` | SessionRef or null | exact current ref |
| `occurrenceId` | ID or null | occurrence at event time |
| `lineageId` | ID or null | active lineage at event time |
| `correlationKey` | 0–8 IDs | ordered semantic identity |
| `factIds` | 1–32 unique IDs | facts proving event claims; context-only visual identifiers never enter this DTO |
| `materialRevision` | int | correlation revision |
| `confidence` | float 0..1 | evidence confidence |
| `tapeChannel` | registered channel ID | taxonomy dimension |
| `taxonomyHash` | sha256 | policy lookup provenance |
| `payload` | kind-specific registered object, max 32 fields | typed semantic data only |

Metrics copied from a V4 envelope enter `payload` only through a kind-specific adapter schema with declared scalar type/unit/unknown semantics. Free-form metrics never become claims.

## DetectorObservation

This is a read-only pre-arbitration/tuning record and never enters episode truth by itself:

```text
schemaVersion, observationId, detectorId, detectorVersion, detectorConfigHash,
observedMonoMs, broadcastEpoch, streamEpoch, sessionRef?, occurrenceId?, correlationKey[0..8],
previousState, candidateState, transitionReason, featureValues{0..64},
predicateResults[0..64], coverage[0..16], wouldEmitEventKind?, tapeChannel
```

Detector states are `inactive|candidate|active|clearing`. Predicate results are `true|false|unknown`; each value names its registered feature/predicate ID and typed value/unit. `wouldEmitEventKind` is nullable. FactLedger and the typed detector/timeline producers create AtomicFact truth independently of editorial acceptance. Only the accepted-event adapter creates a NarrativeEvent, opens or materially revises a speakable episode, or creates an EventOpportunity. A newer FactView may close/invalidate an episode or plan whose claims became false; it cannot open an episode, increment a speakable material revision or trigger a director pass by itself.

## AtomicFact and FactView

AtomicFact fields:

```text
schemaVersion, factId, predicate, subjectId?, objectId?, attributes{0..32},
polarity, validFromMonoMs, validUntilMonoMs?, observedAtMonoMs,
broadcastEpoch, streamEpoch, occurrenceId?, lineageId?, evidenceRefs[1..16], confidence,
scope, status, revision
```

- `polarity`: `positive|negative`.
- `scope`: `occurrence|downstream|stream|revalidate|historical_only`.
- `status`: `provisional|active|expired|superseded|historical|rejected|unknown`.
- Broadcast/stream epochs are positive for every fact admitted to a narrative run. Occurrence/lineage are nullable only for `scope=stream`; occurrence, downstream, revalidate and historical-only facts require both in the v2 registry. On a session transition a revalidate producer may publish a newly evidenced fact under the new occurrence, but the old fact never changes identity/scope in place.
- Predicate/attribute registries define scalar type, unit, null/unknown policy, actor ordering and legal scopes. Missing is unknown; zero/false are values.
- `validUntilMonoMs`, when present, is greater than or equal to valid-from. `observedAtMonoMs` cannot be later than the FactView creation instant.

FactView is `{schemaVersion, viewRevision, createdMonoMs, broadcastEpoch, streamEpoch, occurrenceId?, lineageId?, historyComplete, facts[0..1024], compactedSummaryRefs[0..64]}`. Facts sort by fact ID for hashing; semantic recency comes from revisions/times, not array order. The live caps remain 512 active plus 512 historical summaries.

## Episode

Episode instance/summary fields:

```text
schemaVersion, episodeId, definitionId, scope, occurrenceId?, lineageId?,
semanticIdentity[1..8], correlationIds[0..8], state,
openedMonoMs, updatedMonoMs, resolvedMonoMs?, resolutionReason?,
factIds[0..64], materialRevision, spokenBeatIds[0..64],
nextEligibleMonoMs, lastSpokenBeatId?, continuationPriority,
historyComplete
```

Scope is `stream|occurrence`. `stream_lifecycle` and the explicitly stream-routed `filler_single` lobby episode may omit occurrence/lineage; occurrence scope requires both. The lobby stream form may reference only stream-scope facts and resolves after its silence impulse, context change or narrative-run end. State is `candidate|active|suspended|resolved|invalidated`. Dormant is absence, not a serialized instance. Resolved/invalidated requires terminal time and registered resolution reason; other states require both null. A compacted summary uses the same identity/state contract but may replace `factIds` with summary fact refs explicitly marked historical.

## EventOpportunity

Required fields:

```text
schemaVersion, opportunityId, eventId, eventKind, sourceOrder?,
streamEpoch, occurrenceId?, lineageId?, episodeId, correlationKey[0..8],
tapeChannel, createdMonoMs, expiresMonoMs, basePriority, urgency,
penaltyCoefficient, materialRevision, state, reservationToken?,
terminalReason?, policyHash, sourceFactIds[1..32]
```

Urgency is `background|context|story|critical`; state is `pending|reserved|consumed|expired|superseded|invalidated|evicted`. Only reserved has a reservation token. Only terminal states have terminal reason. Expiry is strictly after creation; priority is finite 0..100 and penalty is finite 0..4. Routing creates/locates the episode before queue admission, so `episodeId` is never null. `occurrenceId` and `lineageId` may both be null only for `stream.started` routed to `stream_lifecycle` or a `filler.lobby` silence opportunity routed to the stream form of `filler_single`; all other opportunities require both. The opportunity contains no prompt, BeatPlan or text.

## PromptOptions and BeatPlan

PromptOptions is exactly:

```text
schemaVersion, freedom, patternChoice, optionalClaimLimit,
allowClauseReorder, maxSentences, temperature, topP, seed
```

Freedom is `tight|balanced|loose`; pattern choice is `fixed|family_pool`; optional claim limit is 0..2; max sentences is 1..2; temperature is 0..2; topP is greater than 0 and at most 1; seed is unsigned 64-bit. Catalog maxima may tighten but never expand these ranges.

BeatPlan is exactly:

```text
schemaVersion, planId, planningCycleId, cycleAttemptOrdinal, beatId, episodeId, opportunityId?, candidateSource,
beatRole, streamEpoch, occurrenceId?, lineageId?, episodeRevision,
requiredClaims[1..16], optionalClaims[0..2], forbiddenClaimTypes[0..32],
requiredFactIds[1..32], realizationFamily, realizationPattern,
realizationBackend, promptOptions, language, styleCardId?, maxChars,
maxSeconds, plannedMonoMs, expiresMonoMs, sourceRefs[1..32],
catalogHash, factViewRevision
```

Candidate source is `event_opportunity|story_successor|episode_beat|filler`; role is `opening|update|outcome|recap|transition|filler`; backend is `authored|qwen_compiled`; language is constant `en`. `planningCycleId` identifies one director impulse and `cycleAttemptOrdinal` is exactly `1|2`; at most two different BeatPlans may be dispatched in that cycle. Only `stream.started` and the stream-scope form of `filler.lobby` may omit occurrence/lineage; the latter may bind only `broadcast.context(context=lobby)` plus a current stream-scope `context.track_identity`. Claims are typed predicate/actor/attribute objects referencing required fact IDs, not natural-language assertions. `maxChars` is 1..512 and cannot exceed endpoint/catalog limits. A BeatPlan is immutable and exists only for the current lane attempt.

## Tape envelope

One NDJSON file begins with one manifest record and then tape records. A file is scoped to one `(processInstanceId, streamEpoch-or-null)`; records from two narrative runs never share a file. Rotated continuations repeat the manifest with the same process/broadcast/stream identity and a new file ordinal. Pre-run process/health records may use a separate `streamEpoch=null` file. Narrative-run close (confirmed OBS end, commentary disable or shutdown) writes a trailer and closes the current file; re-enable opens a new manifest with the new stream epoch.

Manifest fields:

```text
schemaVersion, recordType="manifest", processInstanceId, processStartedAtUtc,
processMonotonicOriginMs=0, appVersion, gitRevision?, platform,
broadcastEpoch?, streamEpoch?, fileOrdinal, openedAtUtc, catalogVersion, catalogHash,
configGeneration, configHash, enabledPurposeChannels,
redactionPolicy, historyComplete, previousFileHash?
```

Record fields:

```text
schemaVersion, recordId, recordType, processInstanceId, broadcastEpoch?, streamEpoch?,
reducerSequence?, recordedMonoMs, recordedAtUtc?, purposeChannel,
tapeChannel?, correlationIds[0..8], payloadSchemaVersion, payload
```

Purpose channel is `flow|llm_eval|detector_tuning`. Record type is one of `context_applied|detector_observation|narrative_event|fact_change|episode_change|opportunity_change|director_decision|llm_attempt|speech_exposure|config_applied|health_change|mailbox_gap|manifest_trailer`. `payload` must validate against its named schema. The writer records ordered actor facts/decisions with reducer sequence and unordered pre-arbitration observations without one. Prompt/completion contents obey capture policy and redaction; hashes and latency metadata remain.

Trailer payload contains final record/file hash, counts by record/purpose/tape channel, drops by reason, last reducer sequence, shutdown/rotation reason and `complete`. A missing/invalid trailer makes that file incomplete but does not make prior valid NDJSON records unreadable.

## Frozen reason IDs

Reason IDs are machine values; operator messages are separate and bounded. The initial registry is:

| Domain | IDs |
| --- | --- |
| director selection | `highest_valid_candidate`, `active_story_continuation`, `related_event_update`, `higher_urgency_switch`, `switch_margin_met` |
| director silence/reject | `no_candidate`, `below_threshold`, `hard_guard_failed`, `source_guard_failed`, `cadence_blocked`, `fatigue_blocked`, `attempt_suppressed`, `planning_cycle_exhausted`, `tts_unavailable`, `stream_inactive`, `context_unknown` |
| opportunity terminal | `consumed_playback_accepted`, `expired_ttl`, `superseded_revision`, `invalidated_truth`, `invalidated_occurrence`, `closed_stream`, `commentary_disabled`, `evicted_capacity` |
| episode terminal | `outcome_observed`, `natural_exit`, `target_changed`, `composite_exited`, `occurrence_ended`, `occurrence_superseded`, `stream_ended`, `commentary_disabled`, `evidence_invalidated` |
| attempt terminal | `realization_timeout`, `realization_transport`, `realization_invalid_response`, `semantic_rejected`, `freshness_stale`, `replaced_precommit`, `tts_failed_before_acceptance`, `stale_worker_token` |
| verifier rejection | `empty`, `too_long`, `sentence_count`, `token_count`, `non_en_contract`, `meta_output`, `unknown_fragment`, `unknown_entity`, `actor_reversed`, `actor_ambiguous`, `number_unbound`, `number_mismatch`, `unit_mismatch`, `polarity_mismatch`, `tense_mismatch`, `required_missing`, `forbidden_claim`, `extra_claim`, `causal_inference`, `intent_inference`, `emotion_inference`, `medical_inference`, `prediction_as_result`, `result_as_prediction`, `unsupported_certainty`, `unsafe_negation` |
| detector transition | `enter_started`, `enter_confirmed`, `enter_lost`, `material_band_changed`, `material_delta_met`, `update_rate_limited`, `clear_started`, `clear_cancelled`, `clear_confirmed`, `target_changed`, `occurrence_reset`, `stream_reset`, `unsupported_stage`, `identity_conflict`, `feature_unknown`, `required_capture_lost` |
| speech terminal | `completed`, `interrupted_stream_end`, `interrupted_occurrence_reset`, `interrupted_commentary_disabled`, `interrupted_truth_invalidated`, `interrupted_shutdown`, `tts_failed_after_acceptance` |
| mailbox/tape health | `mailbox_evicted_update`, `mailbox_recovery`, `mailbox_history_incomplete`, `tape_queue_drop`, `tape_write_failed`, `tape_flush_timeout`, `capture_unavailable` |
| config/runtime health | `disabled_by_config`, `disabled_invalid_config`, `legacy_key`, `starting`, `ready`, `component_unavailable`, `session_identity_conflict`, `obs_state_unknown`, `history_incomplete` |

Adding a diagnostic reason is additive only inside the same version when no consumer exhaustively switches on it; implementation code must still use a registry constant. Removing, renaming or changing terminal meaning requires a schema version change.

## Registry prerequisites

Before schemas can be implemented, issue #236 must materialize machine-readable registries for:

- all 60 current identifier dispositions plus new internal event/command kinds;
- fact predicates/attributes with scalar type, units, legal actors/scopes and unknown semantics;
- feature IDs/units/sample quality;
- story, beat, realization-family, relation and `tapeChannel` IDs;
- reason IDs above and detector transition reasons.

The exact human-review candidate for fact predicates, scalar/unit types, claim allowlists, feature IDs and `tapeChannel` taxonomy is [the fact/feature registry](fact-feature-registry.md). Machine schemas may encode it, but may not silently add a predicate, attribute, enum literal, feature or channel.

The loader rejects duplicate/case-colliding IDs, unknown references, unit mismatch, undeclared attributes, unsafe array/object bounds and catalog hashes built with a different registry version.

## Closure fixtures

The design gate remains closed until branch-only fixtures prove:

1. master EventEnvelope canonical JSON/hash is unchanged;
2. every DTO accepts one complete golden and rejects unknown fields, NaN/infinity, bad units, bad enums, missing required fields and illegal nulls;
3. all 64 beats and 60 dispositions resolve through the registries;
4. tape manifest/record/trailer round-trip and detect truncation/hash mismatch;
5. API fact bindings round-trip through the same AtomicFact schema rather than a looser duplicate;
6. all public/status/decision terminal reasons exist in the frozen registry.
