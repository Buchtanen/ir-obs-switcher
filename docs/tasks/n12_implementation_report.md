# N12 implementation report

**Issue:** [#200](https://github.com/Buchtanen/ir-obs-switcher/issues/200)  
**Integration branch:** `refactor/200-n12-async-consumers`  
**Scope:** N12.0–N12.4 (V2a) plus owner-approved #195 deterministic composer; optional N12.5 subprocess transport remains excluded.

## Delivered architecture

`RaceRuntime` is the composition root. Its `RacePipeline` is the only producer
of immutable accepted batches and owns the session sequence allocator. One
`AsyncEventFanout` broadcasts each frozen item to separate bounded overlay and
commentary subscriptions before either consumer performs work.

```text
one telemetry read + one RaceObserver
            │
       RacePipeline
  stamp → canonical freeze
            │
     AsyncEventFanout
       ┌────┴────┐
       │         │
OverlayConsumer CommentaryConsumer
owned task       owned task + TTS
```

The old `OverlayRuntime` module is only a compatibility import for
`RaceRuntime`; it no longer contains race, commentary, or TTS composition.
There is no synchronous `CommentaryEventConsumer`, direct commentary observe
callback, speech dispatch callback, or live RaceObserver filler closure.

## Bound contracts

- Canonical UTF-8 JSON freeze/thaw validates event identity and rejects NaN or
  non-JSON values before fan-out. Both consumers receive the same immutable
  bytes and thaw private objects.
- Non-empty batches embed the exact same-tick `n12-context/1` snapshot. Context
  updates use a replace-only latest slot; reset and config changes are ordered
  typed controls.
- Engine, narrative, aftermath, flags, timing hunt, grid story, filler, stream
  start, in-car, and session-brief facts enter the producer stream. Audience
  metadata lets overlay discard commentary-only facts after dequeue.
- Silence filler is a bounded request/result mailbox. Commentary has no live
  `RaceObserver` reference.
- The session-scoped driver ledger tracks roster digest, `UserID`, identity
  epoch, static facts and immutable class/overall start position. Driver swaps,
  disconnects, late joins, and session resets cannot inherit stale facts;
  nationality deliberately stays null.
- Situation context uses deterministic 20%/70% race phases with explicit
  final/checkered/finished overrides. A low-priority fact becomes eligible on a
  phase transition or after 120 seconds and yields to higher-priority action.
- Front and rear battle FSMs retain independent relation identities and epochs.
  `BATTLE_FOR_POSITION` is a third fact containing both targets, gaps and
  epochs. Parent facts precede the composite, and commentary records parent
  ENTER speech as `covered_by_two_front` while selecting the dedicated
  bilingual `two_front_battle` node.
- Only proven ACTIVE/UPDATE keys coalesce. Protected overflow is accounted,
  marks the subscription degraded, preserves the incoming event, and requests
  a bounded-backoff restart around the same consumer instance.
- Event-id ledgers suppress duplicate HUD publication and speech across a V2a
  worker restart. `SessionReset` clears the previous-session ledger only when
  consumed in order.
- Config reload is applied from frozen `ConfigUpdate` data; the commentary
  worker does not read mutable runtime settings after construction.
- Shutdown cancels and awaits owned tasks with a two-second bound, interrupts
  queued speech, closes the TTS worker and tape, and closes optional capture.

## Replay and operations

`N12ReplayWriter` writes canonical JSONL schema `n12-replay/1`: header,
context-before-reference, control, events, and optional expected rows.
`load_n12_replay(...).replay(fanout)` rebases the relative monotonic timeline
and feeds the same subscription interface without iRSDK, OBS, bio, or config
access. Optional production capture is available through
`RaceRuntime.start_event_capture(...)`; no new default or INI key was added.

Runtime status includes stream sequence, per-consumer capacity/depth,
enqueue/dequeue/coalesce/eviction/recovery counters, real queue lag,
sequence lag, degraded state, restart requests, consumer failure/duplicate
counters, supervisor restarts, and capture state. Overflow logs include
consumer, policy, event id, sequence, depth, and discarded count.

## Composer and story history

`RaceObserver` now owns a session-scoped 24-beat factual ring. It records accepted event identity, phase, correlation, target roles and a curated set of numeric facts. The next frozen `n12-context/1` snapshot carries that history to `CommentaryConsumer`; no live observer reference crosses the queue boundary.

When `commentary.llm_polish=true`, `commentary/composer.py` walks backwards over the existing sequence-graph edges (maximum three graph nodes) and assembles `history → beat → detail → context/session`. A valid result contains two to four distinct bound facts, fits the selected node's TTS limits and produces compact `commentary-facts/1`. The TTS worker sends that skeleton and fact block to the style-only model. EN and CS have dedicated prompts; two-front FRONT/REAR swaps are rejected. `llm_polish=false` still uses the original authored `choose_filled_line` path.

Graph/runtime compatibility is executable: all 53 active nodes compose and validate in EN+CS, all 37 declared slot names exist in runtime bindings, and all 22 edges can supply a history clause. The audit found one real mismatch: `two_front_battle` declared `UPDATE`, while the director rejected every UPDATE. `BATTLE_FOR_POSITION` UPDATE is now the sole allowed update-speak event and remains limited by the node's 12-second cooldown.

## Automated evidence

Evidence captured on 2026-09-01 from the integration branch:

- `pytest -q`: **1162 passed**.
- `ruff check src tests`: passed.
- `black --check src tests`: passed.
- `mypy` over all N12-touched production modules: passed.
- Full-queue benchmark, 500 batches and two non-draining subscriptions:
  **p95 0.1197 ms**, **max 0.3167 ms**. Contract limits are p95 below the
  default 200 ms poll interval and every publication below 50 ms.
- Replay fixture proves canonical rows and identical ordered ids at both
  subscriptions. Failure fixtures cover per-item exceptions, protected
  overflow recovery, same-instance supervisor restart, duplicate suppression,
  cancellation, frozen config reload, and sibling continuity.

The repository-wide mypy run still reports the pre-existing non-Windows
`subprocess.CREATE_*` / `STARTUPINFO` attribute findings in
`util/process_restart.py`; no N12 module has a type error.

## Integration validation

This branch is intentionally the integration target. Automated fakes prove
that slow overlay work cannot delay commentary and vice versa. The remaining
environment validation is the normal Windows stream-PC pass: real iRSDK,
deliberately slow OBS WebSocket clients, SAPI routed to the virtual audio
device, duck restore, service cancellation, and replay comparison against a
captured live session. These checks require external hardware/services and do
not change the delivered N12 code contract.
