# v2.0.0 branch-only vertical-slice decision fixtures

**Status:** design-freeze candidate owned by issues #235 and #278

These fixtures choose expected decisions before runtime implementation. Times are monotonic milliseconds within one process. Unless overridden: selection threshold 35, switch margin 8, global interval already satisfied, no fatigue/channel pressure, current facts have confidence 1, Qwen is warm, TTS is available and catalog/config hashes are fixed.

## F01 — stream starts before iRacing session

Input: `STREAM_STARTED(epoch=1,startReason=attached_live)` with no SessionRef.

Expected:

- create stream-scope fact/episode/opportunity; occurrence and lineage remain null;
- select authored `stream.started`, policy critical, base score 90;
- no session intro is invented;
- playback acceptance consumes the opportunity and starts the silence clock only after terminal speech.

## F02 — canonical stage progression with inheritance

Input sequence: Practice occurrence P0 produces a best-lap downstream fact; P0 ends; Qualifying Q0 starts/ends with class-position fact; Race R0 starts.

Expected:

- lineage at R0 is `P0>Q0>R0`;
- current facts are R0 only; P0/Q0 are speakable only through explicitly selected historical/recap claims;
- `session.intro.race` can mention a Q0 result only when that optional past-marked claim is selected;
- no absent stage is inserted.

## F03 — rewind Race to Qualifying

Input: active lineage P0>Q0>R0, then a coherent different/older qualifying SessionRef Q1.

Expected:

- ordered R0 end/supersede then Q1 start; no `SESSION_REWOUND` command;
- new lineage P0>Q1; Q0/R0 remain historical/superseded and cannot supply current claims;
- P0 downstream facts remain eligible; building/committed R0 speech is cancelled;
- subsequent Race R1 lineage becomes P0>Q1>R1.

## F04 — same-session confirmed restart

Input: same SessionRef, SessionTime drops more than 5 seconds and remains coherent for at least 100 ms.

Expected:

- one `SESSION_RESTARTED`, new occurrence revision and `session.restart` opportunity;
- prior occurrence facts archive by scope, exposures/history remain;
- pending/reserved old-occurrence opportunities become `invalidated_occurrence`;
- a single rewind sample that is not confirmed creates no restart.

## F05 — first pursuit and controlled score

Input: valid `battle.pursuit` opportunity with policy live_story and material band `material`.

Expected score: `64 base + 6 material = 70`. It passes threshold and opens the correlated episode. No V4 wire priority/severity term appears in the breakdown.

## F06 — related continuation beats unrelated context

Prior accepted beat: `battle.pursuit`. Candidates:

- related `battle.approach`, deduplicated from event+preferred successor, effective score `58 continuation base + 6 continuity + 6 preferred edge + 6 material = 76`;
- independent `session.weather_change`, context urgency and effective score 52.

Expected: select `battle.approach` as `related_event_update`. The lower-urgency weather opportunity remains pending only to its TTL.

## F07 — equal-urgency story switch uses margin

Focused successor score is 76. Independent story candidate A scores 82; candidate B later scores 84.

Expected:

- A is not admitted because `82 < 76 + 8` and remains pending;
- B is admitted exactly at the inclusive margin and wins if no higher-urgency candidate exists;
- tape records `switch_margin_met`, both breakdowns and the focused relation.

## F08 — event during speech, no prepared queue

While `battle.approach` is speaking, a correlated `position.pass` critical opportunity arrives and its result facts resolve the episode.

Expected:

- current playback is not interrupted; no text/prompt/BeatPlan for pass exists yet;
- opportunity/episode meaning updates immediately;
- on speech terminal, still-live pass scores from current outcome facts and wins by higher urgency;
- if its 45-second TTL had expired, no late pass utterance is generated merely from old history.

## F09 — invalid Qwen output chooses a different beat

Qwen output for `battle.pursuit` reverses actors. Verifier returns `actor_reversed`. A separate valid context beat scores 46.

Expected:

- suppress `(battle.pursuit, revision)`; release its opportunity reservation; no repair/retry/authored fallback/exposure;
- in the same `planningCycleId`, dispatch the distinct context beat as `cycleAttemptOrdinal=2` if all hard/source guards pass;
- if that alternative also fails, record `planning_cycle_exhausted`; without a distinct candidate, choose SILENCE and wait for a material accepted revision, new accepted/lifecycle event or silence impulse.

## F10 — long silence filler threshold

At exactly `long_silence_s`, `LONG_SILENCE_ELAPSED` finds a valid out-lap fact and no higher candidate.

Expected score: `24 base + 12 silence pressure = 36`; select `filler.out_lap`. If required fact is missing, record SILENCE/source guard and rearm exactly `now + long_silence_s`, not a short retry.

## F11 — Qwen cold/unavailable

Warm-up fails. One Qwen-backed beat and one authored eligible beat exist.

Expected:

- Qwen component is unavailable; Qwen-backed candidate is hard-ineligible without spending per-beat cold timeout;
- the distinct authored beat may win normally;
- backend mode of the Qwen beat is never changed to authored as fallback.

## F12 — manual speech while automatic commentary disabled

Input: valid localhost/CSRF/versioned manual request, idle lane, TTS available, `commentary.enabled=false`.

Expected: API returns 202 after lane admission. No event, fact, BeatPlan, opportunity, exposure, fatigue or successor is created. A second manual/live request receives busy; race events update truth but do not interrupt the test.

## F13 — protected mailbox overflow

Fill 56 ordinary and 7 protected reservations, then admit another protected reset while the actor is stalled.

Expected:

- ordinary eviction is attempted first; if no ordinary item remains, emergency `MAILBOX_RECOVERY` captures the latest coherent projections, loss range, worker snapshot and reset safety effect;
- actor cancels uncommitted work, sets history incomplete and creates no opportunities for lost results;
- producer does not block or raise into the race loop.

## F14 — playback acknowledgement races reset

TTS is dispatched for old occurrence. Test both recorded orders:

1. reset reducer sequence precedes `PLAYBACK_ACCEPTED`: cancellation keeps opportunity unconsumed; stale acceptance token is audited/ignored;
2. `PLAYBACK_ACCEPTED` precedes reset: opportunity is consumed/exposed, then reset requests interruption and terminal reason is `interrupted_occurrence_reset`.

Replay must reproduce each outcome from reducer sequence; equal OS timestamps do not collapse the cases.

## F15 — fact-only invalidation is not a speech trigger

Input: a `battle_ahead` episode is focused and an ordinary coherent context batch contains no NarrativeEvent, but its newer FactView expires `battle.closing(hero→target)`.

Expected:

- atomically apply the FactView, close/invalidate the episode and cancel a building or committed plan whose claim is now false;
- create no episode, opportunity or material speakable revision and run no director pass from this batch alone;
- the next accepted/lifecycle/silence event or speech terminal pass sees the episode already closed and cannot continue it.

## F16 — disable and re-enable within one OBS broadcast

Input: automatic commentary run `streamEpoch=3` is active under `broadcastEpoch=2`; commentary is disabled and later re-enabled while OBS remains confirmed active.

Expected:

- disable closes all run-3 episodes/opportunities with `commentary_disabled`, cancels narrative speech according to the lane table, writes a complete run-3 tape trailer and leaves `broadcastEpoch=2` unchanged;
- manual speech remains independent while disabled and creates no narrative state;
- re-enable allocates `streamEpoch=4`, creates a new occurrence projection for the still-current SessionRef with `historyComplete=false`, opens a new tape manifest and emits exactly one `STREAM_STARTED(startReason=enabled_mid_stream)`;
- no run-3 opportunity, exposure, attempt suppression, episode or historical claim becomes live in run 4; stale run-3 worker tokens are ignored.

## F17 — pre-session lobby filler uses stream facts only

Input: active narrative run and normalized `broadcast.context(lobby)`, but no coherent SessionRef/occurrence. After `long_silence_s`, a fresh stream-scope `context.track_identity` exists.

Expected:

- route `filler.lobby` to a stream-scope `filler_single` episode/opportunity with null occurrence/lineage and bind exactly lobby context plus track identity;
- no stage, current session progress, weather, gap or on-track action may be claimed;
- without track identity, the same silence impulse records `source_guard_failed`, creates no BeatPlan and rearms the normal silence deadline.

## Required tape assertions per fixture

Each implementation fixture asserts the ordered subset that applies:

```text
context_applied → narrative_event → fact/episode/opportunity change
→ director_decision(score breakdown/reason)
→ llm_attempt? → PLAYBACK_ACCEPTED? → speech_exposure terminal
```

Every row carries catalog/config/policy hashes, source refs and the expected `tapeChannel`. Rejected candidates include hard/source gate or arbitration reason. Tests compare structured records, not prose logs.
