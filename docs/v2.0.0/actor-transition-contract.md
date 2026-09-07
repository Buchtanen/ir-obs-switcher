# v2.0.0 NarrativeRuntime actor and transition freeze

**Status:** design-freeze candidate owned by issues #235, #264 and #284

This branch-only artifact closes ordering, overflow, pipeline and shutdown choices before runtime edits. It specifies one actor and one speech lane; it never authorizes a queue of prepared text.

## Actor ownership

Only `NarrativeRuntime.run()` mutates:

- the last applied immutable timeline and FactView projections;
- EpisodeRegistry, EventOpportunityQueue and attempt suppressions;
- ExposureStore and bounded decision records;
- automatic/manual speech-lane state and worker tokens;
- silence deadline generation and commentary component health.

StreamTimeline, FeatureEngine, FactLedger and DetectorBank remain upstream owners. Qwen, TTS and tape workers perform I/O but cannot mutate actor state. Server handlers post commands and read immutable status snapshots.

## Runtime and lane states

Runtime state is `disabled | starting | ready | degraded | stopping | stopped`. `degraded` remains operational for unaffected authored/detector/tape paths. It is not a second runtime mode.

The single speech lane has exactly these states:

| State | Owned data | Text waiting behind it? |
| --- | --- | --- |
| `idle` | none | no |
| `building` | one immutable BeatPlan and generation token, or one admitted manual request | no |
| `committed` | one verified current utterance dispatched to TTS, awaiting backend acceptance | no |
| `speaking` | one backend-accepted utterance and playback token | no |
| `stopping` | one cancellation in progress | no |

`generated` and `verified` are transition observations inside one actor command, not stable queue states. There is never a second BeatPlan, prompt, generated string or utterance waiter.

## Command envelope

Every mailbox item is immutable and contains:

```text
schema_version = narrative-command/2
command_id: stable unique ID
kind: registry enum
enqueued_monotonic_ms: nonnegative integer
mailbox_sequence: nonnegative admission ordinal assigned atomically by the mailbox
external_order: (fanout_stream_sequence, source_ordinal) or null
context_revision: upstream coherent projection revision or null
token: worker/deadline/manual token or null
payload: kind-specific bounded object
```

External adapter items carry `external_order`; worker/timer/API commands do not. `mailbox_sequence` totally orders successful concurrent admissions and is preserved when protected/ordinary capacity partitions are used. On dequeue the actor assigns the next `reducer_sequence` in mailbox-sequence order. That recorded reducer sequence—not wall-clock equality or task scheduling—is replay authority.

## Complete command inventory

| Kind | Producer | Protected | Coalescing | Actor effect |
| --- | --- | --- | --- | --- |
| `APPLY_CONTEXT_BATCH` | narrative fanout adapter | when batch contains identity/lifecycle/result; otherwise no | only same-correlation ACTIVE/UPDATE revisions before dequeue | atomically apply one coherent timeline/FactView plus ordered NarrativeEvents |
| `CONFIG_UPDATE` | config owner | yes | never | validate/apply each generation in order; defer fields whose declared boundary is not yet legal |
| `LONG_SILENCE_ELAPSED` | owned one-shot deadline | no | same deadline generation only | clear fired token, evaluate one filler impulse, then rearm by frozen rule |
| `REALIZATION_SUCCEEDED` | authored/Qwen worker | yes | never | token-check, verify synchronously, freshness-check and dispatch TTS or reject |
| `REALIZATION_FAILED` | authored/Qwen worker | yes | never | token-check, suppress beat/revision and release reservation |
| `PLAYBACK_ACCEPTED` | TTS worker | yes | duplicate token is ignored and audited | consume narrative opportunity, create exposure and enter `speaking` |
| `SPEECH_COMPLETED` | TTS worker | yes | duplicate token is ignored and audited | terminalize exposure, free lane and run one director pass |
| `SPEECH_INTERRUPTED` | TTS worker | yes | duplicate token is ignored and audited | terminalize exposure/manual request, free lane and replan when enabled |
| `SPEECH_FAILED` | TTS worker | yes | duplicate token is ignored and audited | before acceptance release+suppress; after acceptance keep consumed exposure; free lane |
| `MANUAL_SPEAK_REQUEST` | localhost API adapter | no | never | admit only when lane is idle and TTS available; never create episode/opportunity/exposure |
| `TAPE_HEALTH_CHANGED` | tape writer | required-capture loss is protected | same recorder generation/status | update health; disable only affected required experimental detectors |
| `MAILBOX_RECOVERY` | mailbox | yes | one pending barrier absorbs later loss metadata/snapshot revisions | cancel uncommitted work, reconstruct current projections and mark history incomplete |
| `SHUTDOWN` | application owner | yes | idempotent singleton | stop ingress and execute ordered bounded shutdown |

Stream/session/vehicle lifecycle names in the event disposition are items inside an `APPLY_CONTEXT_BATCH`, not separately scheduled queues. `STREAM_ENDED`, occurrence change/restart and truth-invalidating supersession are applied before other events later in the same batch. A rewind to an older/different SessionRef is represented by ordered old-occurrence end/supersede followed by new-occurrence start; `SESSION_REWOUND` is not a command kind.

## Mailbox capacity and overflow

Initial total capacity is 64 items: 56 ordinary cells, 7 protected cells and one emergency recovery/shutdown cell inside the same mailbox. The partitions are admission reservations, not independent queues; dequeue always follows the single recorded enqueue order.

Admission is nonblocking:

1. Coalesce an eligible ordinary revision in place while preserving the earliest external order and recording every absorbed source ref.
2. If an ordinary item still cannot fit, evict the oldest coalescible ordinary ACTIVE/UPDATE or silence command and record `mailbox_evicted_update`; never evict a result or lifecycle boundary as an ordinary item.
3. A protected item may evict the oldest ordinary item and records the gap.
4. If protected capacity is exhausted, atomically place/refresh `MAILBOX_RECOVERY` in the emergency cell. It carries the latest coherent projections, upstream loss range, current worker snapshots and the incoming protected command's safety effect. Exact intermediate narrative history is marked incomplete; no lost event opportunity is invented.
5. `SHUTDOWN` owns the emergency cell when requested. Existing recovery metadata is attached to shutdown rather than silently erased.

This policy guarantees a bounded nonblocking producer and safe latest truth, not lossless narration under overload. Every loss increments health/tape counters. After recovery, historical/recap claims requiring the lost interval are hard-gated by `history_complete=false`.

## Automatic pipeline transitions

| Current lane | Input/condition | Next lane | Required effects |
| --- | --- | --- | --- |
| `idle` | director selects valid beat | `building` | reserve opportunity if present; create one BeatPlan/token; dispatch one realizer |
| `idle` | no candidate/TTS unavailable | `idle` | record bounded SILENCE/reason; do not consume anything |
| `building` | context makes plan hard-invalid | `idle` | cancel token, release reservation, terminal `invalidated`; replan once |
| `building` | newly admitted candidate outranks plan by frozen arbitration | `building` or `idle` | cancel old token as `replaced` without suppressing it; replan once |
| `building` | stale/mismatched worker token | unchanged | discard callback and record `stale_worker_token` |
| `building` | realization failure/timeout | `idle` | suppress `(beat_id, episode_revision)`, release reservation, replan a different beat once |
| `building` | realization succeeds but verifier rejects | `idle` | same suppression/release; no repair, retry or same-beat authored fallback |
| `building` | verifier passes but freshness commit fails | `idle` | suppress stale revision, release reservation and replan once |
| `building` | verifier and freshness pass | `committed` | dispatch exactly one TTS request/token |
| `committed` | truth/reset/disable/shutdown invalidates request before ack | `stopping` | request cancellation; opportunity remains unconsumed |
| `committed` | ordinary/critical race event | `committed` | reduce truth only; do not replace dispatched utterance |
| `committed` | `PLAYBACK_ACCEPTED` matching token | `speaking` | consume opportunity exactly once; add exposure with full repetition weight |
| `committed` | `SPEECH_FAILED` before ack | `idle` | release and suppress beat/revision; mark TTS degraded when applicable; replan only if TTS remains available |
| `speaking` | ordinary/critical race event | `speaking` | reduce state/opportunities only; no interruption and no prepared text |
| `speaking` | allowed cancellation | `stopping` | request one backend cancellation; consumption is never rolled back |
| `speaking` | completion/failure | `idle` | terminalize exposure, clear token and run one director pass over latest state |
| `stopping` | terminal callback | `idle` or `stopping` | free lane; remain `stopping` only during runtime shutdown |

Allowed automatic cancellation is limited to confirmed stream end, occurrence/run reset, explicit commentary disable, shutdown, or fact/identity supersession that makes the utterance's committed claims false. A newer or more urgent racing event never cancels accepted or dispatched playback.

Attempt suppression occurs only for realization/verification/commit/TTS-before-acceptance failure. Replacement by a new candidate does not suppress a still-valid old beat. Suppression clears only on material episode revision, opportunity/episode terminal state, occurrence reset or stream reset.

## Manual speech

Manual speech is an explicit operator audio test and is available even when automatic commentary is disabled. Admission is serialized through the actor; the API returns 202 only after `MANUAL_SPEAK_REQUEST` moves an idle lane to `building`. Busy or unavailable TTS returns the frozen 409/503 without a waiter.

Manual text passes length/control-character and EN-tag validation, then goes directly to TTS. It creates no NarrativeEvent, EventOpportunity, BeatPlan, Episode transition, ExposureStore row, fatigue or story successor. Race events do not interrupt it. Commentary disable does not cancel it; stream/session resets cancel only narrative speech, while application shutdown cancels both.

## Context/reset matrix

| Boundary | Facts/episodes/opportunities | Building/committed | Speaking narrative | Exposure/history |
| --- | --- | --- | --- | --- |
| iRacing disconnect | suspend current truth; invalidate freshness-dependent opportunities | cancel if required truth unavailable | cancel only if committed claims become false | preserve occurrence and exposure |
| reconnect same ref/no rewind | resume same occurrence | new planning only | unchanged | preserve |
| same-ref confirmed rewind | archive old run facts; create new occurrence revision | cancel | cancel | preserve old as historical according to scope |
| different/new SessionRef | end/supersede old occurrence; activate lineage-selected new one | cancel old occurrence | cancel old occurrence | preserve active ancestors and bounded summaries |
| OBS output unknown | pause OBS-dependent planning/silence timer | cancel only if hard OBS guard required | continue | preserve stream epoch |
| confirmed stream end | close/invalidate all stream state | cancel | cancel | finalize exposure and tape trailer |
| commentary disable | keep upstream projections, stop automatic planning | cancel narrative request | cancel narrative speech; manual continues | preserve exposure until next stream reset/retention |
| process shutdown | no new ingress | cancel | bounded cancel/wait | flush then discard in-memory state |

## Silence deadline transitions

- At confirmed stream start or re-enable during an active stream, arm generation `g+1` for `now + long_silence_s` if OBS state is active and no speech is accepted.
- On `PLAYBACK_ACCEPTED`, cancel the armed deadline. A stale timer token cannot fire.
- On any speech terminal callback, rearm from that callback time when the audience window is active.
- On OBS unknown, cancel while retaining no elapsed credit. On return to active, rearm from return time.
- On `LONG_SILENCE_ELAPSED`, evaluate exactly once. If no speech starts, rearm from command reduction time; never use a shorter retry.
- Race/event director passes do not move the silence origin unless playback is accepted.

## Ordered shutdown

1. Set runtime `stopping` and reject new external/manual ingress.
2. Cancel silence and generation tasks; invalidate their tokens.
3. Request cancellation of committed/speaking TTS and wait only to the configured bounded backend timeout.
4. Enqueue no new director work; reduce the matching terminal callback if it arrives.
5. Ask the tape writer to flush/close and wait at most `shutdown_flush_timeout_s`.
6. Record timeout/drop state through the best available log/manifest path, publish final immutable status and set `stopped`.

No shutdown timeout raises into the main application loop. Worker tasks are owned, named, cancellable and joined or explicitly reported as timed out.

## Closure checks

Issues #235/#284 cannot close until tests or model-based transition enumeration prove:

- every `(lane state, command kind)` is accepted, ignored with a reason, or rejected—never unspecified;
- token mismatch and duplicate callbacks are idempotent;
- no route creates a second generation, playback or waiter;
- every reservation reaches release, consumption or a terminal opportunity state;
- overflow/recovery cannot resurrect lost events or stale facts;
- reset/disable/shutdown cancellation follows the matrix;
- tape replay over reducer sequence reproduces director decisions when recorded Qwen completions are supplied.
