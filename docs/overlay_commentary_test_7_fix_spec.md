# Overlay and commentary Test 7 fix specification

Issue: [#215](https://github.com/Buchtanen/ir-obs-switcher/issues/215)

## Scope

This change fixes the lifecycle and editorial failures confirmed by comparing the
Test 7 stream video with the event tape, overlay snapshots, LLM records and TTS
lifecycle records. It does not redesign overlay visuals, change the event schema,
or add a speech/model dependency.

## Required behaviour

### Overlay lifecycle

- An authoritative state snapshot may adopt an already-rendered live event with
  the same correlation and sequence. Equal sequence is not a stale snapshot.
- A card adopted by the snapshot is removed when it is absent from a later
  snapshot, including terminal mini-story and session reset snapshots.
- A terminal mini-story cannot retain an immortal `storyLease`; a later ordinary
  event can use its configured hold timer normally.
- When an EXIT is represented by a resolved leased RESULT, that RESULT carries
  the fresh identity, sequence and timestamps of the EXIT event.
- Overlay JS cache versions remain in lockstep.

### Commentary fallback and selection

- With LLM polish enabled, `fallback_timeout`, `fallback_error` and
  `retry_exhausted` are never sent to TTS as the authored skeleton.
- A rejected polish releases its mini-story and TTS slot. The existing one-item
  deferred/worker queue then selects the current highest-priority valid waiter;
  equal-priority arrivals replace older ones so a newer continuation wins.
- If no valid waiter exists, commentary waits for a new story. It does not invent
  or speak a generic line.
- LLM-disabled mode remains deterministic and may speak authored copy directly.
- Rejected lines are observable with a stable `llm_polish_rejected` reason.

### Editorial priority invariant

Candidates are grouped into strict editorial tiers before graph scoring. Graph
quality and freshness decide only within the highest available tier:

1. race finish;
2. race start, then flags ordered red, checkered, yellow/caution, green/restart;
3. incident;
4. overtake, overtaken and position change;
5. battle, hunted/hunting and rival pressure;
6. sector timing;
7. pit, weather, lap/session context and remaining filler.

A pending FINISH therefore cannot lose to fatigue, transition bonuses or a lower
tier. Queue replacement uses the same tier value.

### Correctness fixes

- Resolving FINISH preserves `session_result` facts and canonical finish meaning;
  it cannot turn into an “attacking window closed” line.
- Repeated changes in the same direction (`POSITION_LOST` after
  `POSITION_LOST`, or gained after gained) do not interrupt the line in flight.
  The newest equal-priority position result replaces an older waiter.
- A position event without a rival name still speaks the current position when
  that fact exists.

## Acceptance criteria

Automated regression coverage must prove:

- equal-sequence snapshot adoption plus removal by an empty terminal snapshot;
- fresh EXIT metadata on resolved overlay leases and lockstep asset versions;
- every failed LLM outcome is silent while the next highest waiter proceeds;
- strict editorial tiers, FINISH dominance and flag ordering;
- same-direction position changes do not self-interrupt and latest replaces old;
- resolved FINISH retains its fact pack and position-only loss is specific.

The relevant focused test suites, formatting checks and type checks must pass.

## Documentation and configuration impact

`COMMENTARY_ENGINE.md` documents selection/fallback semantics. Overlay protocol
payloads and public configuration keys are unchanged, so `API.md`, `.env.example`
and runtime configuration need no contract change. Overlay asset version is bumped
because browser-source JavaScript changes.
