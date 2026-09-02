# N12 — Commentary Director V2 async consumer isolation

**Status:** reviewed contract / `needs-engineering`

**Parent:** [observers_decoupling_plan.md](../observers_decoupling_plan.md) V2/N12

**Depends on:** PR #181 live-listen fixes; existing P0 fan-out and P1 scheduler. Do not implement in parallel with #195 because both touch director/composition ownership.

**Behavior default:** unchanged until the V2 composition root replaces the current path

**Critical review:** [n12_async_consumers_spec_review.md](n12_async_consumers_spec_review.md)

**Review disposition:** implementation gaps from the critical review are bound
in the appendix below. The target architecture is unchanged.

**Post-N12 refinement:** [live data channels and adaptive sampling](../live_data_channels_sampling_spec.md)
adds a single sampler owner, latest-only live-state domains, and slower cadences
for proven slow/static inputs. It is not part of the initial N12 landing. Its
implementation must start from `master` after N12 merges, while preserving this
document's accepted-event and exact event-time context contracts.

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

#### A2.1 — Independent front/rear battle relations and composite branch

`hunting` and `hunted` are not mutually exclusive modes. They are independent
relations owned by separate FSM tracks:

```text
front relation: hero -> car ahead   (hunting / approach / attack_range / side_by_side)
rear relation:  car behind -> hero  (hunted)

front ACTIVE + rear ACTIVE
  -> parents remain ACTIVE
  -> additionally derive BATTLE_FOR_POSITION / two_front_battle
```

Acceptance, dedupe, active-story storage, queue coalescing, and cooldown state
must key the parents by `(session_id, direction, hero_car_idx, target_car_idx,
relation_epoch)`. A generic `channel="battle"`, priority comparison, or shared
story slot must never let the front relation evict the rear relation or the
reverse. Both parent event ids remain visible to overlay, commentary accounting,
replay, and diagnostics.

The existing `BATTLE_FOR_POSITION` meta event becomes a third derived fact, not
a replacement. Its payload and frozen context must carry both sides explicitly:

```python
TwoFrontBattleFacts(
    hero_position: int | None,
    front_target_car_idx: int,
    front_target_name: str | None,
    front_target_position: int | None,
    front_gap_s: float | None,
    front_relation_epoch: int,
    rear_target_car_idx: int,
    rear_target_name: str | None,
    rear_target_position: int | None,
    rear_gap_s: float | None,
    rear_relation_epoch: int,
)
```

`BATTLE_FOR_POSITION` correlation is
`battle:two-front:<hero>:<front>:<rear>:<front_epoch>:<rear_epoch>`. It may
enter only while both parents are ACTIVE and exits immediately when either
parent exits, changes target, changes session, enters pit suppression, or fails
the 3-second relation freshness gate. The surviving parent remains ACTIVE; it
is not re-entered merely because the composite ended.

Deterministic same-tick order is parent facts first, composite last:

1. front `HUNTING`/intensity transition;
2. rear `HUNTED` transition;
3. derived `BATTLE_FOR_POSITION` ENTER/UPDATE/EXIT.

If both activate on one tick, all three may be accepted with consecutive
sequences. Parent coalesce keys remain independent; the composite UPDATE key
contains both target identities/epochs. A target swap on either side closes the
old parent/composite correlation before opening the new identities.

For speech, only one utterance can play at a time. When a fresh composite and
its parent ENTERs occur in the same batch, CommentaryDirector should prefer the
explicit `two_front_battle` node and record the parent speech decisions as
`covered_by_two_front`; it must not mark the parent events rejected or delete
their active/cooldown state. Later parent UPDATE/EXIT beats remain eligible.
If the composite cannot bind names/gaps, it still has slot-light copy such as
“he is attacking ahead while defending behind.” If latest context shows only
one surviving relation, veto the composite and reselect that parent branch.

Do not map `BATTLE_FOR_POSITION` to the existing `side_by_side` copy in V2:
side-by-side is one front-target intensity, while two-front battle is distinct
geometry with an attacker ahead and a threat behind. The proposed node, slots,
edges, and bilingual copy are specified in
[`commentary_extension_handover.md`](../commentary_extension_handover.md#two-front-battle-branch-needs-engineering).

### A3 — ContextSnapshot schema and delivery

`ContextSnapshot` is versioned and frozen/encoded with the same canonical JSON
rules as envelopes. Schema `n12-context/1` contains:

| Section | Required fields |
| --- | --- |
| identity | `schema_version`, `version`, `session_id`, `captured_monotonic_ms`, `overlay_mode`, `session_type`, `session_num`, `subsession_id`, `track_id` |
| race | `connected`, `player_car_idx`, `lap`, `lap_completed`, `position`, `class_position`, `gap_ahead_s`, `gap_behind_s`, `on_pit_road`, `session_checkered`, `player_finished`, `mute_field`, `incident_count`, `speed_mps` |
| bio | `status`, `bpm`, `hr_state`, `sample_monotonic_ms` |
| story | hero display/speakable names, 2+2 near-field ids/names/gaps, leader name/position, localized weather bindings, quali bag, stream session keys, driver profiles keyed by `CarIdx`, immutable start-grid facts |
| situation | current/completed lap, fixed total laps when known, normalized laps/time remaining, deterministic race phase, progress source/ratio, final-lap/checkered/finished flags |
| config identity | immutable config generation plus `language`, `commentary_enabled`, scheduler flags required for the decision |

Missing optional telemetry stays `null`; no consumer reaches back to live
objects to fill it. Slot values already carried by an accepted envelope remain
authoritative for that event.

#### A3.1 — Driver facts for commentary context

RaceObserver owns one session-scoped driver fact ledger. It joins the current
`DriverInfo.Drivers[]` roster to the hero and near-field cars by `CarIdx`; the
commentary consumer never reparses SessionInfo and never calls the reader. The
ledger is part of the frozen A3 context, not extra mutable fields patched into
an accepted envelope after fan-out.

```python
@dataclass(frozen=True)
class DriverProfileSnapshot:
    car_idx: int
    user_id: int | None
    display_name: str | None
    i_rating: int | None
    safety_rating: str | None
    car_name: str | None
    nationality: str | None
    start_position: int | None
    start_position_scope: Literal["class", "overall"] | None
```

| Fact | Exact source and update rule |
| --- | --- |
| iRating | `DriverInfo.Drivers[].IRating`; accept a finite non-negative integer, retain the last valid value for the current roster identity, format as a localized label before TTS so no four-digit run reaches the validator. |
| Safety Rating | `DriverInfo.Drivers[].LicString`; keep the normalized licence class plus rating (for example `A 3.42`). `LicLevel` / `LicSubLevel` may validate a fixture but must not be used to invent a different displayed value. |
| car | `DriverInfo.Drivers[].CarScreenName`, falling back to `CarScreenNameShort`; never speak `CarPath` or numeric `CarID`. |
| nationality | No reliable nationality/country field is evidenced in the current in-session iRSDK schema. Keep `null` until an approved, tested source exists. Do not infer nationality from `ClubName`, a name, language, or flag graphics; an external iRacing API/cache would be a separately approved dependency and privacy decision. |
| start position | Capture `CarIdxClassPosition[]` for multiclass narration, otherwise `CarIdxPosition[]`, at the first valid pre-green/formation sample. If unavailable, capture the first valid green sample and mark that fallback in diagnostics. Freeze once per car; a late join remains `null`. `QualifyResultsInfo` is qualifying result context, not an authoritative race start position. |

The roster is reparsed only when the SessionInfo revision/content digest changes.
Valid values replace the same `CarIdx` profile; a changed `UserID` on the same
car index is a driver swap and replaces the profile rather than inheriting the
previous driver's facts. Disconnect or `SessionReset` clears the session ledger
and start-grid capture. StreamMemory may retain only already-spoken narrative
facts required by anti-repeat; it must not become an unbounded driver database.

At dequeue, CommentaryConsumer resolves `hero_*` from the player `CarIdx` and
`target_*` from the accepted envelope target/correlation plus the exact embedded
context. A missing or mismatched target identity leaves target facts unbound;
it never falls back to some other nearby car.

Authored use is deliberately sparse:

- normally no more than one profile fact in one utterance;
- target facts are allowed only for a stable, named/correlated opponent;
- iRating/Safety Rating provide factual context, never a claim about talent,
  clean driving, expected result, or blame;
- nationality, when a trustworthy source exists, is descriptive only and never
  drives stereotypes or competitive claims;
- car facts fit intros, strategy/pit context, and selected battle beats;
- start position fits progress, finish, and session-wrap beats;
- at least 70% of each affected cell stays profile-slot-free, and a per-driver,
  per-fact cooldown prevents the same biography from being repeated.

Initial proposed slots and bilingual examples live in
[`commentary_extension_handover.md`](../commentary_extension_handover.md#driver-fact-extension-needs-engineering).

#### A3.2 — Observer-to-commentary data flow and freshness gate

The producer tick has one mandatory order. There is no eventual side lookup
from CommentaryConsumer:

```text
one iRacing read (telemetry + current SessionInfo revision/content)
  -> RaceObserver refreshes DriverFactLedger and near field
  -> producer freezes ContextSnapshot version N
  -> EventEngine + RaceObserver produce candidates against version N
  -> one arbitration/stamp/freeze step
  -> AcceptedEventBatch(context_version=N, context_payload=N, events=...)
  -> commentary FIFO
  -> thaw event + its embedded context N
  -> freshness/identity gate against replace-only latest_context
  -> resolve hero/target slots -> choose one fully bound line -> validate -> TTS
```

Every driver profile carries `session_id`, `user_id`, `car_idx`,
`identity_epoch`, `roster_revision`, and `observed_monotonic_ms`. The context
also records `captured_monotonic_ms`. A producer may reuse static profile values
between unchanged SessionInfo revisions, but every batch embeds a newly captured
context whose dynamic race facts came from the same producer tick. At acceptance:

```text
0 <= accepted_monotonic_ms - context.captured_monotonic_ms <= poll_interval_ms
```

If that invariant cannot be met, the producer records `context_stale_at_accept`
and omits dynamic/profile bindings from that batch rather than publishing a
plausible-looking stale value.

Commentary uses the embedded context as the factual event-time source. The
replace-only `latest_context` has one narrower purpose before final line
selection: it may **veto** an old binding, never replace it. The gate requires:

1. batch, embedded context, and latest context have the same `session_id`;
2. hero/target `(CarIdx, UserID, identity_epoch)` still match when a profile
   slot is requested;
3. the accepted target identity matches the profile selected from context;
4. current-relation copy (gap, live position, hunting/hunted state) is no more
   than 3 seconds old at speech time and remains inside the event TTL;
5. static iRating/SR/car facts remain usable for the session only while the
   identity match holds; captured start position is immutable for that identity.

An ordered `SessionReset` flushes old-session deferred speech before the first
new-session event is eligible. A driver swap increments `identity_epoch`, so a
queued line about the previous user is vetoed even if `CarIdx` was reused. A
late target mismatch, stale relation, missing fact, or unavailable nationality
removes those bindings and reruns selection from the same node with the reduced
binding set. If no fully bound profile-free variant remains, skip and record
`driver_context_stale`, `driver_identity_changed`, or `driver_fact_unavailable`.
Never substitute the current nearest opponent or read live RaceObserver state.

This makes the distinction explicit: event-time facts come from the exact
accepted snapshot; the newest snapshot protects against stale identity and
relation claims without rewriting history.

#### A3.3 — Situational race context for copy and LLM

The viewer must be able to recover where the race is from commentary alone.
RaceObserver therefore derives a small immutable `SituationSnapshot`; it does
not send raw telemetry or the complete SessionInfo document to the LLM.

```python
@dataclass(frozen=True)
class SituationSnapshot:
    session_type: str | None
    current_lap: int | None
    lap_completed: int | None
    total_laps: int | None
    laps_remaining: float | None
    session_time_elapsed_s: float | None
    session_time_total_s: float | None
    session_time_remaining_s: float | None
    progress_ratio: float | None
    progress_source: Literal["laps", "time"] | None
    race_phase: Literal[
        "pre_start", "opening", "middle", "closing",
        "final_lap", "checkered", "finished", "unknown"
    ]
    captured_monotonic_ms: int
```

| Situation fact | Exact source / rule |
| --- | --- |
| current/completed lap | Live `Lap` and `LapCompleted`, normalized to non-negative integers. `current_lap` is spoken only when greater than zero. |
| total laps | Active `SessionInfo.Sessions[SessionNum].SessionLaps` when it is a fixed positive count. `unlimited` and malformed values remain `null`. |
| laps remaining | Live `SessionLapsRemain` through the existing sentinel-aware normalizer. Raw fractional values stay numeric context; a spoken integer/label is produced only by the locale formatter. |
| elapsed/remaining time | Live `SessionTime` plus proposed extraction of `SessionTimeRemain`; total duration comes from active-session `SessionTime` only when fixed. Unlimited sentinels remain `null`. |
| progress | Prefer `lap_completed / total_laps` for fixed-lap races. Otherwise use elapsed/total or `1 - remaining/total` for fixed-time races. Clamp to `[0, 1]`; missing denominator yields `null`, never a guessed phase. |

Race phase is deterministic upstream, never an LLM inference. Override order is
`finished` -> `checkered` -> `final_lap` -> progress phase. `final_lap` requires
the existing normalized `RaceState.is_final_lap`; a percentage alone must not
create it. For a running Race with valid progress, the initial policy is:

- `opening`: progress below 20%;
- `middle`: 20% through below 70%;
- `closing`: 70% or later;
- `unknown`: non-Race session or insufficient trustworthy progress.

Thresholds are one named policy with replay tests and may be tuned later; the
LLM and authored text do not recalculate them. Practice and qualifying may
receive current lap/time facts but never Race `opening/middle/closing` labels.

##### Commentary cadence and graph slots

The graph extension proposes `current_lap`, `lap_context`, `race_phase`, and
`remaining_context` bindings. `lap_context` and `remaining_context` are
locale-formatted labels such as `lap 12 of 30` / `12. kolo z 30` and
`5 laps remaining` / `zbývá 5 kol`; Czech plural forms are created before slot
binding, not by an English template.

During an active Race, RaceObserver tracks `last_situation_spoken_at`,
`last_spoken_lap`, and `last_spoken_phase`. It may request a low-priority
`FIELD_FACT` with `fact="lap_context"` when:

- `race_phase` changes; or
- no spoken utterance has carried current lap/phase for 120 seconds.

The request uses the A5 producer path and the next accepted batch's current
snapshot. It is suppressed behind battle, incident, final-lap, pit, finish, and
session control speech. The lap/phase fact has its own 90-second cooldown, is
not forced during continuous high-priority action, and is never emitted merely
because every telemetry tick changed `Lap`.

Any utterance containing `current_lap`, `lap_context`, `race_phase`, or
`remaining_context` has a 3-second situation-age ceiling at final line
selection. If delayed beyond it, if the lap/phase no longer matches
`latest_context`, or if a reset arrived, reselect a situation-free line or skip
with `situation_context_stale`. Do not rewrite an old battle using the new lap.
A fresh situation filler may be requested on a later producer tick.

##### Bounded LLM prompt contract

When `llm_polish` / past framing is enabled, the request contains only:

```text
SKELETON: fully bound authored line
EVENT FACTS: event type, phase, occurred time, hero/target facts used by skeleton
SITUATION FACTS: session type, current/completed/total lap, remaining context,
                 deterministic race phase, final/checkered/finished booleans
ALLOWED SITUATION ADDITIONS: zero or one exact localized phrase, or NONE
INSTRUCTION: preserve every fact; enrich wording only; do not infer missing data
```

The situation block is built from the same embedded context that produced the
skeleton and passes the A3.2 freshness gate before the request. It contains no
raw roster, `UserID`, full telemetry array, or reader handle. A deferred event
keeps its event-time situation and receives past framing; it is not upgraded to
the newest lap.

The producer/director, not the model, builds `ALLOWED SITUATION ADDITIONS`, for
example `lap 12`, `lap 12 of 30`, or `middle phase`. When the 90-second
situation cooldown allows enrichment, an eligible live or past-framed rewrite
may add **zero or one** phrase verbatim/semantically unchanged. Otherwise the
field is `NONE` and adding lap/phase copy is a validation error. High-priority
incident, final-lap, finish, and control skeletons do not receive optional
additions unless that situation is already part of their authored facts.

Post-validation rejects and falls back to the skeleton when the LLM:

- introduces a lap/remaining number absent from the approved skeleton/context
  (`invented_situation_number`);
- adds more than one situation fact or adds one while the allowlist is `NONE`
  (`unapproved_situation_addition`);
- changes `opening/middle/closing/final/checkered/finished` semantics
  (`situation_phase_conflict`);
- claims a final lap without `is_final_lap`, or reports live/current framing for
  a stale/deferred snapshot (`stale_situation_framing`).

If situation data is missing, omit the block fields and prohibit the LLM from
mentioning lap count or race phase. Timeout, invalid rewrite, or fact conflict
uses the already validated skeleton; the LLM is never required for factual lap
awareness. Proposed slots, bilingual lines, and engineering work are in
[`commentary_extension_handover.md`](../commentary_extension_handover.md#situation-and-llm-context-needs-engineering).

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
| front battle (`HUNTING`, `APPROACH`, `ATTACK_RANGE`, `SIDE_BY_SIDE`) | `(session_id, "front", hero_car_idx, target_car_idx, relation_epoch, intensity)` | replace older ACTIVE/UPDATE for the same front relation/intensity only; never evict rear |
| rear battle (`HUNTED`) | `(session_id, "rear", hero_car_idx, target_car_idx, relation_epoch)` | replace older ACTIVE/UPDATE for the same rear relation only; never evict front |
| two-front composite (`BATTLE_FOR_POSITION`) | `(session_id, "two_front", hero_car_idx, front_target_car_idx, front_epoch, rear_target_car_idx, rear_epoch)` | replace only an older composite UPDATE for the identical pair; parent events remain |
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
- Characterize simultaneous hunting+hunted behavior and the current incomplete
  front-only `BATTLE_FOR_POSITION` payload before replacing its contract.

### N12.1 — Extract producer

- Move telemetry/race tick, EventEngine, EventManagerV2, one RaceObserver, and
  accepted-batch creation out of `OverlayRuntime` into a peer runtime.
- Merge RaceObserver-derived candidates into shared arbitration.
- Implement A1–A5 contracts: freeze API, fixed derived merge, embedded context,
  typed reset/config control plane, and filler request/result path.
- Add the A3.1 session-scoped driver fact ledger and immutable start-grid
  capture; do not add an external nationality lookup in this slice.
- Add the A3.3 situation snapshot, deterministic phase policy, current-lap
  filler request, and bounded LLM fact block; no raw telemetry enters prompts.
- Implement A2.1 independent front/rear relation keys plus the non-replacing
  two-front composite payload and graph branch.
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
- [ ] Simultaneous `HUNTING` and `HUNTED` remain independently ACTIVE and
  accepted; neither direction can evict, dedupe, coalesce, or reset the other.
- [ ] `BATTLE_FOR_POSITION` contains both target identities/gaps, is a third
  derived event, and exits to the surviving parent branch without re-entering
  or deleting it.
- [ ] Commentary has fresh, slot-light `two_front_battle` copy and records
  same-batch parent speech as `covered_by_two_front`, not rejected/dropped.
- [ ] Silence filler uses the A5 request/result path with no callback/shared
  RaceObserver object.
- [ ] Session reset and config reload reach both consumers once in sequence.
- [ ] No empty event batch enters a FIFO; context-only updates use the bounded
  replace-only latest slot at no more than race sampling frequency.
- [ ] Hero and target profile facts resolve by `CarIdx` from the embedded
  context, update on a roster revision/driver swap, and never leak stale facts
  across a session reset.
- [ ] Missing nationality remains unbound, start position is captured once with
  an explicit class/overall scope, and profile-slot-free copy remains usable.
- [ ] Each accepted batch carries the same-tick context used for candidate
  creation; commentary never reads RaceObserver and latest context can only veto,
  not replace, an embedded event-time fact.
- [ ] A session reset, reused `CarIdx`/driver swap, target mismatch, relation
  older than 3 seconds, or expired event cannot produce a stale named/profile
  utterance; the decision has an explicit reason code.
- [ ] The same embedded situation snapshot drives authored slots and LLM facts;
  current lap/phase copy is at most 3 seconds old and never mixes an old event
  with the newest lap.
- [ ] In an active Race, a phase transition or 120 seconds without a spoken
  lap/phase creates an eligible low-priority current-situation fact without
  interrupting higher-priority action.
- [ ] LLM output cannot invent or change lap, remaining-distance, phase,
  final-lap, checkered, or finished facts; invalid output falls back to the
  fully bound skeleton.
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
- Two-front battle fixture: front enters, rear enters, both update at different
  rates, front target changes, rear exits, pit/reset aborts. Assert independent
  parent ids/epochs, parent-parent-composite order, composite payload identities,
  no cross-direction coalescing, and continuity of the surviving branch.
- Two-front speech fixture: full names/gaps, missing front data, missing rear
  data, both names missing, stale composite, and same-batch parent ENTERs. Assert
  composite/parent fallback and explicit `covered_by_two_front` accounting.
- Filler fixture: request available/no-fact/stale paths with no live observer
  reference in CommentaryConsumer.
- Driver facts: malformed/missing roster fields, localized iRating/SR labels,
  car-name fallback, driver swap on reused `CarIdx`, multiclass start-grid
  capture, late join, reset, target mismatch, and unavailable nationality.
- Freshness fixture: delayed batch with unchanged static profile, delayed battle
  beyond 3 seconds, SessionReset overtaking queued work, changed `UserID` on the
  same `CarIdx`, latest-context target mismatch, and stale-at-accept producer
  input. Assert fallback/skip reason and zero wrong-name/profile speech.
- Situation fixtures: lap-limited, timed, unlimited, missing totals, phase
  boundaries at 20%/70%, explicit final/checkered/finished overrides, lap/phase
  cadence, 3-second stale veto, and high-priority suppression.
- LLM fact-lock fixtures: approved current/past situation, invented lap number,
  changed race phase, false final lap, missing situation, timeout, and fallback
  skeleton parity. Tape/replay records the exact bounded situation fact block.
- Content contract: every affected EN/CS cell keeps at least 70% profile-free
  lines; bound profile examples pass the current validator and do not combine
  unrelated biography facts.
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
