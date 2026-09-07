# v2.0.0 narrative schemas, IDs and reason registry freeze

**Status:** design-freeze candidate owned by issues #235–#239, #245 and #261

This branch-only artifact freezes the semantic DTO boundary. Field names below are the canonical lower-camel-case JSON/tape representation; Python may use snake_case internally but round-trips must be lossless. Core DTO, 64-beat, successor-graph, public-config and public-API JSON Schema projections are materialized under `machine/`; detector and executable scenario fixtures remain separate design-freeze gates.

Implementation placement is one neutral `src/irswitch/contracts/narrative.py` module (or package with the same dependency role) containing DTO/schema primitives only, plus packaged canonical schemas under `src/irswitch/contracts/schemas/v2/`. It imports no `logic`, `events`, `race`, `commentary`, `overlay`, `obs` or `server` implementation. Producers, replay/offline tooling and the commentary consumer may import/read it; cross-layer behavior remains in their owning modules. Runtime parsing uses the typed contract layer and explicit invariant checks, so shipping JSON Schema does not add a new validation dependency.

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
| feature frame | `feature-frame/2` |
| detector observation | `detector-observation/2` |
| pre-arbitration event candidate | `event-candidate-tap/2` |
| timeline snapshot | `timeline-snapshot/2` |
| session plan | `session-plan/2` |
| atomic fact | `atomic-fact/2` |
| fact view | `fact-view/2` |
| episode instance/summary | `episode/2` |
| event opportunity | `event-opportunity/2` |
| beat plan | `beat-plan/2` |
| prompt options | `prompt-options/2` |
| realization bundle | `realization-bundle/2` |
| compiled prompt | `compiled-prompt/2` |
| realization request | `realization-request/2` |
| realization result | `realization-result/2` |
| LLM attempt | `llm-attempt/2` |
| TTS utterance | `tts-utterance/2` |
| TTS callback | `tts-callback/2` |
| speech exposure | `speech-exposure/2` |
| narrative catalog | `narrative-catalog/2` |
| tape manifest | `narrative-tape-manifest/2` |
| tape record | `narrative-tape-record/2` |
| public commentary HTTP | `commentary-runtime/2` |
| effective commentary config | `commentary-config/2` |

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
| `occurrenceId` | exact ASCII `<streamEpoch>:<stage>:<ordinal>` | one run of one session ref |
| `lineageId` | 1–3 occurrence IDs joined by ASCII `>` in stage order | active session branch |
| `eventId` | upstream accepted ID or deterministic internal lifecycle ID | stream |
| `episodeId` | story definition + occurrence + correlation identity + episode ordinal | stream |
| `opportunityId` | deterministic event/revision/route ID | stream |
| `planId` | opportunity-or-episode revision + beat + attempt ordinal | stream |
| worker `token` | plan/manual ID + monotonically increasing dispatch generation | process |

Display names are never identities. A target change creates a new correlation/relation epoch rather than mutating an old identity.

`streamEpoch` and `ordinal` use canonical unsigned decimal with no leading zero except the value `0`; a live occurrence requires positive stream epoch, while ordinal starts at zero independently for each stage in the run. Stage is the full lower-case enum. Thus `3:race:2` and `3:practice:0>3:qualifying:1>3:race:2` are canonical; abbreviations, alternate separators and percent/Unicode lookalikes are invalid. `sessionRef` remains a separately validated field and the owner must prove that each encoded occurrence resolves to exactly one retained occurrence carrying that ref.

## NarrativeEvent

Exactly these fields are required unless marked nullable:

| Field | Type/bound | Meaning |
| --- | --- | --- |
| `schemaVersion` | const `narrative-event/2` | version |
| `eventId` | ID | accepted/lifecycle event identity |
| `kind` | registered event-kind ID | semantic type, not free text |
| `phase` | `started|updated|ended|result|impulse` | truth lifecycle |
| `deliveryClass` | `ordinary|protected` | mailbox admission class resolved by the frozen rule below |
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
| `factViewRevision` | int | exact FactView revision in the containing context batch |
| `materialRevision` | int | correlation revision |
| `confidence` | float 0..1 | evidence confidence |
| `tapeChannel` | registered channel ID | taxonomy dimension |
| `funnel` | FunnelIdentity | immutable candidate/event link with downstream IDs still null |
| `taxonomyHash` | sha256 | policy lookup provenance |
| `payload` | kind-specific registered object, max 32 fields | typed semantic data only |

Metrics copied from a V4 envelope enter `payload` only through a kind-specific adapter schema with declared scalar type/unit/unknown semantics. Free-form metrics never become claims.

`deliveryClass=protected` exactly when `phase` is `ended|result` or `kind` is one of `STREAM_STARTED|STREAM_ENDED|SESSION_STARTED|SESSION_ENDED|SESSION_RESTARTED`; every other NarrativeEvent is ordinary. Taxonomy validation must derive and compare this value rather than trusting producer input. Changing this set is an actor/schema contract change, not tuning.

## TimelineSnapshot and ApplyContextBatch

SessionPlan is exactly:

```text
schemaVersion, planRevision, capturedMonoMs, subSessionId?,
valid, reason?, entries[0..3], unsupportedEntries[0..16],
unsupportedOverflowCount
```

Each supported entry is exactly `{sessionRef,stage}`. A valid plan has a nonempty `subSessionId`, null reason, one to three unique supported stages and strictly increasing `sessionNum` and stage rank `practice < qualifying < race`; therefore every nonempty subset is legal and canonical. Unsupported SessionInfo rows are retained only as `{sessionNum,externalType}` audit metadata and never aliased to a supported stage. They preserve source row order; only the first 16 are retained and `unsupportedOverflowCount` is the exact nonnegative omitted count. Truncating unsupported audit rows does not invalidate an otherwise valid plan.

A coherent complete SessionInfo snapshot with missing/invalid SubSessionID or supported-row identity, no supported stage, duplicate supported stage or decreasing rank produces `valid=false`, reason `session_plan_conflict`, nullable `subSessionId`, and empty supported entries. A missing, partially parsed or disconnected SessionInfo source is not a conflicting candidate and publishes no new SessionPlan: before the first plan its revision remains absent, and afterward the last publication is retained while current session identity is suspended by the normal connection contract.

The first coherent plan in a narrative run becomes an immutable accepted prefix. An unchanged observation retains `planRevision`. A later plan is accepted only when all existing entries are an exact prefix and every appended entry has a greater `sessionNum` and stage rank; acceptance increments `planRevision`. Insertion, removal, reorder, retype or identity replacement latches `session_plan_conflict` for the rest of that narrative run, publishes an invalid empty plan at a new revision, clears current session identity from snapshots and suspends new session-scoped state. The last accepted prefix remains internal historical evidence but cannot be used to admit current speech. A new broadcast/run clears the latch and may establish a different initial plan.

TimelineSnapshot fields are exactly:

```text
schemaVersion, timelineRevision, observedMonoMs, broadcastEpoch,
streamEpoch, narrativeRunActive, obsState, sessionRef?, stage?,
sessionPlanRevision?, occurrenceId?, lineageId?, historyComplete,
transitionReasons[0..8]
```

`obsState` is `inactive|active|unknown`; `stage` is `practice|qualifying|race` or null. SessionRef, stage, occurrence and lineage are either all coherent/current or all null. `sessionPlanRevision` is independent: it is null before the first plan publication and otherwise identifies the valid or invalid plan used by this snapshot, including pre-session and unsupported-session states. `narrativeRunActive=false` permits a retained last nonzero stream epoch for status/audit but no active occurrence. `transitionReasons` is empty when no lifecycle boundary occurred; otherwise it contains unique registered reasons in reducer effect order.

When several boundaries share one observation, their canonical order is the filtered order of: `session_ended`, `session_superseded`, `session_suspended`, `narrative_disabled`, `broadcast_ended`, `broadcast_unknown`, `broadcast_started`, `attached_live`, `process_recovery`, `narrative_enabled`, `broadcast_resumed`, `session_started`, `session_restarted`, `session_resumed`. This closes child/old occurrence effects before parent/run closure and creates/resumes the run before its new/current occurrence. Mutually exclusive reasons (for example two stream-start reasons) remain a schema error.

Stream-run allocation has this exclusive precedence:

| Observed condition | `stream.started.startReason` | Timeline reason in `transitionReasons` | History |
| --- | --- | --- | --- |
| process and enabled NarrativeRuntime previously observed this broadcast inactive/unknown, then BroadcastClock confirms a new active edge | `normal` | `broadcast_started` | complete from this run boundary |
| same process attaches its first enabled NarrativeRuntime to a BroadcastClock epoch already known active, with no prior narrative run in that epoch | `attached_live` | `attached_live` | incomplete |
| a newly started process first confirms OBS already active and no verified checkpoint is restored | `process_recovery` | `process_recovery` | incomplete |
| commentary was disabled after any run in the same still-active broadcast epoch and is enabled again | `enabled_mid_stream` | `narrative_enabled` | incomplete |

The first matching row in lifecycle precedence is used; one allocation cannot carry two start reasons. OBS unknown/resume without a closed narrative run allocates nothing and retains the existing epochs. A normal confirmed OBS end uses `broadcast_ended`, closes the run, and has no `stream.started` fact.

`APPLY_CONTEXT_BATCH.payload` is exactly:

```text
timeline: TimelineSnapshot
factView: FactView
events: NarrativeEvent[0..64]
```

The upstream synchronous pipeline completes timeline reduction, typed fact publication and EventManager arbitration before admitting this immutable batch. `timeline.timelineRevision`, `factView.viewRevision` and every event `factViewRevision` are nondecreasing; every event in the batch names exactly the contained FactView revision, and every event fact ID resolves in that view with matching broadcast/stream/occurrence/lineage identity. Events retain accepted external order. A mismatch rejects/audits the event while still allowing a newer coherent timeline/FactView to close or invalidate state.

A context batch is protected exactly when `timeline.transitionReasons` is nonempty or at least one contained event has `deliveryClass=protected`; otherwise it is ordinary. More than 64 accepted events from one upstream publication are partitioned, without loss, into consecutive source-order batches of at most 64. Each part repeats the same immutable timeline/FactView projection, shares the publication fanout sequence and owns an increasing disjoint inclusive source-ordinal range; equal projection revisions are legal idempotent replacements. A pure timeline/fact batch has null ordinal bounds. Each nonempty-event part is an independent planning impulse. This partition is performed only after EventManager acceptance and never reorders or coalesces events.

FeatureFrame/raw telemetry ticks never enter NarrativeMailbox. A batch is emitted only for a changed timeline projection, changed FactView revision, or at least one accepted event. APPLY_CONTEXT_BATCH is never coalesced: even a semantically superseded event may carry a distinct accepted result or fact transition. Capacity pressure uses the documented eviction/recovery barrier instead of an implicit merge.

## DetectorObservation

FeatureFrame is an upstream-only immutable relation projection and never enters NarrativeMailbox:

```text
schemaVersion, frameSequence, observedMonoMs, sourceSnapshotId,
broadcastEpoch, streamEpoch, sessionRef?, occurrenceId?, lineageId?,
correlationKey[1..8], values[0..64]
```

Each value is exactly `{featureId,value,unit,quality,observedMonoMs,validUntilMonoMs?,evidenceRefs[1..16]}` and must match the feature registry scalar/unit. `frameSequence` is positive and process-monotonic across all frames; detector instances ignore duplicate/older frames and never use narrative reducer sequence. SessionRef/occurrence/lineage are either all coherent or all null, but the three released battle detector definitions require all three plus a nonzero active stream epoch. Values are sorted by feature ID for hashing; their correlation identity is the frame identity and cannot be overridden per value.

This is a read-only pre-arbitration/tuning record and never enters episode truth by itself:

```text
schemaVersion, observationId, detectorId, detectorVersion, detectorConfigHash,
parameterSnapshotId, observedMonoMs, broadcastEpoch, streamEpoch,
sessionRef?, occurrenceId?, lineageId?, correlationKey[0..8], windowFrameRange?,
previousState, candidateState, transitionReason, featureValues{0..64},
predicateResults[0..64], coverage[0..16], wouldEmitEventKind?, tapeChannel
```

Detector states are `inactive|candidate|active|clearing`. Predicate results are `true|false|unknown`; each value names its registered feature/predicate ID and typed value/unit. `wouldEmitEventKind` is nullable. `parameterSnapshotId` resolves exactly one manifest snapshot for this detector/config hash. `windowFrameRange`, when captured, is exactly `{firstFrameSequence,lastFrameSequence,postWindowComplete}` with positive inclusive ordered endpoints. Every retained frame in that range is a separate `feature_frame` tape record with matching stream/occurrence/lineage/correlation identity. Optional capture may have gaps reported by drop accounting; required capture requires the entire declared range and any loss invokes the composition-owned disable path frozen in the actor contract. FactLedger and the typed detector/timeline producers create AtomicFact truth independently of editorial acceptance. Only the accepted-event adapter creates a NarrativeEvent, opens or materially revises a speakable episode, or creates an EventOpportunity. A newer FactView may close/invalidate an episode or plan whose claims became false; it cannot open an episode, increment a speakable material revision or trigger a director pass by itself.

## Pre-arbitration event tap and funnel identity

Every candidate submitted to EventManager is copied once to the read-only tape tap before arbitration. The tap never blocks, changes acceptance, retries a candidate or enters NarrativeMailbox. Its exact payload is:

```text
schemaVersion, candidateId, sourceClass, detectorObservationId?, sourceEnvelope?,
kind, phase, occurredMonoMs, broadcastEpoch, streamEpoch, sessionRef?, occurrenceId?,
lineageId?, correlationKey[0..8], materialRevision, tapeChannel, taxonomyHash,
arbitrationOutcome, arbitrationReason, acceptedEventId?
```

`sourceClass` is `detector|direct|lifecycle`. A detector candidate requires exactly one `detectorObservationId` and null `sourceEnvelope`; a direct candidate has null detector observation and may carry the unchanged bounded V4 source tuple; a lifecycle candidate has both null and uses its deterministic internal identity. `candidateId` is deterministic for the source identity, event kind, phase and material revision. The tap freezes the candidate before submission; after the synchronous EventManager return it appends exactly one outcome and submits the immutable record to TapeWriter. `arbitrationOutcome` is `accepted|rejected`; reason is respectively `accepted` or one of `pit_cycle|cooldown|lower_priority|unmatched_exit|unmatched_update|overlay_disabled|invalid_candidate`, and `acceptedEventId` is non-null exactly on acceptance. Re-observing the same canonical candidate/outcome is a duplicate tap no-op; changed content under the same ID is `event_candidate_protocol_violation`. Tape failure cannot reject or accept the candidate.

Every applicable downstream payload carries the same exact bounded `funnel` projection, named FunnelIdentity:

```text
sourceClass, candidateId?, detectorObservationId?, eventId?, materialRevision?,
opportunityId?, planId?, utteranceId?, tapeChannel
```

Each newly created downstream object copies the prior projection and fills only the ID it owns; already created objects remain immutable. Fields become non-null only when that object exists; an ID, revision or channel can never change later in the chain. The stages and counter increments are exact:

| Stage | Authoritative transition | Increment rule |
| --- | --- | --- |
| `kick` | one valid EventCandidateTap is offered to EventManager | once per unique `candidateId`, before acceptance |
| `accepted` | EventManager accepts the candidate and returns its stamped accepted identity | once per unique `(acceptedEventId,materialRevision)`; a speakable route then publishes the linked NarrativeEvent without a second increment |
| `queued` | actor creates or materially revises one EventOpportunity | once per unique `(opportunityId,materialRevision)`; in-place observation refresh is not a new queue count |
| `selected` | director reserves one immutable BeatPlan | once per unique `planId`, including a distinct alternative attempt |
| `started` | actor reduces valid `PLAYBACK_ACCEPTED` | once per unique `utteranceId`; dispatch/commit is not started |
| `expired` | opportunity reaches terminal `expired_ttl` | once per unique opportunity revision that was queued and expires |

Silence is not an EventManager candidate. Its actor evaluation creates a short-lived filler EventOpportunity with `sourceClass=silence`, null candidate/event IDs and begins its funnel at `queued`; a selected filler BeatPlan advances that same link. Natural story successors use `sourceClass=successor`, begin at `selected` without an EventOpportunity, and retain the episode revision through the BeatPlan even though it is outside this compact funnel projection. This adds `silence|successor` only to the downstream funnel source enum, not to EventCandidateTap.

Counters are monotonic within one `streamEpoch`, reset for a new narrative run and are keyed by the immutable `tapeChannel`. Status exposes their bounded live values even if tape recording is disabled; tape replay derives them only from records actually present and marks a cohort incomplete across a recorded gap. Funnel ratios may compare only compatible cohorts: `kick→accepted` for candidate sources, `accepted→queued` only for speakable accepted revisions, and `selected→started` for plans. Missing/non-applicable upstream stages are not zero-valued failures. A candidate rejected by EventManager ends after `kick` with its arbitration reason in the tap decision record; an accepted visual-only event ends after `accepted` and never fabricates an opportunity.

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
- `validUntilMonoMs`, when present, is greater than or equal to valid-from. Eligibility is the half-open interval `validFromMonoMs <= now < validUntilMonoMs`; equality of the endpoints is legal audit history but never current/speakable. `observedAtMonoMs` cannot be later than the FactView creation instant.

FactView is `{schemaVersion, viewRevision, createdMonoMs, broadcastEpoch, streamEpoch, occurrenceId?, lineageId?, historyComplete, facts[0..1024], compactedSummaryRefs[0..64]}`. Facts sort by fact ID for hashing; semantic recency comes from revisions/times, not array order. The live caps remain 512 active plus 512 historical summaries.

FactLedger capacity behavior is deterministic and loss-safe. Before admitting a new active revision it supersedes the older revision of the same semantic key and compacts/removes expired, superseded and rejected detail. It pins only upstream-knowable truth: the newest active stream-scope and active-ancestor downstream fact for each semantic key. It never reads BeatPlan, Episode or speech state. If active storage still exceeds 512, it evicts unpinned occurrence/revalidate facts in ascending `(observedAtMonoMs, revision, factId)` order, records `fact_capacity_evicted`, latches `historyComplete=false` for the run and makes the missing predicate unknown—not false. The downstream actor invalidates any dependent pre-accept work from the new FactView; capacity loss never interrupts already accepted playback by itself. If the upstream pinned set alone cannot fit, FactLedger publishes no partial current view, reports `fact_capacity_exhausted`, and commentary admits no new planning until a later coherent view fits; producers and the main loop continue. That later full view clears exhaustion but remains history-incomplete/degraded because prior loss cannot be reconstructed. Only a new narrative run can restore complete/ready state.

Historical storage first replaces detailed inactive facts with the registry-approved self-contained summary facts. Above 512, the oldest non-lineage individual summaries merge into per-stage aggregate summary records; these aggregates retain counts/extrema and tape ranges but are not actor-specific speakable evidence. Active-lineage downstream summaries are pinned. `compactedSummaryRefs` names at most the newest 64 aggregate/tape ranges in canonical `(stage,predicate,rangeStart)` order and omission is counted inside the aggregate metadata, never mistaken for complete history.

## Episode

Episode instance/summary fields:

```text
schemaVersion, episodeId, definitionId, scope, occurrenceId?, lineageId?,
semanticIdentity[1..8], correlationIds[0..8], state,
openedMonoMs, updatedMonoMs, resolvedMonoMs?, resolutionReason?,
factIds[0..64], materialRevision, spokenBeatIds[0..64],
materialOrder, nextEligibleMonoMs, lastSpokenBeatId?, continuationPriority,
historyComplete
```

Scope is `stream|occurrence`. `stream_lifecycle` and the explicitly stream-routed `filler_single` lobby episode may omit occurrence/lineage; occurrence scope requires both. The lobby stream form may reference only stream-scope facts and resolves after its silence impulse, context change or narrative-run end. State is `candidate|active|suspended|resolved|invalidated`. Dormant is absence, not a serialized instance. Resolved/invalidated requires terminal time and registered resolution reason; other states require both null. `materialOrder` is the candidate-order pair of the event/reducer impulse that created the current material revision. A compacted summary uses the same identity/state contract but may replace `factIds` with summary fact refs explicitly marked historical.

The configured current-episode capacity covers candidate+active+suspended instances. Before opening a new instance, EpisodeRegistry closes invalid/stale instances, then evicts the oldest unpinned suspended instance, then candidate, then lowest-continuation-priority active instance; ties use `materialOrder` and `episodeId`. An instance is pinned while it owns a reserved opportunity or the current building/committed/speaking token. Eviction terminalizes it as invalidated with `capacity_evicted`, invalidates its pending opportunities and writes a summary/tape record. If every retained instance is pinned, the accepted event/facts remain recorded but no new episode/opportunity is created; the decision records `episode_capacity_rejected`. Resolved summaries evict oldest by `(resolvedMonoMs,episodeId)` after their safe fact summaries/tape references are retained. No episode eviction changes FactLedger truth.

## EventOpportunity

Required fields:

```text
schemaVersion, opportunityId, eventId?, eventKind, sourceOrder?, funnel,
candidateOrder, streamEpoch, occurrenceId?, lineageId?, episodeId, correlationKey[0..8],
tapeChannel, createdMonoMs, expiresMonoMs, basePriority, urgency,
penaltyCoefficient, materialRevision, state, reservationToken?,
terminalReason?, policyHash, sourceFactIds[1..32]
```

Urgency is `background|context|story|critical`; state is `pending|reserved|consumed|expired|superseded|invalidated|evicted`. Only reserved has a reservation token. Only terminal states have terminal reason. Expiry is strictly after creation and eligibility is half-open `createdMonoMs <= now < expiresMonoMs`; priority is finite 0..100 and penalty is finite 0..4. Event-derived opportunities require `eventId`; only an actor-created silence opportunity has null event ID and `funnel.sourceClass=silence`. Routing creates/locates the episode before queue admission, so `episodeId` is never null. `occurrenceId` and `lineageId` may both be null only for `stream.started` routed to `stream_lifecycle` or a `filler.lobby` silence opportunity routed to the stream form of `filler_single`; all other opportunities require both. The opportunity contains no prompt, BeatPlan or text.

## PromptOptions and BeatPlan

PromptOptions is exactly:

```text
schemaVersion, freedom, patternChoice, optionalClaimLimit,
allowClauseReorder, maxSentences, temperature, topP, seed
```

Freedom is `tight|balanced|loose`; pattern choice is `fixed|family_pool`; optional claim limit is 0..2; max sentences is 1..2; temperature is 0..2; topP is greater than 0 and at most 1; seed is unsigned 64-bit. The baseline profile tuples are closed rather than freely combinable:

| freedom | patternChoice | optionalClaimLimit | allowClauseReorder | maxSentences | temperature | topP |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| `tight` | `fixed` | 0 | false | 1 | 0.15 | 0.75 |
| `balanced` | `family_pool` | 0..1 selected claims | family promotion flag | 1 | 0.35 | 0.85 |
| `loose` | `family_pool` | 0..2 selected claims | family promotion flag | 2 | 0.55 | 0.90 |

The seed is never process-global. Its material is the exact lower-camel object `{streamEpoch,opportunityId,episodeId,episodeRevision,beatId,cycleAttemptOrdinal}`, including JSON null for a missing opportunity, serialized by the global canonical JSON rule. Seed is the first eight SHA-256 digest bytes interpreted as one unsigned big-endian integer. A family-pool profile requires at least two enabled audited cards; otherwise that profile is schema-ineligible, not silently converted to fixed. Each realization family registry row carries `promotedMaxFreedom`, `preferredFreedom` and the two profile-specific clause-reorder booleans. Effective freedom is the least permissive of operator `llm.max_profile`, BeatDefinition maximum, family promoted maximum and family preferred profile. Policy `critical`, beat role `outcome|transition`, incomplete history, or minimum selected-fact confidence below 0.90 further caps it at tight. No runtime condition widens freedom to address repetition, latency or a failed attempt. The first production catalog sets every promoted maximum to tight; widening is a versioned corpus-backed catalog change.

BeatPlan is exactly:

```text
schemaVersion, planId, planningCycleId, cycleAttemptOrdinal, beatId, episodeId, opportunityId?, candidateSource, funnel,
candidateOrder, beatRole, streamEpoch, occurrenceId?, lineageId?, episodeRevision,
requiredClaims[1..16], optionalClaims[0..2], forbiddenClaimTypes[0..32],
selectedFactIds[1..32], realizationFamily, realizationPattern,
realizationBackend, promptOptions, language, styleCardId?, maxChars,
maxSeconds, plannedMonoMs, expiresMonoMs, sourceRefs[1..32],
catalogHash, effectiveConfigHash, configApplySequence, factViewRevision
```

Candidate source is `event_opportunity|story_successor|episode_beat|filler`; role is `opening|update|outcome|recap|transition|filler`; backend is `authored|qwen_compiled`; language is constant `en`. `candidateOrder` is exactly `{reducerSequence, sourceOrdinal}` with nonnegative integers: event ordinal inside the reducing batch, zero for a timer/worker impulse, or the episode `materialOrder` for a successor/episode beat. It is the stable age/tie-break authority; V4 sequence and timestamps are not substituted. `planningCycleId` identifies one director impulse and `cycleAttemptOrdinal` is exactly `1|2`; at most two different BeatPlans may be dispatched in that cycle. Only `stream.started` and the stream-scope form of `filler.lobby` may omit occurrence/lineage; the latter may bind only `broadcast.context(context=lobby)` plus a current stream-scope `context.track_identity`. A bound claim is exactly `{claimId,predicate,subjectId?,objectId?,polarity,temporalFrame,attributes[0..32],factIds[1..16]}`; polarity is `positive|negative`, temporal frame is `current|projected|historical`, attributes are sorted unique registered attribute IDs, and every claim fact ID occurs in `selectedFactIds`. `requiredClaims` contains every mandatory selected claim; `optionalClaims` contains only the zero to two optional claims actually selected for this attempt, not the BeatDefinition's unselected options. `selectedFactIds` is the sorted unique union used by both arrays. `maxChars` is 1..512 and cannot exceed endpoint/catalog limits. `expiresMonoMs` is strictly greater than `plannedMonoMs` and uses the same half-open validity boundary. `effectiveConfigHash` and `configApplySequence` are the same atomic ConfigLedger snapshot taken at planning. A BeatPlan is immutable and exists only for the current lane attempt.

## RealizationBundle

The pure prompt compiler runs synchronously in the same reducer turn that creates a BeatPlan and produces exactly one immutable worker input:

```text
schemaVersion, bundleId, beatPlan, factBindings[1..32],
actorBindings[0..16], surfaceLexicon, factBindingHash,
surfaceLexiconHash, bundleHash
```

`bundleHash` is the canonical hash of `{beatPlan,factBindings,actorBindings,surfaceLexicon}`; `bundleId` is exactly `rb:` plus the first 32 lower-case hex characters of that digest. `factBindings` are complete AtomicFact copies sorted by fact ID; their IDs equal `beatPlan.selectedFactIds`, every copy is current at `plannedMonoMs`, and `factBindingHash` is the canonical hash of that array. Actor bindings are sorted by actor ID and each is exactly `{actorId,aliases[1..8]}` using the same normalized, unique, collision-free rules as the offline validation endpoint. They bind every non-null subject/object in the selected claims and facts and contain no unused actor.

SurfaceLexicon is exactly:

```text
surfaceValueSets[0..64], relationLexemes[1..64],
connectives[0..32], forbiddenLexemes[0..128]
```

A surface value set is exactly `{surfaceValueSetId,factId,attributeId,valueType,unit?,forms[1..16]}`. It references one selected fact/attribute, uses its registry type/unit, and contains sorted unique exact EN renderings produced by the shared pure number/unit/ordinal/band functions. A relation row is exactly `{claimId,polarity,temporalFrame,forms[1..16]}` and resolves one selected claim. Connectives and forbidden lexemes are sorted unique normalized EN strings from the selected audited family/card and global verifier registry. `surfaceLexiconHash` hashes this exact object; aliases are separately covered by `bundleHash`.

The authored/Qwen worker and deterministic verifier receive this bundle and no live FactLedger, FactView, roster, config or observer reference. On `REALIZATION_SUCCEEDED`, the actor first token-checks, then requires the current FactView to contain canonical-equal, currently valid copies of every bound fact and the same occurrence/lineage/episode revision before verification/commit. Any absence or difference is `freshness_stale`; the verifier never rebuilds a lexicon from newer truth. A compiler bound/reference failure is `realization_input_invalid`, fails closed and consumes the current cycle attempt; validated catalogs/registries must make it unreachable for a valid FactView.

The exact compiled prompt, common request/result schemas, OpenAI-compatible SSE request/response subset, actor deadline, warm-up request, latency equations and `llm-attempt/2` tape payload are frozen in [the Qwen transport contract](qwen-transport-contract.md). That file is normative rather than an implementation example. The schema loader imports those four DTO definitions into the same neutral contracts package; transport code may not widen them.

## TTS utterance and callback protocol

The actor creates one immutable backend request only after a narrative realization has passed token, freshness, semantic and technical validation, or after a manual request has won its admission latch. `TtsUtterance` is exactly:

```text
schemaVersion, utteranceId, utteranceOrdinal, sourceKind, funnel?,
planId?, opportunityId?, episodeId?, manualRequestId?, text, textHash,
language, backend, backendGeneration, configGeneration,
effectiveConfigHash, configApplySequence, voice?, rate, steps?,
audioDevice?, duckInput?, duckRatio, duckFadeMs, maxSeconds,
dispatchedMonoMs, requestHash
```

`utteranceOrdinal` is positive and process-monotonic; `utteranceId` is the canonical ASCII `utt:<processInstanceId>:<utteranceOrdinal>`. `sourceKind` is `narrative|manual`. Narrative requests require `planId`, `episodeId` and the BeatPlan funnel advanced with this utterance ID, carry the BeatPlan's nullable `opportunityId`, and require null `manualRequestId`; manual requests require `manualRequestId` and null narrative IDs/funnel. Text is normalized EN with no control characters: 1..512 characters for narrative and 1..400 for manual. `textHash` hashes the exact normalized text. Language is constant `en`.

`backend` is the already resolved concrete `sapi|espeak|supertonic`, never `auto`; `backendGeneration` is positive and names the successful preflight used by this dispatch. `configGeneration`, `effectiveConfigHash` and `configApplySequence` are the matching ConfigLedger snapshot after `next_utterance`. Voice/device/duck strings are normalized nullable values whose empty config form becomes null. `rate` is always present; `steps` is present only for SuperTonic. `duckRatio` and `duckFadeMs` are always snapshotted even when `duckInput` is null. Narrative `maxSeconds` equals the BeatPlan value; manual uses the `next_plan_or_manual` global value. `requestHash` is the canonical hash of every preceding field, including actual sensitive values; ordinary status/tape projection applies the frozen redaction policy and never substitutes a redacted hash input.

The actor gives the TTS worker an opaque process-local dispatch token exactly `{utteranceId,utteranceOrdinal,backendGeneration,dispatchGeneration}`. `dispatchGeneration` is positive and process-monotonic across TTS submissions; cancellation references the same value and never allocates a replacement token. The token is callback identity, not a replay identity or public credential. The worker may return only this `TtsCallback`:

```text
schemaVersion, callbackId, kind, utteranceId, utteranceOrdinal,
backend, backendGeneration, dispatchGeneration, workerSequence,
observedMonoMs, detailCode?
```

Kind is `playback_accepted|completed|interrupted|failed`. `workerSequence` is positive and starts at 1 per dispatch token. One worker/token may emit at most one `playback_accepted` followed by at most one terminal callback; `failed` may instead be the sole pre-acceptance callback. The worker must enqueue callbacks in increasing sequence through the one NarrativeMailbox. Completion/interruption/failure after acceptance therefore has sequence 2; any missing, repeated, decreasing or otherwise illegal transition is `tts_protocol_violation`. `callbackId` is `ttscb:<utteranceId>:<workerSequence>`. `observedMonoMs` is same-process monotonic metadata no earlier than dispatch and nondecreasing per token; reducer order, deadlines and state changes use actor dequeue time, never trust callback time as ordering authority. The command mapping is exact: the four callback kinds become `PLAYBACK_ACCEPTED`, `SPEECH_COMPLETED`, `SPEECH_INTERRUPTED` and `SPEECH_FAILED` respectively, with the complete callback as payload. `detailCode` is null for accepted/completed, `backend_cancelled` for interrupted, and one of `backend_rejected|backend_process_exit|backend_audio_error|backend_unavailable` for failed; exception text is never admitted.

Callback acceptance requires an exact current dispatch token before inspecting its kind. Stale tokens and canonical-identical duplicate callback IDs are audited no-ops; reuse of a callback ID with different canonical content is `tts_protocol_violation`. The actor writes exactly one terminal result per utterance; a watchdog may synthesize that actor terminal result without fabricating a TtsCallback. Once terminalized, every later worker callback is a no-op. Playback acceptance is valid only from `committed`; a terminal-before-acceptance `failed` is the only legal direct terminal there. Completion/interruption before acceptance or any second acceptance is a protocol violation: it immediately quarantines that backend generation against new work, retains the current token only for bounded cancellation cleanup, and cannot consume an unaccepted narrative opportunity. Acceptance arriving after the actor has already requested cancellation is a stale race no-op rather than a protocol violation, because cancellation and backend acceptance may cross outside the mailbox.

The TTS worker owns ducking as part of the same dispatch token. When `duckInput` is present it attempts the configured duck before acknowledging playback acceptance and issues exactly one idempotent best-effort restore operation on every terminal/cancel path; both operations are bounded inside the existing start/stop watchdogs. Actual OBS attenuation/restoration cannot be guaranteed when OBS is unavailable. Duck failure records `duck_unavailable` and may continue audio, but never crashes or delays the main loop beyond the same watchdog; playback acceptance still means backend acceptance, not proof of acoustic output or successful ducking.

Every utterance produces one final `speech-exposure/2` payload, even when it never reached playback acceptance:

```text
utteranceId, sourceKind, planId?, opportunityId?, episodeId?, manualRequestId?, funnel?,
requestHash, textHash, backend, backendGeneration, effectiveConfigHash,
configApplySequence, dispatchedMonoMs, acceptedMonoMs?, terminalMonoMs,
terminalReason, opportunityConsumed, exposureWeight, duckStatus,
callbackIds[0..2]
```

IDs and source nullability match the TtsUtterance. `acceptedMonoMs` is null exactly when no valid acceptance reduced. `opportunityConsumed` is true exactly for accepted narrative speech; manual is always false. `exposureWeight` is 1 for accepted narrative speech and 0 otherwise. `duckStatus` is `not_configured|applied|unavailable|restore_unconfirmed`; it reports the strongest terminal outcome without claiming physical state. Callback IDs are the unique accepted callback IDs in worker sequence order and exclude rejected stale/duplicate inputs; a watchdog-only terminal may therefore have no terminal callback ID. The payload contains neither raw text nor sensitive voice/device values. Its record envelope and the utterance request hash retain config/replay provenance.

`terminalReason` is exactly `tts_failed_before_acceptance` when dispatch/callback fails before acceptance, otherwise one of the speech-terminal registry IDs. A protocol violation uses `tts_protocol_violation` regardless of acceptance; the separate accepted/consumed fields preserve its exposure semantics.

## ConfigLedger

The validated desired configuration and currently effective mixed-boundary configuration are distinct. ConfigLedger publishes exactly:

```text
schemaVersion, desiredGeneration, desiredHash, effectiveHash, applySequence,
effectiveValues, pendingChanges[0..128], acceptedMonoMs
```

`desiredGeneration` is process-monotonic and increments for every successfully parsed full commentary configuration; invalid input creates a diagnostic but no generation. `applySequence` is process-monotonic and increments for each nonempty atomic effective group. Desired/effective hashes use the global canonical JSON rule over the real normalized values of all public commentary keys with defaults materialized; redaction never changes identity or makes two configurations hash-equivalent. `effectiveValues` is the full internal typed map, not exposed through HTTP or ordinary logs. Each pending change is exactly `{key,boundary,desiredGeneration}` sorted by key. Boundary is one of `next_stream|next_director_pass|next_silence_deadline|next_beat_plan|next_plan_or_manual|next_request|next_utterance|next_cancellation|next_record|next_rotated_file|next_rotation|next_writer_deadline|next_shutdown`. The public config table is the sole key-to-boundary registry; aliases such as “soon” or “restart required” are not runtime states.

ConfigLedger is a narrow cross-cutting coordinator, not state owned by NarrativeRuntime, DetectorBank or the tape writer. Only its atomic install/compare/apply operations mutate desired/effective/pending state. It serializes concurrent boundary applications by `applySequence`; callers receive one immutable snapshot and cannot mutate it. NarrativeRuntime owns narrative boundaries, the stream/config coordinator owns `command|next_stream` before StreamTimeline allocates a run and DetectorBank creates its first FeatureFrame, and the tape writer owns record/file/rotation/writer-deadline boundaries. This avoids an upstream dependency on commentary while keeping one total config order.

`CONFIG_UPDATE` carries either one already parsed full candidate plus bounded diagnostics, or an invalid diagnostic. A valid candidate is installed in ConfigLedger in accepted generation order. The stream/config coordinator applies the `command` group, and, when this creates a narrative run, `next_stream`, before asking StreamTimeline for the coherent enable/disable projection. It atomically admits `CONFIG_UPDATE` followed immediately by the matching protected `APPLY_CONTEXT_BATCH`; no other mailbox item can interleave. If there is no timeline transition it admits only `CONFIG_UPDATE`. The actor caches the installed snapshot and launches required component preflights; only the following context batch changes narrative run/episode/speech state. An invalid candidate installs no generation but uses the same ordered bundle to close any automatic run as `disabled_invalid_config`; it retains the last valid desired/effective maps only for diagnostics and manual TTS, and cannot admit new automatic work until a later valid enabled candidate. If the two-item bundle cannot fit, the mailbox recovery barrier carries both the config diagnostic and latest coherent projection as one safety effect. Scene switching, OBS control and upstream telemetry continue.

For a valid candidate, pending state is recomputed wholesale from every desired value unequal to its effective value and every row receives the new desired generation; this replaces the prior pending set, including reverted keys. At a named boundary its owner asks ConfigLedger to apply exactly all pending keys naming that boundary as one sorted atomic group. The operation increments `applySequence`, recomputes the full effective hash and publishes one `config_applied` transition before the new immutable snapshot becomes visible. Boundaries do not implicitly drain other groups: an operation that crosses several boundaries invokes them in semantic order and therefore sees each completed group. Existing BeatPlans, requests, utterance tokens, detector runs, tape records/files and deadlines never mutate. The immutable object created after a boundary snapshots the resulting effective hash and apply sequence. Next-stream detector/capacity/identity values apply before the new run manifest and first projection; failure leaves commentary disabled for that run rather than mixing old/new values.

The `config_applied` payload is exactly `{applySequence,desiredGeneration,boundary,changedKeys[1..128],effectivePatch[1..128],oldEffectiveHash,newEffectiveHash}`. Its boundary is `process_start|command` or one of the pending boundary values above. `process_start` records the fully defaulted initial effective map when tape is already enabled; otherwise the first later manifest is the initial recorded snapshot. `command` records `commentary.enabled`. `changedKeys` is sorted and unique and exactly matches the sorted keys of `effectivePatch`; a no-op boundary emits no record. Each patch entry is exactly `{key,value}` for a replay-safe scalar/list or `{key,redacted:true}` for a sensitive value. The fixed sensitive set is `commentary.driver_name`, `commentary.driver_nickname`, `commentary.llm.base_url`, `commentary.tts.voice`, `commentary.tts.audio_device`, `commentary.tts.duck_input` and `commentary.tape.output_dir`; all other v2 public values, including every numeric detector/director/cadence threshold, are recorded with their exact typed value. A redacted projection cannot recompute the full config hash or regenerate secret-dependent surface text and must use the recorded completion/exposure for those steps.

When recording is enabled, ConfigLedger atomically attempts to admit this unfilterable transition through the tape writer's reserved control barrier before exposing the new snapshot. Success orders all old-snapshot records before the barrier and all newly admitted records after it. Barrier saturation/failure never blocks a config boundary or the main loop: ConfigLedger still publishes the new snapshot, the out-of-queue loss accumulator stores the missing apply sequence plus old/new hashes under `config_transition_lost`, tape health becomes degraded/incomplete, and the next record's higher sequence makes the gap detectable. That tape cannot claim deterministic replay across the gap. Every newly opened or rotated tape file snapshots the then-current desired generation/hash, effective hash, apply sequence and redacted replay projection in its manifest; subsequent records make later effective changes replayable.

LLM and TTS resource construction is generation-tagged and never performed in the actor. Enabling Qwen or a valid desired LLM endpoint/model/warmup change starts one replacing preflight; `warmup=true` includes a bounded model request, while false ends after client construction. A valid change to TTS backend, voice, steps or audio device starts one replacing backend preflight. Applying the config values is not readiness: while the matching desired component generation is pending or failed, Qwen-backed beats respectively all new automatic/manual TTS admissions are ineligible, while authored planning and unrelated components continue. A successful current-generation `COMPONENT_HEALTH_CHANGED` makes that effective component generation usable on the next normal boundary; stale completions are no-ops. It never mutates in-flight work or itself starts planning/speech. There is no fallback to an older effective component generation after the newer values cross their boundary.

## Tape envelope

One NDJSON file begins with one manifest record and then tape records. A file is scoped to one `(processInstanceId, streamEpoch-or-null)`; records from two narrative runs never share a file. Rotated continuations repeat the manifest with the same process/broadcast/stream identity and a new file ordinal. Pre-run process/health records may use a separate `streamEpoch=null` file. Narrative-run close (confirmed OBS end, commentary disable or shutdown) writes a trailer and closes the current file; re-enable opens a new manifest with the new stream epoch.

Manifest fields:

```text
schemaVersion, recordType="manifest", processInstanceId, processStartedAtUtc,
processMonotonicOriginMs=0, appVersion, gitRevision?, platform,
broadcastEpoch?, streamEpoch?, fileOrdinal, openedAtUtc, catalogVersion, catalogHash,
desiredConfigGeneration, desiredConfigHash, effectiveConfigHash, configApplySequence,
effectiveConfigProjection[1..128], enabledPurposeChannels,
redactionPolicy, historyComplete, detectorParameterSnapshots[0..128], previousFileHash?
```

Each detector parameter snapshot is exactly `{parameterSnapshotId,detectorId,detectorVersion,detectorConfigHash,parameters}`. IDs/hashes resolve registries, parameters contain only that detector's exported typed values in sorted parameter-ID order, and snapshots sort by detector ID. A rotated continuation repeats the identical array; config requiring a new snapshot is deferred to its declared next-stream boundary rather than changing a file/run in place.

Record fields:

```text
schemaVersion, recordId, recordType, processInstanceId, broadcastEpoch?, streamEpoch?,
reducerSequence?, recordedMonoMs, recordedAtUtc?, purposeChannel,
recordPriority, tapeChannel?, correlationIds[0..8], effectiveConfigHash,
configApplySequence, payloadSchemaVersion, payload
```

Purpose channel is `flow|llm_eval|detector_tuning`; priority is `sample|normal|critical`. Record type is one of `context_applied|feature_frame|detector_observation|event_candidate|narrative_event|fact_change|episode_change|opportunity_change|director_decision|llm_attempt|speech_exposure|config_applied|health_change|mailbox_gap|drop_notice|manifest_trailer`. `payload` must validate against its named schema; `feature_frame` payload is exactly FeatureFrame and `event_candidate` payload is exactly EventCandidateTap. The writer records ordered actor facts/decisions with reducer sequence and unordered upstream feature/detector/candidate observations without one. Prompt/completion contents obey capture policy and redaction; hashes and latency metadata remain.

Every record snapshots one ConfigLedger `effectiveConfigHash/configApplySequence` pair in its envelope; a `config_applied` record names its proposed new pair. Within one open file, `config_applied` is the only forward transition between effective snapshots; while recording is disabled, the next manifest is authoritative for otherwise unrecorded transitions. Upstream feature/detector payloads additionally carry their detector config hash and parameter snapshot reference. A rotated continuation may therefore have different desired/effective manifest hashes from the prior file, but keeps the same run identity and detector parameter snapshot array; replay starts from each manifest snapshot and reduces later `config_applied` records in file/apply-sequence order.

Priority is derived, never caller-selected: periodic negatives/background samples are `sample`; normal context/fact/event/opportunity/decision and nonterminal LLM records are `normal`; lifecycle/reset/mailbox gaps, config applications, health failures, speech terminals, verifier rejections and every record required by an enabled `tuning.required` detector are `critical`. Manifest/trailer are file framing and bypass the record queue. `drop_notice` is synthesized from the writer's bounded out-of-queue loss accumulator and is critical.

At capacity, an incoming sample is dropped; normal first evicts oldest sample else is dropped; critical first evicts oldest sample, then oldest normal. If all queued records are critical, the incoming critical record is represented in the loss accumulator and writer health becomes degraded. Loss of any required-detector record additionally emits the out-of-queue CaptureHealthNotice frozen in the actor contract; the composition coordinator, never TapeWriter or NarrativeRuntime, disables only the affected experimental detector and atomically publishes its health/context bundle. The accumulator stores only counts by record type/priority/reason plus first/last monotonic/reducer sequence, capped by the closed registries; it is flushed as the next possible `drop_notice` and always copied into the trailer/operational error path. Tape loss never blocks or mutates world/narrative truth directly.

Trailer payload contains final record/file hash, counts by record/purpose/tape channel, drops by reason, last reducer sequence, shutdown/rotation reason and `complete`. A missing/invalid trailer makes that file incomplete but does not make prior valid NDJSON records unreadable.

## Frozen director relation IDs

Decision records describe the selected candidate's deterministic relationship to its routed/focused episode. `null` means no episode relationship applies. The closed non-null vocabulary is:

| ID | Meaning |
| --- | --- |
| `opens_episode` | accepted event opens its routed episode |
| `updates_active_episode` | accepted event materially updates the same active episode |
| `resolves_active_episode` | accepted event supplies the correlated outcome/closure |
| `continues_focused_episode` | successor or explicit episode beat continues the focused episode |
| `conflicts_with_focused_episode` | candidate's routed episode conflicts with the focused episode |
| `independent_of_focused_episode` | candidate's routed episode is independent of the focused episode |

## Frozen reason IDs

Reason IDs are machine values; operator messages are separate and bounded. Their full identity is `(reasonDomain, reasonId)`: an object/state supplies the domain through its schema, while generic health/decision records carry both fields explicitly. The same ID may occur in two domains only with the same plain-language meaning, but consumers never dispatch on an unscoped free string. The initial registry is:

| Domain | IDs |
| --- | --- |
| director selection | `highest_valid_candidate`, `active_story_continuation`, `related_event_update`, `higher_urgency_switch`, `switch_margin_met` |
| director silence/reject | `no_candidate`, `no_episode_route`, `below_threshold`, `hard_guard_failed`, `source_guard_failed`, `cadence_blocked`, `fatigue_blocked`, `attempt_suppressed`, `planning_cycle_exhausted`, `episode_capacity_rejected`, `tts_unavailable`, `stream_inactive`, `context_unknown` |
| event arbitration | `accepted`, `pit_cycle`, `cooldown`, `lower_priority`, `unmatched_exit`, `unmatched_update`, `overlay_disabled`, `invalid_candidate`, `event_candidate_protocol_violation` |
| timeline transition | `broadcast_started`, `broadcast_ended`, `broadcast_unknown`, `broadcast_resumed`, `narrative_enabled`, `narrative_disabled`, `attached_live`, `process_recovery`, `session_started`, `session_ended`, `session_restarted`, `session_superseded`, `session_suspended`, `session_resumed` |
| opportunity terminal | `consumed_playback_accepted`, `expired_ttl`, `superseded_revision`, `invalidated_truth`, `invalidated_occurrence`, `closed_stream`, `commentary_disabled`, `evicted_capacity` |
| episode terminal | `outcome_observed`, `natural_exit`, `target_changed`, `composite_exited`, `occurrence_ended`, `occurrence_superseded`, `stream_ended`, `commentary_disabled`, `evidence_invalidated`, `capacity_evicted` |
| attempt terminal | `realization_input_invalid`, `realization_timeout`, `realization_transport`, `realization_invalid_response`, `realization_output_oversize`, `realization_cancelled`, `realization_protocol_violation`, `semantic_rejected`, `freshness_stale`, `replaced_precommit`, `tts_failed_before_acceptance`, `stale_worker_token` |
| verifier rejection | `empty`, `too_long`, `sentence_count`, `token_count`, `non_en_contract`, `meta_output`, `unknown_fragment`, `unknown_entity`, `actor_reversed`, `actor_ambiguous`, `number_unbound`, `number_mismatch`, `unit_mismatch`, `polarity_mismatch`, `tense_mismatch`, `required_missing`, `forbidden_claim`, `extra_claim`, `causal_inference`, `intent_inference`, `emotion_inference`, `medical_inference`, `prediction_as_result`, `result_as_prediction`, `unsupported_certainty`, `unsafe_negation` |
| TTS backend detail | `backend_rejected`, `backend_process_exit`, `backend_audio_error`, `backend_cancelled`, `backend_unavailable` |
| detector transition | `enter_started`, `enter_confirmed`, `enter_lost`, `material_band_changed`, `material_delta_met`, `update_rate_limited`, `clear_started`, `clear_cancelled`, `clear_confirmed`, `target_changed`, `occurrence_reset`, `stream_reset`, `unsupported_stage`, `identity_conflict`, `feature_unknown`, `required_capture_lost` |
| speech terminal | `completed`, `interrupted_stream_end`, `interrupted_occurrence_reset`, `interrupted_commentary_disabled`, `interrupted_truth_invalidated`, `interrupted_shutdown`, `tts_failed_after_acceptance`, `tts_start_timeout`, `tts_playback_watchdog`, `tts_stop_timeout`, `tts_protocol_violation` |
| mailbox/tape health | `mailbox_overloaded`, `mailbox_evicted_update`, `mailbox_recovery`, `mailbox_history_incomplete`, `deadline_admission_skipped`, `tape_queue_drop`, `tape_write_failed`, `tape_flush_timeout`, `config_transition_lost`, `capture_unavailable` |
| config/runtime health | `disabled_by_config`, `disabled_invalid_config`, `legacy_key`, `starting`, `ready`, `component_preflight_pending`, `component_preflight_failed`, `component_unavailable`, `admission_timeout`, `session_identity_conflict`, `session_plan_conflict`, `fact_capacity_evicted`, `fact_capacity_exhausted`, `obs_state_unknown`, `history_incomplete`, `duck_unavailable` |

Adding a diagnostic reason is additive only inside the same version when no consumer exhaustively switches on it; implementation code must still use a registry constant. Removing, renaming or changing terminal meaning requires a schema version change.

## Registry prerequisites

Before schemas can be implemented, issue #236 must materialize machine-readable registries for:

- all 60 current identifier dispositions plus new internal event/command kinds;
- fact predicates/attributes with scalar type, units, legal actors/scopes and unknown semantics;
- feature IDs/units/sample quality;
- story, beat, realization-family, relation and `tapeChannel` IDs;
- reason IDs above and detector transition reasons.

The branch-freeze projection is `machine/freeze-registry.json`, generated and checked by `machine/build_freeze_registry.py`. The closed DTO bundle is `machine/dto-contracts.schema.json`, generated by `machine/build_dto_schemas.py`; `machine/beat-catalog.json`, `machine/successor-graph.json`, `machine/config-contract.json` and `machine/api-contract.json` plus their schemas/goldens/mutation checkers freeze the exact beat, continuation, public configuration and HTTP inputs. Non-local comparisons are named by mandatory `x-irswitch-invariants` for implementation validation. The planning copies are not runtime compatibility files, but implementation must promote byte-equivalent registry/schema artifacts into `src/irswitch/contracts/schemas/v2/`, package them and test their hashes. The registry checker also pins `machine/v4-event-envelope.golden.json` to master baseline `0ce75d4`, rejects narrative-only top-level fields and exercises the current V4 freeze/thaw round-trip.

The exact human-review candidate for fact predicates, scalar/unit types, claim allowlists, feature IDs and `tapeChannel` taxonomy is [the fact/feature registry](fact-feature-registry.md). Machine schemas may encode it, but may not silently add a predicate, attribute, enum literal, feature or channel.

The loader rejects duplicate/case-colliding IDs, unknown references, unit mismatch, undeclared attributes, unsafe array/object bounds and catalog hashes built with a different registry version.

## Closure fixtures

The design gate remains closed until branch-only fixtures prove:

1. master EventEnvelope canonical JSON/hash is unchanged;
2. every DTO accepts one complete golden and rejects unknown fields, NaN/infinity, bad units, bad enums, missing required fields and illegal nulls, including RealizationBundle fact/actor/surface/hash mismatch;
3. all 64 beats and 60 dispositions resolve through the registries;
4. tape manifest/record/trailer round-trip and detect truncation/hash mismatch;
5. API fact bindings round-trip through the same AtomicFact schema rather than a looser duplicate;
6. all public/status/decision terminal reasons exist in the frozen registry.
7. all 50 static config keys, two detector templates, 14 apply boundaries and 13 legacy dispositions match the public table, and F36 replays without cross-boundary drain or old-generation backend fallback.
