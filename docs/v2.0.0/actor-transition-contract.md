# v2.0.0 NarrativeRuntime actor and transition freeze

**Status:** actor transition design machine-frozen for issues #235, #264 and #284

This branch-only artifact closes ordering, overflow, pipeline and shutdown choices before runtime edits. It specifies one actor and one speech lane; it never authorizes a queue of prepared text.

## Actor ownership

Only `NarrativeRuntime.run()` mutates:

- the last applied immutable timeline and FactView projections;
- EpisodeRegistry, EventOpportunityQueue and attempt suppressions;
- ExposureStore and bounded decision records;
- automatic/manual speech-lane state and worker tokens;
- the last applied immutable ConfigLedger snapshot used by narrative decisions;
- silence/validity deadline generations and commentary component health;
- current planning-cycle ID, dispatched-plan count (`0..2`) and source impulse.

StreamTimeline, FeatureEngine, FactLedger and DetectorBank remain upstream owners. Qwen, TTS and tape workers perform I/O but cannot mutate actor state. Server handlers post commands and read immutable status snapshots.

## Runtime and lane states

Runtime state is `disabled | starting | ready | degraded | stopping | stopped`. `degraded` remains operational for unaffected authored/detector/tape paths. It is not a second runtime mode.

The single speech lane has exactly these states:

| State | Owned data | Text waiting behind it? |
| --- | --- | --- |
| `idle` | none | no |
| `building` | one immutable narrative BeatPlan + RealizationBundle and realizer generation token | no |
| `committed` | one verified current utterance dispatched to TTS, awaiting backend acceptance | no |
| `speaking` | one backend-accepted utterance and playback token | no |
| `stopping` | one cancellation in progress | no |

`generated` and `verified` are transition observations inside one actor command, not stable queue states. There is never a second BeatPlan, prompt, generated string or utterance waiter.

## Command envelope

Every mailbox item is immutable and contains:

```text
schemaVersion = narrative-command/2
commandId: stable unique ID
kind: registry enum
enqueuedMonoMs: nonnegative integer
mailboxSequence: nonnegative admission ordinal assigned atomically by the mailbox
externalOrder: {fanoutStreamSequence, firstSourceOrdinal?, lastSourceOrdinal?} or null
contextRevision: {timelineRevision, factViewRevision} or null
token: worker/deadline/manual token or null
payload: kind-specific bounded object
```

These are the exact JSON/tape names. Python may map them to snake_case internally under the global lossless mapping rule; snake_case is never accepted on the wire or replay input.

The command discriminator fixes `token`, `payload`, `externalOrder` and `contextRevision` exactly:

| Kind(s) | `token` | `payload` | Context/order fields |
| --- | --- | --- | --- |
| `APPLY_CONTEXT_BATCH` | null | `{timeline,factView,events[0..64]}` | both required non-null and must name the payload revisions/publication range |
| `CONFIG_UPDATE` | null | `{valid,ledger?,diagnostics[0..32]}`; ledger required iff valid | both null |
| `LONG_SILENCE_ELAPSED`, `VALIDITY_DEADLINE_ELAPSED` | `{generation,deadlineMonoMs}` | `{}` | both null |
| `REALIZATION_SUCCEEDED`, `REALIZATION_FAILED` | `{requestId,requestOrdinal,dispatchGeneration}` | exact `realization-result/2` | both null |
| `REALIZATION_DEADLINE_ELAPSED` | `{requestId,requestOrdinal,dispatchGeneration,deadlineMonoMs}` | `{}` | both null |
| `PLAYBACK_ACCEPTED`, `SPEECH_COMPLETED`, `SPEECH_INTERRUPTED`, `SPEECH_FAILED` | `{utteranceId,utteranceOrdinal,backendGeneration,dispatchGeneration}` | exact `tts-callback/2` | both null |
| `SPEECH_DEADLINE_ELAPSED` | prior TTS token plus `{stage,deadlineMonoMs}`, stage `start|playback|stop` | `{}` | both null |
| `MANUAL_SPEAK_REQUEST` | `{manualRequestId,admissionOrdinal}` | `{text,language="en"}`; text 1..400 normalized/control-free | both null |
| `TAPE_HEALTH_CHANGED` | null | `{recorderGeneration,status,affectedDetectorIds[0..128],firstLostSequence?,lastLostSequence?}` | both null; loss endpoints both present or both null |
| `COMPONENT_HEALTH_CHANGED` | null | `{component,generation,status,reason?}` | both null |
| `MAILBOX_RECOVERY` | null | `{latestTimeline,latestFactView,lossFirstMailboxSequence,lossLastMailboxSequence,historyComplete=false,safetyEffects[1..64]}` | both required non-null and name the latest projections plus covered loss range |
| `SHUTDOWN` | null | `{reason,requestedMonoMs}` | both null |

Diagnostics are exact bounded `{code,key?,messageHash?}` objects; they contain no exception/config value. Tape status is `ready|degraded|unavailable`; component is `llm|tts`, component status is `ready|degraded|unavailable`. A health loss range is inclusive and ordered. `safetyEffects` are closed `{kind,identity,payloadHash}` records whose kind is one of the protected command kinds absorbed by the recovery barrier; they are replay evidence, not nested commands. Unknown payload/token fields are rejected. The JSON Schema owns the same discriminator matrix; adding a command or changing a payload requires `narrative-command/3`.

Every context batch carries `external_order`; worker/timer/API commands do not. Its fanout sequence is positive. A batch with events carries the inclusive first/last per-publication ordinals represented by that part; a pure timeline/fact batch has both ordinals null. Split parts share their publication fanout sequence and have increasing disjoint ordinal ranges. `context_revision` exists only for context/recovery commands and always names both projections; neither scalar substitutes for the other. `mailbox_sequence` totally orders successful concurrent admissions and is preserved when protected/ordinary capacity partitions are used. On dequeue the actor assigns the next `reducer_sequence` in mailbox-sequence order. That recorded reducer sequence—not wall-clock equality or task scheduling—is replay authority.

## Complete command inventory

| Kind | Producer | Protected | Coalescing | Actor effect |
| --- | --- | --- | --- | --- |
| `APPLY_CONTEXT_BATCH` | narrative fanout adapter | exactly when timeline transitionReasons is nonempty or a contained event has derived `deliveryClass=protected` | never | atomically apply one coherent TimelineSnapshot/FactView plus 0..64 ordered NarrativeEvents; pure FactView change only invalidates/closes, while at least one accepted/lifecycle NarrativeEvent may trigger one director pass |
| `CONFIG_UPDATE` | stream/config coordinator | yes | never; admitted atomically before its optional matching context batch | cache the already installed ConfigLedger snapshot/diagnostic and launch generation-tagged component preflights; run/episode/speech lifecycle changes only in the immediately following coherent context batch |
| `LONG_SILENCE_ELAPSED` | owned one-shot deadline | no | same deadline generation only | clear fired token, evaluate one filler impulse, then rearm by frozen rule |
| `VALIDITY_DEADLINE_ELAPSED` | owned nearest-expiry one-shot deadline | no | same deadline generation only | sweep facts already expired in the applied view plus opportunity/BeatPlan revision deadlines; cancel invalid building/committed work, never run director, then rearm |
| `REALIZATION_SUCCEEDED` | authored/Qwen worker | yes | never | token-check, freshness-check bound facts/identity, verify synchronously against the same bundle and dispatch TTS or reject |
| `REALIZATION_FAILED` | authored/Qwen worker | yes | never | token-check, suppress beat/revision and release reservation |
| `REALIZATION_DEADLINE_ELAPSED` | actor-owned one-shot deadline | yes | same request token only | token-check, terminalize as timeout, cancel/detach transport and apply the one-alternative cycle bound without waiting |
| `PLAYBACK_ACCEPTED` | TTS worker | yes | duplicate/stale callback identity is ignored and audited | validate the frozen TtsCallback/token; narrative consumes its opportunity and creates exposure, manual does neither; both enter `speaking` and pause audience silence |
| `SPEECH_COMPLETED` | TTS worker | yes | duplicate/stale callback identity is ignored and audited | validate the frozen TtsCallback/token; terminalize exposure/request and free lane; only a natural narrative terminal runs one director pass |
| `SPEECH_INTERRUPTED` | TTS worker | yes | duplicate/stale callback identity is ignored and audited | validate the frozen TtsCallback/token; terminalize exposure/request and free lane; replan only for a natural narrative terminal whose cancellation policy permits it |
| `SPEECH_FAILED` | TTS worker | yes | duplicate/stale callback identity is ignored and audited | validate the frozen TtsCallback/token; narrative before acceptance releases+suppress and after acceptance keeps consumed exposure; manual only terminalizes its request; both free lane |
| `SPEECH_DEADLINE_ELAPSED` | actor-owned one-shot watchdog | yes | duplicate/stale token ignored | `start|playback|stop` stage applies the bounded timeout transition below; never creates a second utterance |
| `MANUAL_SPEAK_REQUEST` | localhost API adapter | no | never | atomically claim its one-shot admission latch, then nonblocking-dispatch the effective preflighted TTS generation and enter committed only when idle/available; never create episode/opportunity/exposure |
| `TAPE_HEALTH_CHANGED` | capture-safety coordinator | required-capture loss is protected | same recorder generation/status and affected detector set | update health; its atomically following context batch carries the upstream detector disable/expiry effects |
| `COMPONENT_HEALTH_CHANGED` | owned Qwen/TTS preflight worker | yes when unavailable, otherwise no | same component/generation/status | accept only current generation; update readiness without starting planning or speech |
| `MAILBOX_RECOVERY` | mailbox | yes | one pending barrier absorbs later loss metadata/snapshot revisions | cancel uncommitted work, reconstruct current projections and mark history incomplete |
| `SHUTDOWN` | application owner | yes | idempotent singleton | stop ingress and execute ordered bounded shutdown |

Stream/session/vehicle lifecycle names in the event disposition are items inside an `APPLY_CONTEXT_BATCH`, not separately scheduled queues. `STREAM_ENDED`, occurrence change/restart and truth-invalidating supersession are applied before other events later in the same batch. A rewind to an older/different SessionRef is represented by ordered old-occurrence end/supersede followed by new-occurrence start; `SESSION_REWOUND` is not a command kind.

A batch containing no NarrativeEvent never starts a director pass merely because a fact changed. It may cancel a stale building/committed plan, invalidate an opportunity or close/suspend an episode. Accepted/lifecycle/silence input or a speech terminal command is the planning impulse; that later pass evaluates the newest FactView and any now-valid natural successor. This prevents raw tick cadence from becoming an implicit speech trigger while preserving fact-safe continuation.

## Config boundary order

ConfigLedger is the cross-component atomic owner defined in the schema contract; the actor never mutates it directly. The stream/config coordinator has already applied the `command` group and atomically admitted any matching timeline batch immediately after `CONFIG_UPDATE`. The actor caches that snapshot and starts or replaces required LLM/TTS preflight tokens without awaiting them; the following context command alone closes/creates the run. For actor-owned boundaries it requests exactly the named group and snapshots the returned hash/apply sequence before creating the object/action:

```text
stream/config coordinator: next_stream → open run tape manifest → first projection/frame
director impulse: next_director_pass → score candidates
silence arm/rearm: next_silence_deadline → create deadline token
automatic selection: next_plan_or_manual → next_beat_plan → create BeatPlan
manual admission: next_plan_or_manual → next_utterance → check matching TTS preflight → dispatch
Qwen dispatch: next_request → create exact RealizationRequest + request/deadline token
TTS dispatch: next_utterance → check matching preflight → create utterance token
cancellation: next_cancellation → create cancellation/watchdog token
tape writer: next_record/next_rotated_file/next_rotation/next_writer_deadline at its corresponding owned boundary
shutdown owner: next_shutdown → bound tape flush
```

If an applied LLM/TTS group has no successful matching current-generation preflight, the actor records `component_preflight_pending|component_preflight_failed` and treats only that component as unavailable. It never uses the prior generation for new work. Existing plans, requests, utterances, cancellations, records, files and deadlines retain their snapshotted hash and values. `COMPONENT_HEALTH_CHANGED` accepts only the current token/generation, updates readiness, and does not itself run the director or dispatch speech.

Tape/config ordering uses ConfigLedger's reserved writer barrier, not NarrativeMailbox. Normally its unfilterable `config_applied` transition is admitted after all old-snapshot records and before any newly admitted record. Enabling opens the current-run writer with the new manifest snapshot and then writes the transition; disabling attempts the transition and complete trailer before capture stops. A saturated/failed barrier never delays disable, a lifecycle transition or any other config application: the new snapshot still publishes, while the out-of-queue loss accumulator records `config_transition_lost`, exact hashes/sequence and incomplete replay. Tape boundaries are owned by the writer, while `next_stream` is owned upstream before DetectorBank's first new-run frame. Neither owner imports or calls NarrativeRuntime.

## Mailbox capacity and overflow

Initial total capacity is 64 items: 56 ordinary cells, 7 protected cells and one emergency recovery/shutdown cell inside the same mailbox. The partitions are admission reservations, not independent queues; dequeue always follows the single recorded enqueue order.

A config change that changes `commentary.enabled` is one atomic admission bundle: consecutive `CONFIG_UPDATE`, then its coherent protected `APPLY_CONTEXT_BATCH`. Required-capture loss uses the same two-cell rule for `TAPE_HEALTH_CHANGED`, then the coherent protected `APPLY_CONTEXT_BATCH` produced after upstream detector disable. The mailbox reserves both cells or neither; no producer can obtain a mailbox sequence between either pair. When two protected cells are unavailable, the emergency recovery barrier receives the diagnostic/health change plus the transition batch's latest projection and safety effects as one recoverable unit. It never admits only one half.

Admission is nonblocking:

1. Coalesce only `LONG_SILENCE_ELAPSED` or `VALIDITY_DEADLINE_ELAPSED` with the same kind/generation, `REALIZATION_DEADLINE_ELAPSED` with the same exact request token, `TAPE_HEALTH_CHANGED` with the same recorder generation/status/affected-detector set, or `COMPONENT_HEALTH_CHANGED` with the same component/generation/status. APPLY_CONTEXT_BATCH never coalesces.
2. An ordinary command uses an ordinary cell when one exists. A manual request is rejected as `mailbox_overloaded` rather than evicting admitted work.
3. If an ordinary context batch cannot fit, evict the oldest ordinary silence command first. If none exists, evict the oldest ordinary context batch, record its full source/revision range and atomically place/refresh `MAILBOX_RECOVERY` in the emergency cell with the latest coherent projections. Lost accepted events become auditable lost history and never opportunities.
4. A protected item may evict the oldest ordinary silence/context item and must place/refresh the same recovery barrier whenever a context batch was lost.
5. If protected capacity is exhausted, place/refresh `MAILBOX_RECOVERY` in the emergency cell. It carries the latest coherent projections, upstream loss range, current worker snapshots and every incoming protected command's idempotent safety effect. Exact intermediate narrative history is marked incomplete; no lost event opportunity is invented.
6. Refreshing a pending recovery keeps its original mailbox position but replaces its projection with the newest revision and expands the loss range. On reduction, the barrier jumps to that recorded projection and all subsequently dequeued older context revisions/tokens are stale no-ops; replay uses the same payload/reducer order.
7. `SHUTDOWN` owns the emergency cell when requested. Existing recovery metadata and safety effects are attached to shutdown rather than silently erased; ingress is already closed, so it cannot be refreshed by later normal work.

This policy guarantees a bounded nonblocking producer and safe latest truth, not lossless narration under overload. Every loss increments health/tape counters. After recovery, historical/recap claims requiring the lost interval are hard-gated by `history_complete=false`.

Every reducer command first performs the same logical validity sweep at its captured reduction time. Therefore, if a validity timer cannot enter a full ordinary partition, it records `deadline_admission_skipped` and the already queued command at the head of the actor's future work performs the sweep; no truth/event history is lost and no recovery barrier is needed. When the mailbox becomes empty, the armed timer is guaranteed an ordinary cell. Deadline commands never create a planning impulse.

## Automatic pipeline transitions

| Current lane | Input/condition | Next lane | Required effects |
| --- | --- | --- | --- |
| `idle` | director selects valid beat | `building` | reserve opportunity if present; synchronously create one BeatPlan + RealizationBundle/token; dispatch one realizer |
| `idle` | no candidate/TTS unavailable | `idle` | record bounded SILENCE/reason; do not consume anything |
| `building` | context makes plan hard-invalid | `idle` | cancel token, release reservation, terminal `invalidated`; replan only if this same command contains an accepted/lifecycle event impulse, otherwise wait |
| `building` | a later accepted-event impulse admits a challenger that outranks the plan | `building` or `idle` | cancel old token/release as `replaced` without suppression; close its cycle and start the event's new cycle at attempt 1 |
| `building` | stale/mismatched worker token | unchanged | discard callback and record `stale_worker_token` |
| `building` | matching realization deadline | `idle` | invalidate token, cancel/detach transport, suppress revision as `realization_timeout`; immediately try one different beat only for cycle attempt 1 |
| `building` | realization failure/timeout | `idle` | suppress `(beat_id, episode_revision)`, release reservation; dispatch one different beat only if this was cycle attempt 1, otherwise record `planning_cycle_exhausted` and wait |
| `building` | realization succeeds but verifier rejects | `idle` | same suppression/release and cycle bound; no repair, retry or same-beat authored fallback |
| `building` | verifier passes but freshness commit fails | `idle` | suppress stale revision, release reservation and apply the same one-alternative cycle bound |
| `building` | verifier and freshness pass | `committed` | dispatch exactly one TTS request/token |
| `committed` | truth/reset/disable/shutdown invalidates request before ack | `stopping` | request cancellation; opportunity remains unconsumed |
| `committed` | ordinary/critical race event | `committed` | reduce truth only; do not replace dispatched utterance |
| `committed` | `PLAYBACK_ACCEPTED` matching token | `speaking` | consume opportunity exactly once; add exposure with full repetition weight |
| `committed` | `SPEECH_FAILED` before ack | `idle` | release and suppress beat/revision; mark TTS degraded when applicable; dispatch the one alternative only if TTS remains available and this was cycle attempt 1 |
| `committed` | completion/interruption or malformed/out-of-order callback | `stopping` | record `tts_protocol_violation`, quarantine the backend generation immediately, keep an unaccepted narrative opportunity unconsumed and request bounded cancellation |
| `speaking` | matching completion | `idle` | terminalize exactly once as completed; request idempotent duck restore; narrative alone starts one current-state director pass |
| `speaking` | matching interruption/failure | `idle` | terminalize exactly once with consumed exposure retained; request idempotent duck restore; replan only when the stored terminal policy permits it |
| `speaking` | second acceptance or malformed/out-of-order callback | `stopping` | record `tts_protocol_violation`, quarantine the backend generation immediately and request bounded cancellation; the already consumed exposure stays consumed |
| `stopping` | acceptance callback | `stopping` | audit as stale/illegal and never consume; await terminal or stop watchdog |
| `stopping` | matching terminal callback | `idle` | terminalize exactly once according to whether acceptance already occurred; request idempotent duck restore; never run director for lifecycle/shutdown cancellation |
| any | callback for noncurrent/terminal token, or quarantined generation other than its retained cleanup token | unchanged | audited no-op; never consume, restore twice, replan or revive a backend |
| `speaking` | ordinary/critical race event | `speaking` | reduce state/opportunities only; no interruption and no prepared text |
| `speaking` | allowed cancellation | `stopping` | request one backend cancellation; consumption is never rolled back |

Allowed automatic cancellation is limited to confirmed stream end, occurrence/run reset, explicit commentary disable, shutdown, or fact/identity supersession that makes the utterance's committed claims false. A newer or more urgent racing event never cancels accepted or dispatched playback.

Each TTS token owns at most one current watchdog. In `committed`, `start_timeout_s` bounds dispatch-to-`PLAYBACK_ACCEPTED|SPEECH_FAILED`. In `speaking`, the selected BeatPlan `maxSeconds` (manual uses global `max_utterance_s`) bounds accepted playback. Either deadline moves the lane to `stopping`, requests cancellation and arms `stop_timeout_s`. A matching terminal callback before the stop deadline follows the normal table. On stop timeout the actor invalidates/quarantines the worker token, terminalizes any accepted exposure conservatively, marks TTS `component_unavailable`, and frees narrative state; no later callback for that token may mutate state and no automatic/manual speech is admitted until a `COMPONENT_HEALTH_CHANGED(backendGeneration>quarantinedGeneration,status=ready)` from a successful explicit config-rebuild preflight. There is no periodic retry or spontaneous recovery from a stale callback. Backend wrappers must make best effort to terminate their process/audio handle, but inability to prove physical silence never blocks or crashes the main loop.

Every dispatched request is the exact immutable `tts-utterance/2` object and every worker response is the exact `tts-callback/2` object from the schema contract. The actor stores `accepted=false`, nullable accepted time and one terminal-director policy with the token. Normal narrative completion/interruption uses `replan_if_enabled`; manual speech and every stream/session/reset/disable/shutdown/truth-invalidating cancellation use `never`. Reducer dequeue time is the authoritative accepted/terminal time; callback-observed time is latency evidence only. A synchronous dispatch rejection creates no committed lane/token. After successful nonblocking dispatch, only mailbox callbacks or actor watchdogs may advance it.

Ducking belongs to the worker token, not NarrativeRuntime or OBS scene logic. The worker attempts ducking before `PLAYBACK_ACCEPTED` and issues one idempotent best-effort restore operation on terminal/cancel. A duck failure is recorded as `duck_unavailable` but remains fail-soft and does not reinterpret playback acceptance; a terminal/watchdog must still release the token and request restoration without claiming that unavailable OBS applied it.

`auto` backend selection is resolved before utterance admission and the concrete backend/generation is immutable in its token. The baseline compatibility order is SAPI, then eSpeak; SuperTonic is explicit-only. No dispatched text fails over to another backend after error/timeout.

### Backend acknowledgement adapter matrix

The common TTS worker, not NarrativeRuntime, owns a one-shot acknowledgement latch for each dispatch token. It may post `PLAYBACK_ACCEPTED` only after the selected adapter reaches the software boundary below. Merely entering the worker, synthesizing PCM, completing duck fade, creating a Python task or placing a request in an internal queue is never acceptance.

| Backend | Exact acceptance boundary | Completion | Pre-acceptance failure | Cancellation evidence |
| --- | --- | --- | --- | --- |
| SAPI default endpoint | the v2 PowerShell helper's asynchronous `SpVoice.Speak` call returns a positive stream number and the helper flushes its single framed acceptance line | SAPI wait reports that stream finished and helper exits zero | COM/voice/setup/async-Speak error, invalid stream number or helper exit before its framed acceptance line | helper stops/purges the voice and exits with the framed interrupted terminal; kill/timeout without that frame is resolved by actor watchdog |
| SAPI selected waveOut endpoint | synthesis produced nonempty PCM and `waveOutWrite` returned success for the owned prepared buffer, then the helper flushes its single framed acceptance line | the owned header reaches done, is unprepared, device closes and helper exits zero | synthesis, device-open, prepare or write failure before the line | helper calls reset on the owned handle and emits interrupted; forced termination remains watchdog-owned |
| eSpeak/eSpeak-NG | `Popen` returns an owned child handle for the fully validated argv and the immediate nonblocking exit probe has not reported failure, then the worker posts acceptance | owned child exits zero | spawn failure or nonzero exit observed by the immediate probe before acceptance | owned child is terminate→bounded wait→kill; confirmed cancellation posts interrupted |
| SuperTonic | synthesis produced nonempty finite PCM and `sounddevice.play` returns after accepting the full buffer/stream parameters | `sounddevice.wait` returns without backend error | model/synthesis/device lookup or `play` error before return | owned stream is stopped; confirmed stop posts interrupted |

The SAPI framed line is machine protocol on a dedicated pipe, not parsed from human log text. Each adapter posts at most one acceptance and one terminal callback in worker-sequence order. Zero-exit without the required acceptance frame, terminal-before-acceptance other than `failed`, duplicate frames, or conflicting adapter identity is `tts_protocol_violation`; it is not reinterpreted as a successful short utterance. Physical loudspeaker output remains unobservable and outside the promise. Backend cancellation is best effort: actor state is released only by a valid terminal callback or the already frozen stop watchdog, never by assuming that a cancellation request succeeded.

### Required-capture safety ownership

TapeWriter never imports or mutates DetectorBank or NarrativeRuntime. On loss of any record belonging to an enabled `tuning.required` CapturePlan, it writes the loss accumulator and emits one idempotent `CaptureHealthNotice(recorderGeneration,affectedDetectorIds,firstLostSequence,lastLostSequence)` through an out-of-queue bounded health latch owned by composition. The latch survives saturation of the record queue.

The composition-owned capture-safety coordinator validates the current recorder generation, disables only the named experimental detectors through DetectorBank's narrow control interface, and asks the normal upstream pipeline to close their FSMs/facts/candidates with `required_capture_lost`. It then atomically admits `TAPE_HEALTH_CHANGED(capture_unavailable)` followed by that coherent TimelineSnapshot/FactView/event batch. NarrativeRuntime only reduces the health projection and the normal truth invalidations; it never calls upstream. Duplicate/older notices are no-ops. Recovery of the recorder never re-enables a detector inside the current run: a successful preflight and a later `next_stream` boundary are both required.

Attempt suppression occurs only for realization/verification/commit/TTS-before-acceptance failure. Replacement by a new candidate does not suppress a still-valid old beat. Suppression clears only on material episode revision, opportunity/episode terminal state, occurrence reset or stream reset.

One planning impulse owns one `planningCycleId` and may dispatch at most two distinct BeatPlans: its initial choice and one alternative after realization/verification/freshness/TTS-before-acceptance failure. That internal failure consumes ordinal 2; a second failure ends the cycle with `planning_cycle_exhausted`. A later accepted/lifecycle/silence event, material accepted event revision, or narrative speech-terminal command starts a new cycle. If such a new accepted event legitimately replaces a building plan, the old cycle closes `replaced_precommit` and the challenger is ordinal 1 of the new cycle; the cancelled beat is not suppressed. A non-outranking event leaves the existing cycle untouched. Pure FactView batches and manual terminals start no cycle. This fixed per-impulse bound is not public config and prevents an LLM/validator failure cascade without treating real new events as retries.

Every realizer dispatch/result follows [the Qwen transport contract](qwen-transport-contract.md). NarrativeRuntime arms its own monotonic request deadline instead of trusting an HTTP library callback. Result-first cancels the timer; deadline-first invalidates the result token. RealizerService atomically owns at most one logical request and never queues another. Per-chunk streaming data stays inside the worker; only one terminal result enters NarrativeMailbox. A canonical duplicate is a no-op, while the same result ID with changed content is `realization_protocol_violation`. Worker-observed times are metrics; reducer sequence and dequeue time own state.

## Manual speech

Manual speech is an explicit operator audio test and is available even when automatic commentary is disabled. Admission is serialized through the actor; the API returns 202 only after `MANUAL_SPEAK_REQUEST` has nonblocking-dispatched the text through the current effective preflighted backend generation and moved an idle lane directly to `committed`. It has no realizer/building transition. Busy, synchronously rejected dispatch or unavailable TTS returns the frozen 409/503 with the lane unchanged.

The request carries a process-local one-shot `ManualAdmissionLatch` with states `pending | actor_claimed | caller_abandoned`. This latch is only a command/reply rendezvous; it is not a speech waiter, prepared-text queue, actor input or replayed DTO. The API adapter validates the request, allocates the latch, performs nonblocking mailbox admission, then awaits the result for a fixed 1,000 ms:

1. mailbox rejection returns `mailbox_overloaded`/503 and atomically abandons the latch;
2. on dequeue, the actor must atomically change `pending → actor_claimed` before mutating the lane; an already abandoned request is a stale no-op;
3. in the same synchronous reducer turn, the actor either dispatches the effective TTS generation, moves `idle → committed` and resolves 202, or leaves the lane unchanged and resolves 409/503;
4. on timeout or client cancellation, the adapter atomically changes `pending → caller_abandoned`; if it wins, it returns `admission_timeout`/503 and later actor reduction cannot speak; if the actor already claimed, its result is immediately authoritative and is returned instead.

No `await` is permitted between actor claim, lane decision and latch resolution. Thus every response has one linearization point, and no request reported as rejected can later produce audio. Tape stores request ID and final admission decision, never the latch object.

Manual text passes length/control-character and EN-tag validation, then goes directly to the effective configured TTS backend/voice/rate; the request cannot select or construct another backend generation. It creates no NarrativeEvent, EventOpportunity, BeatPlan, Episode transition, ExposureStore row, fatigue or story successor. Race events do not interrupt it. Commentary disable does not cancel it; stream/session resets cancel only narrative speech, while application shutdown cancels both. Manual playback acceptance pauses the audience silence deadline and its terminal callback rearms that deadline from terminal time, but neither callback itself runs the director.

## Context/reset matrix

| Boundary | Facts/episodes/opportunities | Building/committed | Speaking narrative | Exposure/history |
| --- | --- | --- | --- | --- |
| iRacing disconnect | suspend current truth; invalidate freshness-dependent opportunities | cancel if required truth unavailable | cancel only if committed claims become false | preserve occurrence and exposure |
| reconnect same ref/no rewind | resume same occurrence | new planning only | unchanged | preserve |
| same-ref confirmed rewind | archive old run facts; create new occurrence revision | cancel | cancel | preserve old as historical according to scope |
| different/new SessionRef | end/supersede old occurrence; activate lineage-selected new one | cancel old occurrence | cancel old occurrence | preserve active ancestors and bounded summaries |
| OBS output unknown | pause OBS-dependent planning/silence timer | cancel only if hard OBS guard required | continue | preserve stream epoch |
| confirmed stream end | close/invalidate all stream state | cancel | cancel | finalize exposure and tape trailer |
| commentary disable | keep raw upstream projections; close the current narrative run and all episodes/opportunities with `commentary_disabled` | cancel narrative request | cancel narrative speech; manual continues | finalize its tape trailer, retain audit only and clear live exposure before any later run |
| process shutdown | no new ingress | cancel | bounded cancel/wait | flush then discard in-memory state |

## Silence deadline transitions

- The audience window is exactly `runtime status=ready|degraded`, valid commentary config has `enabled=true`, `narrativeRunActive=true`, and OBS state is `active`. Session presence, on-track state and candidate availability are not part of this predicate.
- At confirmed broadcast start, allocate a new `streamEpoch`; at re-enable during the same active `broadcastEpoch`, allocate another new `streamEpoch` with `historyComplete=false`. In the same actor reduction, process lifecycle candidates first and then arm generation `g+1` for `now + long_silence_s` if the audience window is active and no speech is accepted. A stream/session opening BeatPlan does not move or cancel this origin before playback acceptance.
- On narrative or manual `PLAYBACK_ACCEPTED`, cancel the armed deadline. A stale timer token cannot fire.
- On any speech terminal command, rearm from actor reduction time only when the audience window is active and no other speech is accepted; worker-observed callback time is metrics only, and a manual terminal does not itself run the director. A manual terminal while automatic commentary is disabled/end-of-stream never arms it.
- On OBS unknown/inactive, commentary disable, confirmed stream end, runtime stopping or shutdown, cancel and retain no elapsed credit. On return to an active audience window without a new run, rearm from that transition's reduction time; a new/re-enabled run follows the first-stream rule above.
- On `LONG_SILENCE_ELAPSED`, clear the exact token and evaluate exactly once. If the lane is `building|committed|speaking|stopping`, or no filler passes current guards, no filler is selected. If no playback becomes accepted in that reduction, rearm from command reduction time; never use a shorter retry. A later pre-acceptance failure/terminal performs the normal rearm again and invalidates the intervening generation.
- Race/event director passes do not move the silence origin unless playback is accepted.
- `long_silence_s` is snapshotted at every arm under `next_silence_deadline`. Changing it does not move an already armed deadline; the new value applies at the next cancel/rearm boundary. Exactly one current generation exists, so a simultaneous terminal and elapsed callback follows mailbox order and the later stale token is a no-op.

## Validity deadline transitions

- Eligibility intervals are half-open: a fact is current at `validFromMonoMs <= now < validUntilMonoMs` (or no upper bound); opportunity/BeatPlan is valid at `created|plannedMonoMs <= now < expiresMonoMs`. At exact upper bound it is invalid.
- The actor arms one nearest-expiry generation for the minimum current opportunity, successor-revision and BeatPlan deadline. FactLedger owns fact-time expiration and publishes a fact-only coherent context batch; the actor also refuses any applied fact whose upper bound is already reached.
- Any command reduction sweeps all deadlines `<= reductionNow` before handling that command. A matching `VALIDITY_DEADLINE_ELAPSED` does only this sweep and rearm.
- Expiring a reserved opportunity or building plan cancels its generation token, terminalizes it as `expired_ttl`, and does not consume planning attempt 2. Expiring a committed pre-acceptance utterance requests cancellation and leaves the opportunity unconsumed/expired. Speaking playback is not interrupted merely because its source opportunity later expires.
- Expiry never starts the director. After plan/opportunity validity expires, runtime waits for a later accepted/lifecycle/silence event or speech-terminal impulse, exactly as for any other fact-invalid continuation.

## Ordered shutdown

1. Set runtime `stopping` and reject new external/manual ingress.
2. Cancel silence and generation tasks; invalidate their tokens.
3. Request cancellation of committed/speaking TTS and wait only to `commentary.tts.stop_timeout_s`; quarantine an unresponsive backend token.
4. Enqueue no new director work; reduce the matching terminal callback if it arrives.
5. Ask the tape writer to flush/close and wait at most `shutdown_flush_timeout_s`.
6. Record timeout/drop state through the best available log/manifest path, publish final immutable status and set `stopped`.

No shutdown timeout raises into the main application loop. Worker tasks are owned, named, cancellable and joined or explicitly reported as timed out.

## Closure checks

Issues #235/#284 cannot close until tests or model-based transition enumeration prove:

- every `(lane state, command kind)` is accepted, ignored with a reason, or rejected—never unspecified;
- token mismatch and duplicate callbacks are idempotent;
- no route creates a second generation, playback or waiter;
- every admitted Qwen request reaches one result or actor deadline; result/deadline order cannot strand `building`, enqueue another request or produce two terminal attempts;
- every reservation reaches release, consumption or a terminal opportunity state;
- overflow/recovery cannot resurrect lost events or stale facts;
- reset/disable/shutdown cancellation follows the matrix;
- tape replay over reducer sequence reproduces director decisions when recorded Qwen completions are supplied.

The branch-only model evidence is `machine/actor-transition-model.json` with its closed schema, goldens and mutation set. Its checker cross-checks the exact 17-kind NarrativeCommand union, enumerates all 85 lane/command pairs, verifies the 56/7/1 single-mailbox partition and exact protected/coalescing allowlists, then executes race, ordering and overflow traces. These fixtures close the pre-implementation design gate; implementation still owes focused pytest/pytest-asyncio tests using byte-equivalent rules.
