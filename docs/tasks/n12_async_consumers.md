# N12 — Commentary Director V2 async consumer isolation

**Status:** reviewed contract / `needs-engineering`

**Parent:** [observers_decoupling_plan.md](../observers_decoupling_plan.md) V2/N12

**Depends on:** PR #181 live-listen fixes; existing P0 fan-out and P1 scheduler. Do not implement in parallel with #195 because both touch director/composition ownership.

**Behavior default:** unchanged until the V2 composition root replaces the current path

**Critical review:** [n12_async_consumers_spec_review.md](n12_async_consumers_spec_review.md)

**Review disposition:** implementation gaps from the critical review are bound
in the appendix below. The target architecture is unchanged.

## Goal

Replace the logical `overlay -> commentary` chain inside `OverlayRuntime` with
one producer and two independently scheduled consumers. Both consumers see the
same accepted event ids; neither consumer latency, failure, or retry controls
when the other runs.

This task uses “process” as an independently supervised execution lane. V2a is
two `asyncio.Task` workers inside `irswitchd`. The transport boundary is
serialization-safe so V2b can run either lane as a Windows spawned subprocess
if operational isolation is later required. V2a must not rely on shared mutable
objects that would make V2b a redesign.

## Current-state evidence

| Current path | Consequence |
| --- | --- |
| `main.py` creates one `OverlayRuntime.run()` task | Overlay is the composition root for race observation and commentary. |
| `EventFanout.emit()` iterates synchronous `on_envelopes()` callbacks | Consumers are ordered, not independently scheduled. |
| `_emit_from_race()` awaits `_publish()` before speech dispatch | A slow overlay publish delays commentary enqueue. |
| `CommentaryEventConsumer` calls `_observe_commentary()` inline | Director/scheduler work still occupies the overlay race tick. |
| Director uses `OverlayBus.bio`; filler hooks close over `RaceObserver` | Commentary has hidden overlay/runtime dependencies. |
| Sidecars call commentary directly | Not every spoken beat traverses one accepted stream. |
| `take_derived_envelopes()` drains after engine arbitration | Derived events do not share the same arbitration/identity contract. |

## Target ownership

| Owner | Owns | Must not own |
| --- | --- | --- |
| `RacePipeline` (producer) | one telemetry read; context analysis; one RaceObserver; event sources; shared arbitration; batch sequence | HUD bus, commentary director, TTS |
| `AsyncEventFanout` | subscriptions, queue enqueue, immutable batch copies, overflow metrics | consumer policy, rendering, speech |
| `OverlayConsumer` | RaceState presentation, event wire, active HUD stories, overlay tape/bus | CommentaryDirector or TTS |
| `CommentaryConsumer` | Director, opener/brief policy, SpeechScheduler, TTS/duck, commentary decisions | OverlayBus publication or HUD gating |
| composition root (`main.py` or new runtime owner) | create/start/stop/supervise producer + both consumers | domain decisions |

There is one `RaceObserver`. Its watch modules (`aftermath`, `narrative`, flags,
timing hunt, grid story, later modules) return candidates to the producer. A
module does not subscribe to overlay or commentary itself.

## Message contract

Proposed internal types (names may change; semantics may not):

```python
@dataclass(frozen=True)
class ContextSnapshot:
    version: int
    session_id: str
    monotonic_ms: int
    race: RaceStateView
    bio: BioStateView
    story: StoryContextView

@dataclass(frozen=True)
class AcceptedEventBatch:
    stream_sequence: int
    session_id: str
    batch_sequence: int
    accepted_monotonic_ms: int
    context_version: int
    context_payload: FrozenContextSnapshot
    events: tuple[FrozenAcceptedEvent, ...]
```

- `EventEnvelope.event_id` and `sequence` are assigned once before fan-out.
- Queue payloads are immutable or serialized copies. `metrics` and nested
  objects cannot be mutated after publication.
- Empty event batches are forbidden. State snapshots and reset/config boundaries
  use the A3/A4 channels instead of pretending to be an empty event batch.
- Audience/catalog metadata controls what a consumer acts on. It does not create
  a second event identity or a private commentary side path.
- Producer arbitration owns factual acceptance, dedupe, correlation, and event
  identity. Overlay presentation budgets and commentary speech budgets remain
  consumer-local after dequeue; one must not suppress the other.
- Replay stores the accepted batch plus context version so both consumers can be
  driven deterministically without live iRSDK.

## Sidecars that must join the stream

Before deleting the chain, convert these direct paths into producer events:

1. `ENTER_CAR` from `InCarDetector`.
2. Practice/quali/race session intros and SoF/weather briefs.
3. `STREAM_START` from the OBS rising edge.
4. `FIELD_FACT` / `WEATHER_CHANGE` silence candidates.
5. `SESSION_WRAP`, `SESSION_PREVIEW`, aftermath, flags, timing hunt, grid story.

Some are commentary-only, but still receive a normal event id and pass the
shared fan-out. The overlay consumer discards them by audience after dequeue.
Silence watchdog requests should become a message to the producer/RaceObserver
or consume a producer-owned fact snapshot; the commentary worker must not call
a live `RaceObserver` object owned by another lane.

## Queue semantics

### Broadcast, not work stealing

Use two subscriptions / two queues. One queue consumed by two workers is wrong:
each event would reach only one consumer.

### Ordering

- Per consumer: strictly increasing sequence within a session.
- Across consumers: no completion-order guarantee.
- Duplicates after worker restart are safe through event-id idempotency.
- The typed `SessionReset` control item is ordered with event batches and resets
  each consumer exactly once.

### Backpressure

Initial sizes are code constants measured in joint tests; do not expose INI
knobs before evidence.

1. Enqueue to both subscriptions without awaiting consumer work.
2. Coalesce superseded `ACTIVE`/`UPDATE` items with the same dedupe key.
3. Protect terminal/high-value events (`RESULT`, `EXIT`, FINISH, INCIDENT,
   stream/session opener).
4. If capacity still cannot be recovered, evict the oldest lower-priority
   coalescible item and record `consumer_queue_overflow` with consumer, event id,
   sequence, depth, and policy.
5. Never block the telemetry sampling loop on queue space.

Commentary additionally checks event-time TTL when dequeuing. A stale event is
logged as expired, not spoken in present tense. Overlay may apply its own hold
and expiry rules after dequeue without altering the shared envelope.

## Lifecycle and failure isolation

- Start: construct queues -> start overlay worker -> start commentary worker ->
  start producer. No accepted event is published before both subscriptions exist.
- Each worker catches domain exceptions around one batch and continues. A
  worker-level crash is restarted with bounded backoff; it does not cancel its
  sibling.
- Shutdown: stop producer -> bounded drain -> cancel/await consumers -> restore
  ducking and close sinks/tape. Windows cancellation and subprocess termination
  must have tests.
- Config reload passes an immutable config snapshot/control message to each
  owner. Consumers do not reach through `OverlayRuntime` for live settings.
- Health/status is aggregated through public snapshots, never private attribute
  reads across owners.

## Implementation appendix — binding decisions

The contracts in this appendix are required before N12.1. They replace the
earlier implementation choices left open by the architecture section.

### A1 — Canonical envelope freeze API

Mutable `EventEnvelope` exists only in the producer before identity stamping.
The queue and replay boundary uses canonical UTF-8 JSON bytes:

```python
FrozenEnvelope = bytes

def freeze_envelope(envelope: EventEnvelope) -> FrozenEnvelope:
    """Validate and encode one already-stamped envelope as canonical JSON."""

def thaw_envelope(payload: FrozenEnvelope) -> EventEnvelope:
    """Return a new consumer-owned envelope from canonical JSON."""
```

`freeze_envelope` requires a non-empty `event_id`, positive `sequence`, and a
valid envelope. It encodes `envelope.to_dict()` with deterministic key ordering,
compact separators, and UTF-8 (`ensure_ascii=False`). Unsupported/non-JSON
metric values fail the candidate before publication and produce an actionable
producer decision; they do not crash the race loop.

The producer stamps once, freezes once, and never mutates that envelope again.
Both queues may safely reference the same immutable `bytes`; each consumer
thaws its own private object only when required. Tests must prove that mutating
one thawed `metrics` dict cannot affect the frozen payload or the other
consumer. `copy.deepcopy` and `MappingProxyType` are not the transport contract:
the first does not prove future IPC safety and the second is not the replay
format.

`FrozenAcceptedEventBatch` is a frozen dataclass containing only primitives,
tuples, and immutable byte values. Each item is explicit internal metadata plus
the public envelope:

```python
@dataclass(frozen=True)
class FrozenAcceptedEvent:
    envelope: FrozenEnvelope
    audiences: tuple[Literal["overlay", "commentary"], ...]
    source: str
    source_ordinal: int
    coalesce_key: tuple[str, ...] | None
```

`audiences`, source metadata, and `coalesce_key` are internal transport fields;
they do not change the public V4 wire schema. The batch includes the frozen
context payload defined in A3.

### A2 — Engine and RaceObserver derived merge policy

All sources normalize to candidates before the one producer acceptance path:

```text
EventEngine candidates ───────┐
                              ├─ collect in fixed source order
RaceObserver watch candidates ┘
       → validate/dedupe within audience+channel
       → assign correlation/event id + global session sequence once
       → freeze → one AcceptedEventBatch → both subscriptions
```

Behavior-preserving source order for V2a is:

1. existing `EventEngine.tick()` registration order;
2. RaceObserver `narrative`;
3. `aftermath`;
4. `flags`;
5. `timing_hunt`;
6. `grid_story`;
7. filler response candidates requested under A5.

RaceObserver watch modules must return candidates, not pre-published envelopes.
During migration, an adapter may normalize an existing derived envelope into a
candidate, but only the producer may assign its final event id and sequence.

Acceptance/dedupe is scoped by `(audience, channel)`. Commentary-only facts
therefore cannot evict a HUD story, while both subscribers still receive and
account for the accepted event. Producer acceptance does not apply TTS busy,
cooldown, or voice priority.

Same-tick incident policy is explicit:

- factual `INCIDENT` and `INCIDENT_AFTERMATH` may both be accepted and receive
  consecutive sequence numbers;
- `INCIDENT_AFTERMATH` is commentary-only and cannot evict the HUD incident;
- `CommentaryDirector._prefer_incident_over_aftermath` remains the consumer
  rule that speaks at most one from the same batch, preferring `INCIDENT`;
- producer arbitration must not silently drop the aftermath fact because it may
  still be useful for replay/debug and a later recovery transition.

Existing priorities, cooldowns, event types, and fixed source order are
characterized in N12.0 before this merge changes runtime ownership.

### A3 — ContextSnapshot schema and delivery

`ContextSnapshot` is versioned and frozen/encoded with the same canonical JSON
rules as envelopes. Schema `n12-context/1` contains:

| Section | Required fields |
| --- | --- |
| identity | `schema_version`, `version`, `session_id`, `captured_monotonic_ms`, `overlay_mode`, `session_type`, `session_num`, `subsession_id`, `track_id` |
| race | `connected`, `player_car_idx`, `lap`, `lap_completed`, `position`, `class_position`, `gap_ahead_s`, `gap_behind_s`, `on_pit_road`, `session_checkered`, `player_finished`, `mute_field`, `incident_count`, `speed_mps` |
| bio | `status`, `bpm`, `hr_state`, `sample_monotonic_ms` |
| story | hero display/speakable names, 2+2 near-field ids/names/gaps, leader name/position, localized weather bindings, quali bag, stream session keys |
| config identity | immutable config generation plus `language`, `commentary_enabled`, scheduler flags required for the decision |

Missing optional telemetry stays `null`; no consumer reaches back to live
objects to fill it. Slot values already carried by an accepted envelope remain
authoritative for that event.

Each consumer subscription owns:

- a bounded FIFO for event/control stream items; and
- a replace-only `latest_context` slot which does not consume FIFO capacity.

Context-only updates are capped by configured race sampling frequency (5 Hz by
default), replace the previous `latest_context`, and do not count as event queue
lag. Every non-empty `AcceptedEventBatch` also embeds the exact frozen context
used during acceptance, so commentary never performs a version lookup and
replay cannot pair an event with a later HR/session state. Empty event batches
are forbidden.

### A4 — One typed control plane

Reset and config reload use typed control messages outside `EventEnvelope`.
Do not invent `CONTROL_*` speech/HUD events and do not keep a second hidden
callback path.

```python
StreamItem = FrozenAcceptedEventBatch | SessionReset | ConfigUpdate
```

Every `StreamItem` has a producer-global `stream_sequence`. Both subscription
FIFOs receive the same item order.

- `SessionReset(old_session_id, new_session_id, reason, stream_sequence)` is the
  only consumer reset boundary. It is enqueued before any event from the new
  session. Each consumer acknowledges/applies it once.
- `ConfigUpdate(generation, frozen_config, stream_sequence)` is the only reload
  path. Each owner applies only its documented subset.
- Shutdown is supervisor lifecycle, not an event or config message.

Producer-local analyzers and the one RaceObserver reset at the same detected
boundary before new-session candidate collection. Consumer reset hooks through
`OverlayRuntime` are removed in N12.3.

### A5 — Silence filler request/response

Commentary never calls a live RaceObserver. The replacement is a bounded typed
request queue from CommentaryConsumer to the producer:

```python
FillerRequest(
    request_id: str,
    session_id: str,
    requested_monotonic_ms: int,
    locale: str,
    last_spoken_event_id: str | None,
)
```

- Queue capacity is one outstanding request per commentary consumer. While a
  request for the same session awaits a result/event, repeated silence ticks do
  not allocate a new `request_id`; the existing request remains outstanding.
- The producer drains requests before candidate collection on the next race
  tick, rejects a stale/wrong-session request, and asks its RaceObserver for the
  next weather/field candidate using producer-owned cooldown/rotation state.
- A fact becomes a normal `FIELD_FACT` or `WEATHER_CHANGE` candidate, then passes
  A2 arbitration, stamping, freeze, and broadcast. Commentary hears it only
  when it later dequeues the accepted event; overlay sees and ignores its
  commentary-only audience.
- When no fact is available, the producer returns a typed
  `FillerResult(request_id, status="no_fact" | "stale" | "disabled")` to the
  commentary response inbox for decision logging. This reverse-channel result
  is not a shared `StreamItem` and is not an `EventEnvelope`.
- There is no synchronous response, reverse callback, or shared RaceObserver
  reference. Request age is measured from `requested_monotonic_ms`.

### A6 — Queue coalescing contract

Only `ACTIVE` and `UPDATE` may be coalesced. Freeze computes an optional
`coalesce_key`; absence means the item is never coalescible.

| Family | Coalesce key | Rule |
| --- | --- | --- |
| battle (`HUNTING`, `HUNTED`, `SIDE_BY_SIDE`, attack-range updates) | `(session_id, event_type, correlation_id)` where correlation includes hero + target car | replace older ACTIVE/UPDATE for the same battle only |
| sector/timing progress | `(session_id, event_type, subject.car_id, lap, sector_id)` | UPDATE only; never RESULT/PB/lap completion |
| pit active story | `(session_id, event_type, correlation_id)` where correlation is the pit-cycle id | replace active progress within one stop |
| bio/system active warning | `(session_id, event_type, subject.car_id, correlation_id)` | replace active sample; preserve EXIT/RESULT |
| incident, finish, flags, opener, session brief, all RESULT/EXIT | none | never coalesce or evict as a superseded update |

Adapters must provide the correlation components before freeze. The generic
fallback dedupe key is not sufficient evidence for coalescing. If a family lacks
a proven key, treat it as non-coalescible and surface queue pressure in N12.4.

On overflow, first replace an existing equal `coalesce_key`, then evict the
oldest lower-priority coalescible item. A protected/non-coalescible item is never
silently dropped; failure to admit it marks that consumer degraded and records
the event id, queue depth, and policy. Because a finite non-blocking queue cannot
guarantee delivery through an unbounded consumer stall, this condition restarts
that consumer and accounts for every item discarded during recovery. The
producer still does not wait for consumer work.

### A7 — Deterministic replay bundle

N12 capture uses JSONL schema `n12-replay/1` with canonical payloads:

| Row | Contents |
| --- | --- |
| `header` | schema version, source commit, config generation/digest, locale, capture start monotonic origin |
| `context` | context version, captured monotonic offset, full A3 payload including bio/HR |
| `control` | stream sequence and serialized SessionReset/ConfigUpdate |
| `events` | stream sequence, batch sequence, accepted monotonic offset, context version, frozen accepted-event records |
| `expected` (test fixture only) | overlay wire ids and commentary decision/speech ids used as assertions |

Contexts are written before the first event/control row that references their
version. Replay restores the relative monotonic timeline, feeds the same
subscription interfaces, and never reads live iRSDK, OBS, bio, or config.
Production capture may omit `expected`; deterministic tests keep it beside the
input rather than teaching the producer about consumer output.

### A8 — Producer timing and restart idempotence

At default 5 Hz under full queues and fake consumers that never dequeue:

- fan-out publication uses no await on consumer work and completes within a
  50 ms test deadline per batch;
- over a 500-batch stress fixture, producer tick p95 stays below the configured
  poll interval; report the measured p95 rather than hiding a slow run;
- queue depth never exceeds capacity and every coalesce/eviction is accounted.

V2a supervision restarts the failed worker task around the **same consumer
instance**, preserving scheduler/cooldown state and a bounded per-session ledger
of processed event ids. A duplicate event id records `duplicate_event` and
causes no second HUD publish or speech. `SessionReset` clears the prior-session
ledger only after the ordered boundary is applied. V2b durable acknowledgements
remain part of optional N12.5, not an implied V2a disk database.

## Implementation slices

### N12.0 — Characterization

- Capture event ids/sequences, overlay wires, commentary decisions, tape rows,
  reset order, and direct sidecars for deterministic fixtures.
- Add a test proving the current synchronous delay; it becomes the V2 regression
  test when the implementation changes.
- Freeze fixtures for source order, current derived priorities/cooldowns,
  incident/aftermath same-tick behavior, and context fields required by both
  consumers.

### N12.1 — Extract producer

- Move telemetry/race tick, EventEngine, EventManagerV2, one RaceObserver, and
  accepted-batch creation out of `OverlayRuntime` into a peer runtime.
- Merge RaceObserver-derived candidates into shared arbitration.
- Implement A1–A5 contracts: freeze API, fixed derived merge, embedded context,
  typed reset/config control plane, and filler request/result path.
- Do not change content, priorities, cooldowns, or public wire schema.

### N12.2 — Async fan-out and peer consumers

- Replace synchronous `EventConsumer.on_envelopes()` with owned async queue
  subscriptions.
- Add `OverlayConsumer` and refactor `CommentaryEventConsumer` into its own run
  loop.
- Enqueue the identical frozen batch to both before yielding to consumer work.
- Implement A6 coalescing and processed-event idempotence ledger.

### N12.3 — Remove private chain

- Convert all sidecars listed above to the accepted stream.
- Remove `_observe_commentary`, `_dispatch_speech_envelopes`, commentary filler
  closures, and `OverlayRuntime` ownership of director/scheduler/TTS.
- `overlay/` must not import `commentary/`; `commentary/` must not read
  `OverlayBus`.

### N12.4 — Operations and replay

- Queue/lag/restart status, structured overflow logs, deterministic replay,
  bounded shutdown, config reload, and failure injection.
- Live joint test with deliberately slow TTS and deliberately slow WebSocket
  clients.
- Implement A7 replay bundle and publish A8 queue/lag/timing evidence.

### N12.5 — Optional literal OS-process split

Only after V2a metrics show a need. Keep producer in the main service and run
overlay and/or commentary behind the same subscription interface using Windows
`spawn`-safe IPC. No fork assumptions, no duplicate iRSDK reader, and no new
dependency without approval. The async task implementation remains the default
until this slice is explicitly approved.

## Acceptance criteria

- [ ] Exactly one RaceObserver and one shared arbitration path exist.
- [ ] With no overflow, overlay and commentary observe identical ordered event-id
  and sequence lists.
- [ ] Sleeping/blocking a commentary fake does not delay overlay publication or
  the producer tick; the inverse also holds.
- [ ] An exception/restart in one consumer does not stop or reset the other.
- [ ] Sidecars and derived events use the shared accepted stream; no direct
  overlay-to-director call remains.
- [ ] Queue overflow/coalescing is deterministic, priority-aware, and visible in
  status/logs.
- [ ] `freeze_envelope` canonical bytes are identical for identical payloads;
  thawed consumer mutations are isolated.
- [ ] Engine and derived events use the A2 source order and a single sequence
  allocator; same-tick incident/aftermath speaks at most once.
- [ ] Silence filler uses the A5 request/result path with no callback/shared
  RaceObserver object.
- [ ] Session reset and config reload reach both consumers once in sequence.
- [ ] No empty event batch enters a FIFO; context-only updates use the bounded
  replace-only latest slot at no more than race sampling frequency.
- [ ] TTS TTL/cooldown uses event time; queue wait is observable lag.
- [ ] Cancellation leaves no pending task, TTS process, ducked OBS source, or
  open tape handle.
- [ ] Replay of one captured accepted stream deterministically drives both
  consumers.
- [ ] With full queues and non-draining consumers, fan-out meets the 50 ms
  deadline, producer tick p95 stays below the configured poll interval, and
  queue accounting is complete.
- [ ] Restarting a worker around the same consumer instance does not duplicate
  HUD publication or speech for an already processed event id.
- [ ] Existing overlay wire, commentary copy, priority, graph, and INI defaults
  remain unchanged unless a later slice explicitly changes them.

## Required tests

- Async unit: broadcast parity, per-consumer order, no cross-consumer order
  assumption, canonical freeze/thaw isolation, A6 overflow/coalescing,
  idempotent duplicate.
- Failure: consumer exception, restart/backoff, full queue, cancelled producer,
  cancelled consumer, bounded shutdown.
- Integration: slow commentary vs overlay latency; slow overlay vs commentary;
  session reset mid-queue; config reload; stream-start/in-car mutex; derived
  incident plus engine incident arbitration.
- Integration fixture: 20 battle UPDATEs at 5 Hz coalesce while FINISH is never
  evicted; incident + aftermath + flag in one producer batch follows A2 order.
- Filler fixture: request available/no-fact/stale paths with no live observer
  reference in CommentaryConsumer.
- Replay/tape: one A7 capture including context/HR timeline produces expected HUD
  wire and commentary decisions independently.
- Architecture grep/import test: `overlay/` has no `CommentaryDirector` import or
  direct observe callback; commentary has no `OverlayBus` dependency.

## Config and dependency impact

- N12 specification adds no runtime key and changes no default.
- Queue sizes remain internal until joint-test evidence justifies configuration.
- No database and no new package dependency are required for V2a.
- A literal subprocess transport is a separately approved slice and must update
  `CONFIG.md`, `config/config.example.ini`, service packaging, and Windows
  shutdown documentation if it becomes selectable.
