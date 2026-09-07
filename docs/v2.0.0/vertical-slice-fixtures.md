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

Expected: API returns 202 with `admittedState=committed` only after nonblocking dispatch to the effective preflighted TTS generation. No event, fact, BeatPlan, opportunity, exposure, fatigue or successor is created. A second manual request receives busy; race events update truth but do not interrupt the test or create a prepared waiter.

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

## F18 — context batch is a coherent fact/event cut

Input: `APPLY_CONTEXT_BATCH` contains timeline revision 31 and FactView revision 88, but one accepted NarrativeEvent names `factViewRevision=87`; its fact ID exists only in the older view. A later batch contains revision 89 and an event correctly naming 89.

Expected:

- apply the coherent revision-88 timeline/FactView so it may close or invalidate old state, but reject/audit the mismatched event and create no episode/opportunity or planning impulse from it;
- never resolve the event against a cached older view and never merge either context batch with another revision;
- apply revision 89 independently; only its coherent event may open/revise speakable state and trigger one director pass.

## F19 — refreshed recovery barrier jumps over stale queued context

Input: mailbox pressure evicts context revisions 101–104 and creates a recovery barrier at mailbox sequence 20. Before dequeue, later pressure refreshes that same barrier with coherent timeline/FactView revision 110 and expanded loss range. Context commands with revisions 105–109 remain physically behind sequence 20; revision 111 arrives after it.

Expected:

- reducing the barrier cancels uncommitted work, applies revision 110, marks history incomplete and records the full loss range without inventing opportunities for revisions 101–110;
- subsequently dequeued revisions 105–109 and their worker tokens are stale audited no-ops even though their mailbox sequence is later;
- revision 111 applies normally; tape replay over the same reducer sequence and barrier payload produces the same state.

## F20 — manual admission timeout cannot produce delayed audio

Input: a valid manual request enters the mailbox while the actor is stalled. Exercise both one-shot latch orders around the fixed 1,000 ms deadline.

Expected:

1. adapter changes `pending → caller_abandoned` first: return `admission_timeout`/503; later actor dequeue treats the request as stale and does not mutate the lane or call TTS;
2. actor changes `pending → actor_claimed` first: in the same synchronous turn it either dispatches the current preflighted TTS generation, enters `committed` and resolves 202, or keeps idle and resolves 409/503; the timeout callback cannot replace that result;
3. neither order creates a narrative opportunity, exposure, second queue or prepared waiter, and tape contains only the request ID plus terminal admission decision.
4. manual acceptance pauses the audience silence deadline and terminal rearms it, but neither starts a director pass; backend/voice/rate override fields are rejected as unknown.

## F21 — oversized accepted publication is losslessly partitioned

Input: one upstream publication contains 130 accepted events in known external order over one coherent TimelineSnapshot/FactView revision. Events 64 and 129 are `phase=result`; all others are ordinary updates.

Expected:

- adapter emits three nonempty context batches containing 64, 64 and 2 events with consecutive external orders, identical projection revision and no loss/reordering/coalescing;
- the first two batches are protected because each contains a derived protected result; the last is ordinary;
- equal timeline/FactView revisions apply idempotently, while every batch remains an independent planning impulse and event opportunities preserve original source order.

## F22 — stream-run start reasons are exclusive

Exercise four fresh allocations and one resume: a known inactive→active OBS edge; first same-process NarrativeRuntime attachment to an already known active epoch; fresh process startup finding OBS active; re-enable after a closed narrative run while its broadcast remains active; and unknown→active recovery of a run that was never closed.

Expected:

- allocate exactly one run with `normal/broadcast_started/complete`, `attached_live/attached_live/incomplete`, `process_recovery/process_recovery/incomplete`, and `enabled_mid_stream/narrative_enabled/incomplete` respectively;
- the unknown→active resume retains both existing epochs, emits no `STREAM_STARTED`, and uses `broadcast_resumed` only as the timeline transition;
- no allocation carries multiple start reasons or imports history from before an incomplete boundary.

## F23 — scoring decay, order and story cap use one formula

Input: one semantic exposure of weight 1 is exactly 90 seconds old, one pattern exposure is exactly 180 seconds old, and two otherwise equal story candidates have candidate orders `(40,3)` and `(40,4)`. Public consecutive limit is 3, the focused StoryDefinition limit is 2, and two beats of that episode have been playback-accepted consecutively.

Expected:

- semantic and pattern fatigue values are each exactly 0.5 before their named score coefficients; no `exp(-1)` alternative or hidden family/role penalty is applied;
- `(40,3)` wins the stable age tie-break, independent of timestamps or V4 sequence;
- effective consecutive limit is 2, so another non-closing successor is hard-ineligible, while a fact-supported closure/outcome or critical event remains eligible.

## F24 — validity deadline expires a building beat without fallback

Input: an event opportunity and its building BeatPlan both have `expiresMonoMs=50_000`. No race/lifecycle input arrives; the matching validity deadline is reduced at exactly 50,000. Also exercise a full ordinary mailbox where the timer admission is skipped but its already queued head command reduces at 50,001.

Expected:

- the half-open boundary makes both objects invalid at exactly 50,000; cancel the generation token, terminalize the opportunity `expired_ttl`, and ignore a later worker completion;
- run no director pass and do not spend cycle attempt 2—the runtime waits for a later accepted/lifecycle/silence or speech-terminal impulse;
- in the full-mailbox order, record `deadline_admission_skipped`; the next command's mandatory pre-reduction sweep produces the same terminal truth at 50,001 without a recovery barrier or invented opportunity.

## F25 — simultaneous timeline boundaries retain every effect

Input: first observe an enabled normal broadcast start with a coherent Race SessionRef in the same upstream observation. Separately, transition from active Qualifying Q0 to Race R0 in one observation.

Expected:

- the first snapshot carries ordered `transitionReasons=[broadcast_started,session_started]`, allocates the run before the occurrence and emits both matching lifecycle events exactly once;
- the second carries `[session_ended,session_started]`, closes Q0 before opening R0 and builds lineage through Q0;
- duplicate, reversed, over-eight or mutually exclusive transition reason lists fail schema validation rather than silently dropping a boundary.

## F26 — unresponsive TTS cannot strand or overlap the lane

Input: separately stall a TTS token before playback acceptance, after acceptance, and after a cancellation request. Let start/playback/stop watchdogs fire in token order; then deliver stale callbacks and finally a successful preflight for a higher backend generation.

Expected:

- start timeout releases the unconsumed reservation through bounded cancellation; playback watchdog keeps an already consumed opportunity/exposure and requests interruption;
- stop timeout invalidates/quarantines the token, records the corresponding terminal reason, marks TTS unavailable and prevents all automatic/manual speech despite late acceptance/completion callbacks;
- only `COMPONENT_HEALTH_CHANGED(ready)` for a strictly higher backend generation restores admission; no polling retry, second lane or main-loop exception occurs.

## F27 — tape overload has deterministic loss accounting

Input: fill the tape writer queue first with sample+normal records, then with only critical records. Submit a normal record, a critical speech terminal and a required-detector critical window while storage is stalled.

Expected:

- normal/critical arrivals evict oldest lower classes in exact sample-then-normal order; equal classes retain FIFO;
- all-critical overflow never blocks the producer: the bounded loss accumulator records type/priority/reason and first/last time/reducer ranges, later emits `drop_notice`, and the trailer contains the same counters even if no queue slot opened;
- losing the required window posts protected `capture_unavailable` and disables only its experimental detector; world/narrative truth and the main loop continue unchanged.

## F28 — feature ordering and bucket coverage are upstream-owned

Input: deliver relation FeatureFrames with sequences 10, 12, then duplicate/older 12 and 11. In a 1-second bucket provide one valid sample at its start but no following coverage; separately provide regularly spaced samples covering at least 80% of six or more buckets.

Expected:

- detector reduces only frames 10 then 12; duplicate/older frames are audited no-ops and narrative reducer order is never consulted;
- the lone sample contributes at most `sample_interval_s` coverage and cannot make its bucket/window valid;
- the covered window can compute median buckets, OLS slope and net closing only with at least three valid buckets and matching stream/occurrence/lineage/relation identity.

## F29 — offline validation has a self-contained actor lexicon

Input: validate a directional hero→car:22 beat whose text uses “Morgan”. Test a complete binding (`hero→he`, `car:22→Morgan`), a missing target binding, an unused third actor and the same case-folded alias assigned to both actors.

Expected:

- only the complete collision-free binding reaches semantic parsing and can accept the ordered claim;
- missing, unused or colliding bindings return `invalid_request`/400 before parsing, with no live roster/config/fact read and no Qwen call;
- reversing the two valid aliases remains `actor_reversed`, proving that caller-supplied display strings do not weaken direction.

## F30 — TTS auto resolution never retries an utterance

Input: with both SAPI and eSpeak available, admit one `backend=auto` utterance and force its resolved SAPI generation to fail or time out after dispatch. Separately configure explicit SuperTonic.

Expected:

- auto snapshots SAPI and its generation into the utterance; failure follows normal terminal/quarantine behavior and never submits the same text to eSpeak;
- a future explicit config rebuild may choose another backend only for later utterances and uses a higher generation;
- SuperTonic is selected only when explicitly configured, never merely because auto probes find it installed.

## F31 — session plan is explicit, ordered and stable

Input: build coherent SessionInfo plans for each nonempty supported subset P, Q, R, P→Q, P→R, Q→R and P→Q→R. Separately provide no supported stage, duplicate, decreasing-rank and incomplete SubSessionID/supported-row identity, then a temporarily unavailable partial snapshot. Include 18 unsupported rows. Finally freeze P→Q while Q is current, then test adding future R versus removing/retyping P or Q.

Expected:

- all seven subsets produce valid plans in exact increasing `sessionNum`/stage-rank order without inventing a missing stage, and every later TimelineSnapshot carries the matching `sessionPlanRevision` even before a supported session becomes current;
- coherent empty-supported, duplicate, decreasing or incomplete-identity input produces a serializable invalid empty plan with `session_plan_conflict`, no occurrence/lineage allocation and no session-scoped speech; unavailable/partial input publishes no plan and follows connection suspend instead of latching conflict;
- exact repetition keeps the revision; appending previously unseen future R advances it without changing P/Q identity, while insertion, removal, reordering, retyping or identity replacement latches the conflict and suspends new session-scoped state until a new broadcast/run;
- the first 16 unsupported rows remain source-ordered audit metadata, overflow count is 2, and none becomes a supported stage or lineage node.

## F32 — bounded facts and episodes fail unknown, never false

Input: fill active facts to 512 and current episodes to their configured capacity. Admit an updated semantic-key fact, then a new unpinned occurrence fact, then force a pinned-only fact set. Separately fill episodes with evictable suspended/candidate/active instances and finally with only instances owning reserved or in-flight speech.

Expected:

- an updated semantic key supersedes its old revision without growing storage; ordinary overflow evicts the oldest unpinned eligible fact deterministically, records `fact_capacity_evicted`, marks history incomplete and treats the missing claim as unknown;
- newest stream/downstream active-lineage keys are the only upstream-pinned facts; FactLedger never reads BeatPlan/Episode/speech state, and eviction of a BeatPlan-required occurrence fact makes the downstream actor cancel that pre-accept work as unknown;
- upstream-pinned-only overflow publishes no partial FactView, reports `fact_capacity_exhausted` and pauses new planning without blocking producers or the main loop;
- a later complete bounded view resumes planning but remains `fact_capacity_evicted`/history-incomplete for that run; only a fresh lossless run reports facts ready/complete;
- episode pressure evicts in suspended→candidate→lowest-priority-active order with stable ties, terminal reason `capacity_evicted`, opportunity invalidation and retained summary/tape evidence;
- when all episodes are pinned, the accepted event and fact truth remain recorded but no episode/opportunity is created, with `episode_capacity_rejected`; no second speech lane, false fact or silent overwrite appears.

## F33 — prompt freedom is a deterministic safety clamp

Input: enumerate every PromptOptions field combination around tight/balanced/loose. Then request loose globally for: a family promoted only to tight, a critical/outcome beat, incomplete history, confidence 0.89, and a promoted noncritical context family with two enabled audited cards. Exercise repetition pressure and a failed realization.

Expected:

- only the closed profile tuples validate; tight cannot carry optional claims, reorder or two sentences, and a family pool with fewer than two enabled cards is ineligible;
- config, beat maximum, family promotion/preference and runtime safety caps combine only by taking the least permissive result; the first production catalog therefore always compiles tight;
- a later fully promoted, complete-history, confidence-at-least-0.90 noncritical context beat may compile its catalog-preferred wider tuple; the canonical material `{"beatId":"battle.approach","cycleAttemptOrdinal":1,"episodeId":"battle-ahead:3:17:22:4","episodeRevision":4,"opportunityId":"opp:401","streamEpoch":3}` hashes to seed `16041955996680716084`;
- repetition pressure chooses among eligible cards or leaves the candidate fatigued, while failure discards that beat revision; neither widens or mutates PromptOptions.

## F34 — detector tuning windows are fully replay-addressable

Input: record one required detector transition whose inclusive pre/post window is FeatureFrame sequence 200–214 and whose manifest parameter snapshot is `params:battle_ahead_v1:7`. Rotate the tape during the range, then separately lose frame 209. Repeat with optional capture.

Expected:

- both files repeat the identical bounded parameter-snapshot array and chained manifest identity; each frame is a typed `feature_frame` record and the observation resolves the exact detector/config hash, inclusive range and completed post-window;
- rotation does not create a new parameter snapshot or break the logical frame range, and replay reconstructs frames 200–214 in sequence without consulting current config;
- loss of required frame 209 is represented by drop accounting, makes the range incomplete and emits protected capture-unavailable behavior for only that experimental detector;
- optional loss remains explicitly incomplete/degraded but does not disable the production detector or fabricate/interpolate the frame; no unversioned input-sample side schema exists.

## F35 — a real new event replaces into a new planning cycle

Input: while cycle 70 attempt 1 is building a context beat, accept a new critical pass event whose candidate clears replacement cost and hard gates. Separately deliver a lower-scoring event. Fail the replacement candidate's verifier once.

Expected:

- the critical event cancels/releases the old token as `replaced_precommit` without suppression and closes cycle 70; its pass BeatPlan is attempt 1 of a new cycle 71, not attempt 2 of cycle 70;
- verifier failure may select one distinct still-valid beat as cycle 71 attempt 2; a second failure exhausts only cycle 71 and never retries either failed beat revision;
- the lower-scoring event is retained only through its opportunity TTL, does not cancel the current build and does not change that build's cycle/ordinal;
- every replacement is attributable to a recorded accepted-event impulse; pure facts, manual terminal and timer expiry can never reset the attempt budget or create a replacement loop.

## F36 — mixed-boundary config is explicit and replayable

Input: during an active race and while one BeatPlan from desired generation 6 is building, accept valid full config generation 7 changing `director.selection_threshold` (next director pass), `max_utterance_s` (next BeatPlan or manual admission), `tts.backend` (next utterance with preflight), `detector.battle_ahead_v1.max_closing_slope` (next stream) and `tape.detail` (next record). Hold the generation-7 TTS preflight pending, cross each available boundary, rotate the tape, then accept generation 8 reverting the still-pending detector value. Separately submit one invalid reload.

Expected:

- generation 7 immediately becomes desired, while the existing BeatPlan and its worker token retain generation-6 values/hash; status exposes distinct desired/effective hashes and only bounded sorted pending keys, never values or a fake service-restart requirement;
- `next_record`, `next_director_pass` and `next_beat_plan` each apply exactly their own sorted group and emit `config_applied` payloads with strictly increasing apply sequence, generation 7, old/new effective hashes and exact typed replay-safe patches; no boundary drains another group and sensitive local/name/device/path values use only the frozen redaction marker;
- the first new TTS admission applies the generation-7 utterance group but returns component unavailable while its matching preflight is pending; it never dispatches through generation 6. A stale preflight completion is ignored, and a current successful completion only enables a later normal admission impulse;
- the rotated file manifest snapshots the then-current desired/effective hashes and apply sequence; ConfigLedger's reserved recorder barrier places every transition after all old-snapshot records and before new-snapshot records, while detector parameter snapshots remain unchanged within the active run;
- with the barrier deliberately saturated, the config/lifecycle boundary still completes without blocking, the loss accumulator retains the missing sequence and hashes as `config_transition_lost`, later records expose the apply-sequence gap and replay is explicitly incomplete rather than silently using an old config;
- accepting generation 8 recomputes the entire pending set, so the reverted detector key disappears instead of applying generation 7 at the next stream; every remaining pending row is tagged 8;
- invalid input creates no desired generation or hash; the config coordinator atomically orders its `CONFIG_UPDATE` immediately before the coherent disable batch, which closes automatic narration as `disabled_invalid_config` while preserving the last valid ready effective backend only for manual TTS/diagnostics. No unrelated command may interleave, and a later valid enabled update is required to start another incomplete run.

## F37 — switch policy cannot be undone by urgency sort or filler

Input: a valid focused story continuation P has story urgency and score 76. In separate passes add: independent story A score 84; independent context B score 90; critical C score 36; and filler F score 100. Then, while an independent story BeatPlan with planned score 70 is building, accept a new context event whose raw score 90 becomes 78 after replacement cost.

Expected:

- A reaches the inclusive `76+8` margin and switches; B has lower urgency but also clears the margin and switches when no higher-urgency challenger exists, proving that a later global urgency sort cannot silently restore P;
- C switches by higher urgency despite its lower score, and if C and a margin-qualified challenger coexist the higher-urgency set is selected first;
- F never competes while P or any other story/event/episode candidate is selectable; it may be selected only in the fallback tier after that tier is empty;
- the building context challenger reaches exactly `70+8` after replacement cost and may replace as a new accepted-event planning cycle; the same candidate at 77 cannot replace, and no successor/filler/pure-fact/timer input can invoke this precommit replacement path;
- every result records the compared incumbent/challenger scores, urgency ranks, relation, margin, replacement cost and stable-tail inputs.

## F38 — realization input is frozen and freshness compares exact facts

Input: plan `battle.approach` from FactView 90 using relation fact R and gap fact G=1.4 seconds. In the same reducer turn compile its RealizationBundle, then let the live FactView advance while Qwen runs. Exercise separately: unrelated fact change; canonical-equal R/G copies retained; G superseded by G2=1.1; G evicted to unknown; actor alias changed in the live roster; and a malformed compiler output missing G's SurfaceValueSet.

Expected:

- bundle fact IDs equal sorted `selectedFactIds`; fact copies, collision-free actor bindings, exact finite EN surfaces, lexicon hash and bundle hash are frozen before worker dispatch, and Qwen/verifier receive no live state handle;
- an unrelated change or a new FactView retaining canonical-equal current R/G passes freshness and verifies against the original 1.4-second surfaces; a later roster alias cannot alter or invalidate the frozen bundle;
- superseded/different G2 and missing/evicted G both return `freshness_stale` before semantic parsing, release/suppress by the normal attempt rule and never rebuild the bundle around 1.1 seconds;
- malformed/missing surface data fails closed as `realization_input_invalid` before worker dispatch, consumes only that cycle attempt and is unreachable after catalog/registry schema validation;
- tape carries plan, bundle, fact and lexicon hashes plus captured content according to explicit redaction policy, sufficient to prove which immutable input produced the recorded completion/verdict.

## Required tape assertions per fixture

Each implementation fixture asserts the ordered subset that applies:

```text
context_applied → narrative_event → fact/episode/opportunity change
→ director_decision(score breakdown/reason)
→ llm_attempt? → PLAYBACK_ACCEPTED? → speech_exposure terminal
```

Every row carries catalog/config/policy hashes, source refs and the expected `tapeChannel`. Rejected candidates include hard/source gate or arbitration reason. Tests compare structured records, not prose logs.
