# N12 — Commentary Director V2 async consumer isolation

**Status:** proposed / `needs-engineering`

**Parent:** [observers_decoupling_plan.md](../observers_decoupling_plan.md) V2/N12

**Depends on:** PR #181 live-listen fixes; existing P0 fan-out and P1 scheduler

**Behavior default:** unchanged until the V2 composition root replaces the current path

**Critical review:** [n12_async_consumers_spec_review.md](n12_async_consumers_spec_review.md)

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
    session_id: str
    batch_sequence: int
    accepted_monotonic_ms: int
    context_version: int
    envelopes: tuple[FrozenEventEnvelope, ...]
```

- `EventEnvelope.event_id` and `sequence` are assigned once before fan-out.
- Queue payloads are immutable or serialized copies. `metrics` and nested
  objects cannot be mutated after publication.
- A batch may contain no events only when it carries a required state/control
  boundary; otherwise do not enqueue empty ticks.
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
- A session/reset boundary is ordered with event batches and resets each
  consumer exactly once.

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

## Implementation slices

### N12.0 — Characterization

- Capture event ids/sequences, overlay wires, commentary decisions, tape rows,
  reset order, and direct sidecars for deterministic fixtures.
- Add a test proving the current synchronous delay; it becomes the V2 regression
  test when the implementation changes.

### N12.1 — Extract producer

- Move telemetry/race tick, EventEngine, EventManagerV2, one RaceObserver, and
  accepted-batch creation out of `OverlayRuntime` into a peer runtime.
- Merge RaceObserver-derived candidates into shared arbitration.
- Do not change content, priorities, cooldowns, or public wire schema.

### N12.2 — Async fan-out and peer consumers

- Replace synchronous `EventConsumer.on_envelopes()` with owned async queue
  subscriptions.
- Add `OverlayConsumer` and refactor `CommentaryEventConsumer` into its own run
  loop.
- Enqueue the identical frozen batch to both before yielding to consumer work.

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
- [ ] Session reset and config reload reach both consumers once in sequence.
- [ ] TTS TTL/cooldown uses event time; queue wait is observable lag.
- [ ] Cancellation leaves no pending task, TTS process, ducked OBS source, or
  open tape handle.
- [ ] Replay of one captured accepted stream deterministically drives both
  consumers.
- [ ] Existing overlay wire, commentary copy, priority, graph, and INI defaults
  remain unchanged unless a later slice explicitly changes them.

## Required tests

- Async unit: broadcast parity, per-consumer order, no cross-consumer order
  assumption, immutable payload, overflow/coalescing, idempotent duplicate.
- Failure: consumer exception, restart/backoff, full queue, cancelled producer,
  cancelled consumer, bounded shutdown.
- Integration: slow commentary vs overlay latency; slow overlay vs commentary;
  session reset mid-queue; config reload; stream-start/in-car mutex; derived
  incident plus engine incident arbitration.
- Replay/tape: one accepted capture produces expected HUD wire and commentary
  decisions independently.
- Architecture grep/import test: `overlay/` has no `CommentaryDirector` import or
  direct observe callback; commentary has no `OverlayBus` dependency.

## Config and dependency impact

- N12 specification adds no runtime key and changes no default.
- Queue sizes remain internal until joint-test evidence justifies configuration.
- No database and no new package dependency are required for V2a.
- A literal subprocess transport is a separately approved slice and must update
  `CONFIG.md`, `config/config.example.ini`, service packaging, and Windows
  shutdown documentation if it becomes selectable.
