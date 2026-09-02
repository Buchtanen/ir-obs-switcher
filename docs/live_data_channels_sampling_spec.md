# Live data channels and adaptive sampling

**Status:** specification / `needs-engineering`

**Issue:** [#212](https://github.com/Buchtanen/ir-obs-switcher/issues/212)

**Baseline:** this document is delivered from the current `master` as a docs-only
change. That baseline still has synchronous `EventFanout` callbacks and separate
polling in `main.py` and `OverlayRuntime`.

**Prerequisite:** [N12 async consumer isolation](tasks/n12_async_consumers.md) must
land on `master` first. Any implementation of this specification starts by
updating its branch from that post-N12 `master`; this branch does not merge or
reimplement N12.

## 1. Problem

The current process reads overlapping iRacing data in more than one loop and
recomputes broad race context at one common cadence. This is simple, but it
couples data acquisition, detection, presentation, and commentary:

- fast facts needed for battle, incident, pit, flag, finish, and crossing
  detection share a cadence with slow facts such as weather and machine load;
- continuous live state has no explicit publication contract, so a consumer
  either reaches into another owner or receives repeated unchanged snapshots;
- a slow consumer can occupy an inline callback today; N12 fixes event delivery,
  but does not define how consumers obtain changing live state economically;
- exact event-time evidence and a consumer's newest live view are different
  needs and must not be confused.

The target is one sampler owner, different source cadences, and two deliberately
different delivery semantics: ordered facts for events and latest-only state for
live views.

## 2. Goals

1. Give overlay and commentary independent, explicit access to the same live
   data without either consumer owning or polling the source.
2. Preserve ordered, bounded, independently consumed accepted events from N12.
3. Sample each data class only as often as its decisions require.
4. Keep fast safety- and story-relevant detectors at the race sampling cadence.
5. Preserve exact event-time context while allowing change-driven live updates.
6. Make overload, staleness, and data volume measurable and deterministic.

## 3. Non-goals

- This specification does not implement N12 or change current runtime behavior.
- It does not introduce a general message broker, subprocess transport, or a new
  dependency.
- It does not reduce the cadence of incident, battle, pit, flag, finish, lap, or
  crossing detection without separate evidence and a product decision.
- Continuous weather and system snapshots do not enter the accepted-event FIFO.
  Meaningful `WEATHER_CHANGE` and weather-filler candidates still follow N12
  factual arbitration; system telemetry remains live state unless separately
  specified.
- It does not add public API or configuration keys in this docs-only change.

## 4. Relationship to N12

N12 remains the authority for accepted-event identity, arbitration, immutable
event-time context, bounded per-consumer queues, reset/config boundaries, and
independent overlay/commentary workers. This specification extends that design
after N12 with:

- a process-wide telemetry sampler instead of overlapping reads;
- a latest-only state hub for continuous data;
- domain-specific sampling and publication policies;
- a small live guard view for decisions that legitimately depend on current
  state at dequeue time;
- separate filler-request and presentation-lifecycle channels.

No rule here permits a current snapshot to rewrite the historical context
attached to an accepted event.

## 5. Target architecture

```text
                     iRSDK / OS / OBS / BLE
                              │
                    TelemetrySampler (one owner)
                              │
             ┌────────────────┴────────────────┐
             │ grouped source samples          │ versioned source state
             ▼                                 ▼
      RacePipeline (post-N12)             LiveStateHub
      analyze → observe → arbitrate       latest-only domain slots
             │                                 │
             ▼                                 ├──────────────┐
      AcceptedEventChannel                     ▼              ▼
      ordered, bounded broadcast         OverlayConsumer  CommentaryConsumer
             │                                 ▲              ▲
             ├─────────────────────────────────┘              │
             └────────────────────────────────────────────────┘

      CommentaryConsumer ── FillerRequestMailbox ──> RacePipeline
      OverlayConsumer     ──┐
      CommentaryConsumer  ──┴─ PresentationLifecycle ─> interested observers
```

### 5.1 Ownership

| Owner | Owns | Must not own |
| --- | --- | --- |
| `TelemetrySampler` | source connections, grouped reads, source revisions, timestamps, cadence, reconnect/backoff | event policy, HUD, speech |
| `RacePipeline` | fast analysis, one `RaceObserver`, candidates, arbitration, exact context freeze | source polling, HUD/TTS policy |
| `AcceptedEventChannel` | N12 ordered broadcast and per-consumer bounded queues | live-state storage, consumer decisions |
| `LiveStateHub` | latest immutable value per domain, revision, freshness, conflation metrics | event ordering, history, polling |
| `OverlayConsumer` | HUD projection, dirty publication, presentation lifecycle | telemetry reads, commentary policy |
| `CommentaryConsumer` | director, filler policy, speech scheduling, live guards | telemetry reads, overlay gates |
| composition root | construction, task ownership, supervision, shutdown order | domain decisions |

## 6. Channel contracts

### 6.1 Accepted events: ordered bounded broadcast

Use the N12 `AcceptedEventBatch` contract. Every subscriber has its own bounded
queue, delivery order, overflow policy, and health metrics. A blocked or failed
consumer cannot delay the producer or another consumer. Event ids and context
are assigned once before fan-out.

This channel carries discrete accepted facts, not periodic state snapshots.
Empty event batches remain forbidden.

### 6.2 Live state: latest-only conflated domains

Continuous data is published through domain slots. Updating a slot replaces its
previous unread value; consumers read or await the newest revision. Intermediate
values may be conflated by design because this channel represents current state,
not history.

```python
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

@dataclass(frozen=True)
class VersionedState(Generic[T]):
    domain: str
    source_revision: int
    sampled_monotonic_ms: int
    published_monotonic_ms: int
    freshness: str  # fresh | held | stale | unavailable
    value: T
```

Initial domain split:

| Domain | Examples | Publication |
| --- | --- | --- |
| `race.fast` | session time/state, hero position/speed, lap, pit, flags, nearby cars | on semantic change, capped by fast sample rate |
| `race.context` | analyzed `RaceStateView`, near field, leader, story facts | on semantic change |
| `weather` | air/track temperature, wind, precipitation/wetness, skies | slow sample + meaningful change |
| `session.static` | session/weekend/driver metadata | source revision change; fallback probe |
| `system` | CPU/GPU/load/temperatures when enabled | slow sample + meaningful change |
| `bio` | external bio sensor state | push from source |
| `obs` | streaming/recording/scene state | push or OBS reconciliation |

A slow subscriber cannot build an unbounded backlog: it receives the latest
revision and the count of conflated updates is observable.

### 6.3 Exact context and live guards

An accepted event carries the frozen context version and payload defined by N12.
That payload is the evidence for replay, rendering, and speech framing. Slow or
static fields in it include their own source revision, sample time, and freshness
so a held value is explicit.

Those additions are a new `n12-context/2` schema, not a silent mutation of
N12's `n12-context/1`. Decoders and replay fixtures retain explicit support for
`n12-context/1`; every recording declares its schema version and an unsupported
future version fails visibly rather than being guessed.

Consumers may also read a deliberately small `LiveGuardState` for current-time
vetoes such as "stream is no longer live" or "session generation changed". A
guard can suppress or defer an action; it cannot edit the event, replace its
historical facts, or silently reframe it using newer data.

### 6.4 Filler requests: dedicated latest request mailbox

Commentary silence policy sends a typed filler request to the producer-owned
story/fact path. The mailbox keeps at most one outstanding request per
commentary consumer, as required by N12 A5; equivalent silence ticks retain the
same request id. The response returns through accepted arbitration
as a normal event or an explicit no-candidate result. Commentary must not reach
into `RaceObserver` or `OverlayBus` to obtain filler facts.

### 6.5 Presentation lifecycle: latest state per story

HUD `shown`, `updated`, and `ended` feedback from `OverlayConsumer`, plus speech
`queued`, `started`, `finished`, and `cancelled` feedback from
`CommentaryConsumer`/`SpeechScheduler`, is separate from factual events. It uses
a bounded latest slot per `(consumer, story_id)` so presentation state cannot
delay race detection. Producer-side observers or policy modules subscribe only
when they need presentation-aware cooldown/lifecycle policy. The channel must
not become a second path for accepted race facts.

### 6.6 Control plane

Session reset and config generation use the ordered `SessionReset` and
`ConfigUpdate` controls from N12. They are never encoded as fake empty event
batches or live-state values. A source disconnect/reconnect is represented by
that domain's freshness/revision transition; a session identity change still
emits `SessionReset`. Session generation is carried by all relevant messages so
delayed work from an old generation can be rejected deterministically.

Shutdown is supervisor lifecycle, not a published stream item: stop production,
bounded-drain, cancel/await workers, then close sources.

## 7. Sampling model

Sampling cadence is selected by the fastest decision that consumes a source,
not by the fastest loop in the process. Candidate defaults below are starting
points for measurement, not new configuration defaults in this PR.

During M1 compatibility, the shared iRSDK capture rate is
`max(iracing.poll_hz, sampling.race.hz)`. Separate monotonic due-time gates feed
the mode selector at `iracing.poll_hz` and race selectors at
`sampling.race.hz` from the newest immutable capture. This preserves both
existing keys without duplicate reader calls. A later decision to unify or
deprecate the keys requires its own config migration and documentation.

| Group | Candidate cadence | Rationale |
| --- | ---: | --- |
| fast race dynamics | existing `sampling.race.hz` (default 5 Hz; current cap 30 Hz) | incidents, battle, pit, flags, finish, laps, crossings |
| live-state publication | change-driven, at most fast cadence | consumers need changes, not duplicate ticks |
| weather | 0.5 Hz (every 2 s) | environmental change is slow; freshness stays visible |
| session/static metadata | on iRSDK session-info revision; 0.2 Hz fallback probe | YAML/static data changes rarely |
| system telemetry | 1 Hz when enabled | sufficient for health/HUD trends unless measured otherwise |
| bio sensors | source push; optional heartbeat only for liveness | preserve native update semantics |
| OBS | source push plus bounded reconciliation | edge-sensitive external state |
| config | reload edge → ordered `ConfigUpdate`; no polling | control-plane generation change |

### 7.1 Fast evaluation is not fast publication

The sampler supplies each fast race sample to the pipeline. Stateful detectors
evaluate every such sample even when the public live view has not changed. Their
previous-value latches, thresholds, and monotonic timers therefore keep the same
temporal meaning.

The state hub publishes only when a domain's canonical semantic value changes or
when a bounded heartbeat is required to communicate liveness. This reduces
serialization and WebSocket traffic without decimating detection.

### 7.2 One shared source sample

Within a fast cycle, all selectors derive from one immutable source sample and
one monotonic timestamp. `main.py`, the race pipeline, and consumers do not issue
independent reads for the same iRSDK variables. Expensive derived views are
computed once per needed revision and reused.

When the two existing rate keys differ, mode and race due-time gates may reuse a
capture but never run above their requested rate. Source capture itself uses the
higher requested rate, so neither selector can force a second SDK read.

### 7.3 Slow and static fields

Slow selectors retain their last value between samples. A context freeze records
that the value is held and its age. When age exceeds the domain's explicit stale
budget, freshness becomes `stale`; consumers choose a documented fallback and do
not present the value as current. Missing data becomes `unavailable`, distinct
from a legitimate zero/empty value.

Session, weekend, and driver metadata primarily follow the iRSDK session-info
revision. The low-rate probe exists for reconnects or adapters that cannot expose
the revision reliably.

### 7.4 Change detection

Each domain defines a canonical comparison:

- discrete values compare exactly;
- floats use domain units and a documented epsilon/hysteresis;
- collections use stable ordering and only fields relevant to consumers;
- weather/system values use meaningful display or decision thresholds;
- a freshness transition is itself a change;
- optional heartbeats carry the same source revision and are counted separately.

Change detection occurs before serialization. Consumers must not each invent
different tolerances for the same shared live field.

## 8. Backpressure, failure, and shutdown

- Accepted-event overflow follows the explicit N12 per-consumer policy and is
  never silently conflated.
- Live-state overflow replaces an unread revision by design and increments a
  conflation counter.
- Source failure retains the last value only until its stale budget expires.
  Reconnect/backoff never crashes the main loop.
- A selector failure marks only its domain unavailable; the fast pipeline and
  unrelated domains continue.
- Background tasks are owned and cancellable. Shutdown stops production, drains
  according to N12 policy, cancels/awaits workers, and closes sources in a
  deterministic order without publishing a shutdown item.

## 9. Observability

Expose at least these per-source/domain signals:

| Signal | Purpose |
| --- | --- |
| source reads/s and read duration | prove that slow groups are actually slow |
| source revision and sample age | distinguish fresh, held, stale, unavailable |
| selector duration/failures | locate expensive or unreliable derivation |
| samples / semantic changes / heartbeats | quantify unchanged work avoided |
| context freezes/s and frozen bytes | measure event-context cost |
| event queue depth, drops, lag, consumer health | retain N12 isolation evidence |
| state updates, conflations, subscriber lag | prove latest-only behavior |
| WebSocket messages/s and bytes/s | verify downstream traffic reduction |

Metrics must not introduce high-cardinality labels such as event id, driver name,
or session id.

## 10. Migration plan

| Phase | Change | Exit evidence |
| --- | --- | --- |
| M0 | Merge N12; add baseline read/queue/state/WS metrics | post-N12 `master`, recorded baseline |
| M1 | Introduce `TelemetrySampler`; route existing fast behavior through one shared sample | parity tests; no duplicate iRSDK reads |
| M2 | Add `LiveStateHub`; move overlay/commentary live reads to domain subscriptions | independent consumers; bounded conflation |
| M3 | Split weather, static, and system selectors to measured slower cadences | detector parity; lower reads/CPU/bytes |
| M4 | Add freshness metadata, change-driven WS publication, and context-freeze economy | replay fidelity; stale tests; traffic comparison |
| M5 | Remove remaining cross-owner reads; document tuned defaults | architecture checks and operational evidence |

Each phase is separately releasable and keeps the main loop stable. Cadence
reductions are measured after instrumentation rather than bundled as assumptions.

## 11. Verification plan

### Unit

- cadence scheduler uses monotonic time and does not accumulate drift;
- exact/epsilon/hysteresis comparisons publish only semantic changes;
- state slots conflate to the latest revision and report skipped revisions;
- held → stale → unavailable transitions are deterministic;
- session generation rejects delayed old work;
- event context remains immutable when live state advances.

### Integration and replay

- one recorded fast trace produces the same accepted detector events before and
  after M1/M3;
- overlay and commentary consume independently when either worker is slow or
  fails;
- weather/static/system reads match their cadence bounds while fast detectors
  still evaluate every race sample;
- a delayed event renders/speaks from its event-time context and may be vetoed,
  but not rewritten, by a live guard;
- reconnect/reset/shutdown leave no orphan task and no old-generation output;
- unchanged input materially reduces state/WS messages and bytes.

### Manual operational check

Compare a representative practice/race capture before and after each cadence
change: source reads/s, CPU, queue lag, context bytes, WS bytes, event ids/order,
and visible/spoken story output.

This PR is documentation-only, so it takes the TDD exception: no behavior exists
to drive with a failing runtime test. Verification for this change is Markdown
link validation, whitespace/diff checks, and consistency review. Runtime tests
are mandatory in the implementation phases above.

## 12. Acceptance criteria

- [ ] Implementation starts only after N12 is merged and the implementation
      branch is updated from that post-N12 `master`.
- [ ] Exactly one runtime owner reads each external source/group.
- [ ] Accepted events retain N12 ordered bounded per-consumer delivery and exact
      immutable event-time context.
- [ ] Continuous domains use latest-only versioned state with explicit freshness.
- [ ] Fast detectors evaluate every configured race sample; slow sampling applies
      only to proven slow/static selectors.
- [ ] Overlay and commentary have no cross-owner polling or mutable live-state
      reach-through.
- [ ] Filler and presentation lifecycle use their dedicated bounded contracts.
- [ ] Reset/config controls are ordered and generation-safe; reconnect freshness
      and supervisor-owned shutdown follow their distinct contracts.
- [ ] Cadence, staleness, conflation, queues, and downstream byte volume are
      observable without high-cardinality metrics.
- [ ] Replay/parity evidence shows no lost, reordered, or historically rewritten
      accepted event.

## 13. Configuration and documentation impact

No runtime configuration, public API, dependency, or behavior changes in this
specification PR. Candidate rates are intentionally not added to
`config.example.ini` until M0 measurements validate them. An implementation PR
must update configuration reference/example, architecture docs, troubleshooting,
and release notes for every user-visible or operational contract it changes.

## 14. Resolved decisions and open measurements

Resolved:

- events and live state are separate channel classes;
- event context is historical and immutable; live guards are current and small;
- live state conflates, accepted events do not;
- weather/static/system can be slower, fast race detection cannot be casually
  decimated;
- N12 lands first and remains authoritative for async event delivery.

Measure before locking implementation defaults:

- the lowest safe weather and system cadence for current UI precision;
- domain epsilon/hysteresis and stale budgets;
- whether a liveness heartbeat is needed per domain and at what maximum period;
- context-freeze CPU/bytes and whether structural sharing is worthwhile;
- acceptable queue/drop/conflation alert thresholds on the stream PC.
