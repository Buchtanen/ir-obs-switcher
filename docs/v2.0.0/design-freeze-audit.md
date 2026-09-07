# v2.0.0 narrative runtime — pre-implementation design-freeze audit

**Status:** runtime implementation gate is closed until the checklist in this document and issue #235 is complete
**Baseline:** `master@0ce75d4`
**Development branch:** `codex/commentary-story-flow-spec`
**Baseline evidence:** 1,364 pytest tests passed on 2026-09-07 using the existing project virtualenv
**Static baseline evidence:** Ruff passed, Black would leave 322 files unchanged, Mypy passed 174 source files
**Delivery:** one atomic breaking-change PR after the complete branch passes release gates

This is a planning artifact for the v2 branch. It must not be included in the final diff to `master`.

## Current gate verdict

**NOT READY FOR RUNTIME EDITS.** The architecture is feasible, but the unchecked artifacts below are real blockers, not implementation details. Complete disposition, public config/API, actor-transition and semantic-schema contracts now exist as review candidates. Machine-readable schemas/golden/model-based fixtures and automated cross-document validation do not. Issue #235 must remain open until every blocking artifact is reviewed, committed and pushed.

Master cross-checks that changed or sharpened the design:

- `events/envelope.py` is already the shared V4 overlay wire, so a commentary-specific envelope revision would create an unnecessary cross-product break.
- `events/async_fanout.py` already supplies the bounded commentary mailbox and recovery slot; adding a second reducer transport would duplicate ordering and overflow semantics.
- `EventManagerV2` publishes only accepted events, so tuning kick-rate requires a separate pre-arbitration observation tap.
- `overlay/session.py` currently permits partial keys and TrackID fallback while `iracing/session_context.py` requires `(SubSessionID, SessionNum)`; v2 must use the stricter single identity.
- `RunClock` already implements the useful `>5 s` and `>=100 ms` rewind guard; its behavior moves under StreamTimeline rather than being independently reimplemented.
- `BroadcastClock` already owns a two-second output-flicker debounce and epoch; StreamTimeline consumes it instead of inventing a second stream clock.
- Current TTS marks story “speaking” before backend playback and only SuperTonic has a pre-play hook. The v2 acknowledgement contract therefore requires changes in every supported backend wrapper.
- Master uses `STREAM_START`, while the proposal uses lifecycle `STREAM_STARTED`; the canonical event-ID registry must explicitly map/remove the old name rather than allowing both.
- The legacy graph's 50 event types are not the full master vocabulary. The audited union is 60 identifiers; the disposition candidate and exact 64-beat baseline live in `event-beat-disposition.md`.

## Frozen delivery model

- Runtime work is implemented sequentially in this branch; no partial family or planning-doc PR goes to `master`.
- Internal vertical slices and shadow comparison are development checkpoints, not releasable compatibility modes.
- The final branch contains one authoritative v2 runtime. Temporary legacy/shadow adapters are removed before the final PR.
- The final PR is human-reviewed, uses `semver:major` and contains `BREAKING CHANGE:` plus config/API migration notes.
- Rollback means restoring the latest v1 release/binary and its saved configuration, not flipping a runtime family flag.
- A child issue may close before merge only after its implementation and tests are committed and pushed on this branch and its dev diary names the immutable commit SHA and evidence.
- Closing an issue does not mean its code reached `master`. Issue #279 and umbrella #234 remain open through final integration and release disposition.
- Planning-only files excluded from the final PR are enumerated in `final-pr-exclusion-manifest.md`; the manifest itself and temporary links from root/current-behavior docs are also excluded.
- Actual v2 behavior, config, API and migration documentation is mandatory in the final PR.

## Resolved contract conflicts

| Area | Weakness found | Frozen resolution |
| --- | --- | --- |
| Delivery | Spec assumed per-family strangler rollout to master | Incremental branch development, atomic final breaking cutover |
| Rollback | Runtime legacy flag conflicted with one-runtime v2 | Roll back the release/binary and v1 config; remove dual runtime before PR |
| Event priority | Existing envelope priority could be confused with speech priority | `EventEnvelope.priority` stays transport/event salience; speech `base_priority` belongs to EventSpeechPolicy |
| Event expiry | Existing wire `expiresAt` could be reused accidentally | Wire/presentation expiry and monotonic EventOpportunity expiry are different fields and clocks |
| Catalog naming | `events/event_catalog.py` already means overlay presentation mapping | New names are `event_taxonomy`, `detector_catalog` and `commentary/narrative_catalog`; no second generic EventCatalog |
| Tape routing | Purpose channel and event family were conflated | `flow/llm_eval/detector_tuning` are capture purposes; mandatory `tape_channel` is the event taxonomy dimension |
| Accepted-event ordering | Priority queue could mutate truth order | Reducer consumes FIFO/recorded sequence; priority is used only after state reduction |
| Concurrent callbacks | Event and speech completion could race without replay order | Single NarrativeRuntime actor assigns and records total `reducer_sequence` |
| Async ownership | Workers could mutate director state | Only the actor mutates narrative state; Qwen/TTS/tape return immutable commands |
| Queue count | Separate external and worker-result queues would make interleaving ambiguous | Evolve/replace commentary EventSubscription with one bounded NarrativeMailbox preserving its overflow/recovery semantics; fanout adapters and owned workers post to that same mailbox |
| State ownership | NarrativeRuntime was described as owner of upstream timeline/fact/detector truth | StreamTimeline owns occurrence/lineage, FeatureEngine owns windows, DetectorBank owns detector FSM/current derived truth; the actor owns an immutable fact projection plus episodes/opportunities/exposure/speech orchestration |
| Sequence names | EventEnvelope sequence, fanout stream sequence and reducer order could be conflated | Preserve session-scoped overlay `EventEnvelope.sequence`; external narrative order is `(fanout_stream_sequence, source_ordinal)`; actor `reducer_sequence` is authoritative for decision replay |
| Prepared speech | Event waiting could become a renamed sentence queue | Opportunity contains meaning/scheduling metadata only; BeatPlan/text is just-in-time and single-flight |
| Opportunity consumption | Selection, commit and exposure had no precise boundary | Reserve at planning, consume at the software-observable `PLAYBACK_ACCEPTED` boundary (public lifecycle name `SPEECH_STARTED`); failure before backend acceptance releases reservation, later failure/interruption stays consumed |
| Opportunity updates | Multiple revisions could all be narrated late | Same correlation update supersedes older revision unless catalog marks distinct outcomes |
| Post-beat behavior | Continuation versus new event was underdefined | One candidate set; hard gates, urgency, score and `switch_margin`; otherwise successor or silence |
| Story relation | Relevance could drift into embeddings/LLM | Relation is deterministic catalog routing plus occurrence/correlation identity |
| Scene membership | Raw OBS scene names would couple commentary to deployment | Beat uses normalized `broadcast_context` with `ignore/prefer/require`; logic owns raw scene mapping |
| Session vocabulary | Internal `qualifying` differs from iRSDK `Qualify` and overlay mode | One adapter maps external values; internal enum is lower-case; unsupported stages remain explicit |
| Stream authority | iRacing and OBS could both own stream lifecycle | OBS output owns stream edges; iRSDK owns session identity/stage |
| OBS disconnect | Disconnect could create a false stream end | Disconnect is `unknown`; only confirmed not-streaming ends a stream |
| Process restart | History restoration was unspecified | Without a verified checkpoint, create a new narrative epoch and forbid pre-restart historical claims |
| Historical memory | “Remember everything” conflicted with bounded memory | Active ancestry is never evicted; old detail compacts to safe summaries and full audit remains on tape |
| Graph safety | Analyzer was optional although malformed cycles are runtime risk | Loader referential/reachability/SCC barrier checks are blocking; rich analyzer/3D viewer remains optional |
| Random replay | Qwen and global RNG could violate determinism claims | Deterministic authored seed; decision replay uses recorded Qwen completion, model eval compares semantics/distribution |
| Config reload | Mid-stream catalog/threshold changes could reinterpret state | Taxonomy/catalog/detectors/capacities freeze per stream; selected operational settings apply only at explicit generation boundaries |
| Invalid config | Breaking config could crash the whole service | Disable commentary with explicit health reason; scene switching continues |
| API impact | Spec called API optional despite required diagnostics | Commentary API payload becomes explicit `commentary-runtime/2`; API docs/tests are mandatory |
| Language | Overlay locale could silently drive speech | v2 speech/validation is fixed EN and independent of overlay locale |
| LLM fallback | Failure policy could retry or repeat a topic | One attempt per beat/revision; discard and re-arbitrate; no repair or same-beat fallback |
| Detector tuning | Recorder failure conflicted with fail-soft main loop | Disable only a required experimental detector; never block or crash the race loop |
| Overlay compatibility | A proposed EventEnvelope v2 would make a commentary refactor break the overlay wire | Keep the accepted V4 EventEnvelope/wire unchanged; a narrative adapter creates an internal versioned `NarrativeEvent` command and resolves policy from catalogs |
| Kick-rate evidence | Commentary sees only events accepted by EventManager, so suppressed detector activity was invisible | Add a read-only pre-arbitration `DetectorObservation` tape tap; only accepted events enter the narrative reducer |
| TTS start | “First audio frame” is not observable uniformly for SAPI, eSpeak and SuperTonic | Each backend must acknowledge playback acceptance exactly once; physical speaker output is explicitly outside the contract |
| Mid-speech priority | Critical-event interruption policy had no closed rule | Normal race events never interrupt an utterance; stream/session/reset invalidation, explicit commentary disable or shutdown may cancel it, and the new event then competes from its still-live opportunity |
| Required tuning | Default-off tape plus `tuning.required` could disable production commentary unexpectedly | Released production detectors use `none` or `optional`; `required` is allowed only for an explicitly enabled experimental detector with successful recorder preflight |

## Frozen ownership and dependency direction

```text
iracing extraction
  → immutable normalized snapshot
race RaceState/observer
  → immutable race snapshot
events FeatureEngine + FactLedger + DetectorBank + event taxonomy
  → immutable FeatureFrame/FactView
  → unchanged immutable accepted V4 EventEnvelope
  → narrative input adapter + catalog lookup → immutable NarrativeEvent command
commentary NarrativeRuntime actor
  → immutable timeline/fact projections
  → episodes/opportunities/exposure/director/speech orchestration
  → immutable BeatPlan
commentary Qwen/authored realizer → verifier → commit gate → speech worker

logic StreamTimeline → immutable timeline snapshot/commands and normalized broadcast context DTO
server → construction/wiring/status projection only
overlay and commentary remain peer consumers of accepted events
```

Forbidden dependencies:

- `events/` importing commentary policy or TTS;
- `commentary/` reading mutable RaceObserver or private OBS client state;
- `logic/` importing commentary;
- `server/` mutating component-private state;
- overlay presentation catalog defining speech priority, TTL or story relationships.

Neutral immutable DTOs may live in the producing layer or a narrow contracts module that imports no consumer.

## Frozen scheduling semantics

### Input mailbox

- Truth events are reduced in accepted/recorded order, never priority order. External accepted order is `(fanout_stream_sequence, source_ordinal)`; all external and internal commands receive one total `reducer_sequence` on dequeue.
- NarrativeMailbox is the sole actor inbox. Event fanout uses a narrow adapter into it; Qwen/TTS/timer completions self-post immutable commands to the same inbox. There is no second result queue to merge nondeterministically.
- Protected reset/config/speech/shutdown commands cannot be silently dropped.
- Only same-correlation ACTIVE/UPDATE revisions may coalesce.
- Mailbox recovery cancels uncommitted work, reconstructs current truth from the latest immutable context and records lost history; it never invents missed opportunities.

### EventOpportunityQueue

- Initial capacity: 128, marked `estimated` but schema/range fixed before implementation.
- Ordering: valid candidates compare urgency, effective score, then oldest source sequence and stable IDs.
- Lifecycle: `pending → reserved → consumed` or `expired/superseded/invalidated/evicted`.
- Consumption: backend playback acceptance (`PLAYBACK_ACCEPTED`, exposed as `SPEECH_STARTED`). SuperTonic acknowledges after `sd.play` accepts the stream; SAPI/eSpeak wrappers must provide an equivalent one-shot acknowledgement after process/backend acceptance. This is an auditable software boundary, not a claim that a physical speaker emitted a sample.
- A failed beat suppresses only `(beat_id, episode_revision)` and leaves the underlying opportunity pending until TTL.
- Overflow removes expired/superseded, then the lowest noncritical candidate; all-critical overflow evicts the oldest with an audit record.
- An in-flight utterance is not preempted by another racing event. Only a stream/session/run reset, explicit commentary disable, shutdown, or commit-truth invalidation may cancel it. A newly urgent event remains eligible only while its opportunity TTL is live.

### Post-beat arbitration

```text
valid event opportunities
∪ valid successors of the last spoken beat
∪ other valid episode beats
∪ valid filler opportunities
→ hard gate
→ urgency + score + switch policy
→ one BeatPlan or SILENCE
```

The active story is not a lock. A related event can update or resolve it. An independent/conflicting event changes story only if its urgency is greater or its score exceeds continuation by `switch_margin`.

## Frozen stream/session failure semantics

- OBS streaming state owns stream boundaries; OBS disconnect is unknown, not ended.
- iRSDK `SessionInfo.Sessions[SessionNum].SessionType` owns current session type.
- Start in the middle of a session sets `history_complete=false`; missing prior stages are never inferred.
- Session restart/rewind creates a new occurrence and preserves active ancestors according to lineage rules.
- iRacing disconnect suspends current truth but does not end the OBS stream.
- Process restart without verified state persistence creates a new narrative stream epoch; v2.0.0 does not rehydrate live state from tape.
- `Warmup`, `Test` and unknown session types are unsupported, not aliases for Practice.

## Frozen public compatibility surface

- Final v2 is EN-only.
- Config sections and removed v1 keys are defined in specification §20.
- Commentary API v2 and removed `/api/commentary/assignments` are defined in §20.1.
- Old commentary config produces migration warnings; invalid v2 commentary config disables only commentary.
- No runtime compatibility loader for sequence-graph v1 remains in the final build.
- Existing V4 EventEnvelope, overlay wire and presentation behavior remain unchanged by this refactor. Narrative-only identity, fact references, policy and `tape_channel` live in `NarrativeEvent`, story payloads and catalogs.
- Exact v2 config/API review candidates, including apply boundaries, migration, nullability, request bounds and local/LAN Ollama URL policy, live in `public-contracts.md`; implementation fixtures must be byte-for-structure equivalents.
- Exact single-mailbox admission/recovery, command inventory, speech-lane transitions, reset matrix and shutdown order live in `actor-transition-contract.md`; model-based transition fixtures remain blocking.
- DTO fields, schema versions, stream-scope nullability, canonical hashes, tape envelopes and reason IDs live in `schema-contracts.md`; machine-readable schemas/goldens remain blocking.
- The controlled-EN acceptance function, all 37 realization-family boundaries, rejection IDs, Qwen timeout/warm-up rule and promotion gates live in `realization-verifier-contract.md`; grammars/corpora remain blocking.
- Fourteen ordered expected scenarios covering lineage, scoring, no-queue behavior, invalid Qwen, silence, overflow and callback/reset races live in `vertical-slice-fixtures.md`; structured executable fixtures remain blocking.
- `final-pr-exclusion-manifest.md` names every planning path, forbidden temporary mechanism and required final behavior document.

## Blocking artifacts before the first runtime behavior edit

All boxes below must be complete in branch planning commits and issue #235 before behavior code changes:

- [ ] Canonical registry of event, feature, fact, reason, terminal-state and `tape_channel` IDs, including units and unknown semantics.
- [x] Complete identifier disposition matrix for all 60 known master identifiers and all 54 legacy nodes drafted in `event-beat-disposition.md`.
- [ ] Final review and machine validation of the exact 64 BeatDefinitions, including required/forbidden claims and realization family for every beat.
- [ ] Complete successor graph with deterministic relation, guard, preference and terminal/dead-end policy.
- [ ] Review the NarrativeEvent, NarrativeCommand, DetectorObservation, Fact, Episode, EventOpportunity, BeatPlan and tape contracts in `schema-contracts.md`; materialize JSON Schemas and a fixture proving the V4 EventEnvelope wire is unchanged.
- [ ] Review the exact config defaults/ranges in `public-contracts.md` and add the v1→v2 migration fixture matching specification §20.
- [ ] Review the exact API shapes in `public-contracts.md` and add request/response golden fixtures matching §20.1.
- [ ] Review the actor state-transition table, single-mailbox enqueue/dequeue order, protected/coalescible command matrix and shutdown/overflow reason codes in `actor-transition-contract.md`, then add model-based fixtures.
- [ ] Backend-neutral playback-acceptance acknowledgement, cancellation matrix and exact speech terminal-state table.
- [ ] Long-silence origin, pause/rearm rules and first-stream behavior table.
- [ ] Pre-arbitration detector-observation tap and kick→accepted→queued→selected→started funnel definitions.
- [ ] Released-versus-experimental detector tuning-policy matrix and recorder-failure transition behavior.
- [ ] Catalog loader checks for IDs, references, reachability, SCC exit barriers, ranges and cross-field invariants.
- [ ] Review all 37 family rows and acceptance/promotion rules in `realization-verifier-contract.md`; materialize grammars and counterexample corpora before admitting authored/tight/balanced/loose paths.
- [ ] Review the fourteen expected scenarios in `vertical-slice-fixtures.md` and materialize structured executable fixtures without changing runtime.
- [x] Final-PR exclusion manifest for planning files and temporary legacy/shadow code drafted in `final-pr-exclusion-manifest.md`.
- [x] Master baseline test evidence captured: `1364 passed in 15.10s`.
- [x] Master static baseline evidence captured: Ruff/Black/Mypy passed.

If any item changes after runtime implementation starts, work stops and returns to #235 for explicit re-freeze. Tuning an `estimated` value inside an already frozen type/unit/range is not an architecture change; changing identity, ownership, lifecycle, units, queue semantics, API/config schema or dependency direction is.

## Production gates that necessarily occur after implementation

These are not design gaps and cannot be proven before code exists:

- detector precision/recall/delay/flapping from recorded test sessions;
- Qwen verifier false-accept/false-reject corpus results;
- end-to-end Windows event→audio latency;
- tape bytes/minute, CPU overhead, slow/full-disk behavior;
- OBS/iRSDK disconnect, session rewind and shutdown drills;
- v1 binary/config downgrade rollback rehearsal.

Failure of any production gate blocks the final PR; it does not reopen frozen architecture automatically.
