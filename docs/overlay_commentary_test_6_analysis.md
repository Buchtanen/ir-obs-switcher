# Overlay Commentary Test 6 — VOD + session tape analysis

Date: 2026-09-02

Branch: `refactor/200-n12-async-consumers`

Analyzed revision: `d8a88b7`

VOD: [Overlay Commentary Test 6](https://www.youtube.com/live/Fd347CqlkG4)

## Scope

This report evaluates only the content produced by irswitch:

- static system overlay,
- dynamic V4 event cards,
- commentary selection, LLM polish and TTS,
- session chapters and live timing.

The dashboards rendered by iRacing itself are reference evidence, not part of the evaluated overlay.

Evidence sources:

- full visual review of the 37:25 VOD,
- full audio transcription used for navigation and phrase comparison,
- the three production DEBUG tapes listed below,
- current implementation on the analyzed branch.

Application logs were not included. The tapes contain commentary and `llm_polish` rows, so the runtime log level was DEBUG and the most important decisions are still observable.

## Correction to the initial analysis

The session tape did record correctly. It was initially missing only from the local checkout and was later added to the branch. The earlier hypothesis about a disabled recorder or a different working directory does not apply to this stream.

The three files align with the VOD wall clock:

| Session | Tape | Rows | Header wall clock | Header mode |
| --- | --- | ---: | --- | --- |
| Practice | `recordings/overlay-20260901T223356Z-0-0.jsonl` | 1,185 | 22:33:56 UTC | `PRACTICE` |
| Qualifying | `recordings/overlay-20260901T224151Z-0-1.jsonl` | 1,479 | 22:41:51 UTC | `QUALIFYING` |
| Race | `recordings/overlay-20260901T225129Z-0-2.jsonl` | 1,710 | 22:51:29 UTC | `RACE` |

Together they contain 4,374 rows: 2,244 commentary decisions/finals, 867 event envelopes, 972 event decisions, 165 active-story snapshots, 106 LLM polish operations, 16 scene changes, three headers and one tape `green` marker. The attempt counters imply 386 model calls across those 106 operations; retries within one operation are sequential. The tape retains only the final response text for each operation, not every rejected intermediate text.

## Executive verdict

The system is connected and moving real data end to end, but the live result is not yet reliable enough. The dominant fallback and latency defects are deterministic prompt/validator defects, not an unreachable Qwen model. A controlled localhost replay also demonstrates a narrower model limitation: Qwen3:4b is reliable on simple and canonicalized beats, but is not consistently reliable when it must bind several drivers, positions and opposing gap directions while also adding creative colour.

| Area | Result for this VOD |
| --- | --- |
| LLM transport | Healthy: 106 operations, no HTTP error and no timeout fallback |
| Accepted LLM polish | 41/106 = 38.7% |
| Technical skeleton fallback | 65/106 = 61.3% |
| Semantic fidelity of final LLM output | 59/106 strictly grounded; 90/106 preserve the core facts/direction if safe editorial colour is allowed |
| Materially wrong final LLM output | 16/106 overall; 8/41 among outputs accepted and spoken |
| Audible commentary | 105 completed TTS calls, about 2.9 calls/minute |
| Static overlay | Stable and visually correct |
| Dynamic V4 stories | Unreliable because of invalid relations and unmatched EXIT identities |
| Session chapters | Incorrect because their clock resets during one continuous YouTube VOD |

The original audio-only estimate of roughly 47% skeleton-like speech was a lower estimate caused by ASR segmentation and by skeleton variants that do not match verbatim. The tape gives the authoritative technical value: **61.3% fallback**, or 64 of 105 completed audible calls after excluding the final call cancelled by `QUIT`.

The validator result must not be read as the model's factual success rate. A manual proposition-level audit found many false rejections and several false acceptances. The dominant remediation is therefore not to disable validation or globally lower every threshold. It is to reduce the prompt to selected propositions, align validation with those propositions, reserve hard rejection for material factual errors, and stop paying for repeated inference on style-only warnings.

### VOD checkpoints

VOD timestamps are playback-oriented; tape diagnosis below uses the more precise session `t_mono` and header wall clock.

| VOD checkpoint | Visible/audible symptom | Tape explanation |
| --- | --- | --- |
| [08:18](https://www.youtube.com/live/Fd347CqlkG4?t=498) | Qualifying but a large HUNTING card is visible | Negative signed gaps are accepted as close front relations |
| [19:47](https://www.youtube.com/live/Fd347CqlkG4?t=1187) | Green call says the race is already in its middle phase | Raw session time is already 106/480 s after formation |
| [25:44](https://www.youtube.com/live/Fd347CqlkG4?t=1544) | Commentary says the gap is closing while the displayed values grow | HUNTING was valid at ENTER but exited before LLM processing completed |
| [28:57](https://www.youtube.com/live/Fd347CqlkG4?t=1737) | P14 two-front card and sample copy | Active meta story is valid initially, but its later EXIT uses another correlation ID |
| [34:38](https://www.youtube.com/live/Fd347CqlkG4?t=2078) | P14 card remains while iRacing shows P30 | Stale P14/P15 stories are still present in the server's authoritative list |
| VOD chapters | Qualifying 01:06, Race 02:05, End 21:39 | Chapter offsets use a stream clock that resets between local stream segments |

## 1. LLM polish and skeleton fallback

### Measured outcomes

| Session | Operations | `ok` | `retry_exhausted` | Fallback rate |
| --- | ---: | ---: | ---: | ---: |
| Practice | 18 | 7 | 11 | 61.1% |
| Qualifying | 27 | 11 | 16 | 59.3% |
| Race | 61 | 23 | 38 | 62.3% |
| **Total** | **106** | **41** | **65** | **61.3%** |

There are no `fallback_timeout` or `fallback_error` outcomes. Every fallback is `retry_exhausted`: the model returned text, but the local validator rejected it until the retry budget ran out.

Latency:

| Population | Median | P90 | Maximum |
| --- | ---: | ---: | ---: |
| All operations | 4.06 s | 5.62 s | 12.01 s |
| Accepted output | 1.43 s | 3.61 s | 4.57 s |
| Retry exhausted | 4.69 s | 6.38 s | 12.01 s |

The median number of attempts is five. Sixty-four of 106 operations use the full five attempts. Retrying invalid variants is therefore both the primary fallback cause and the primary avoidable latency cost.

### Validator contradiction

The final rejected response carries these codes; one response may carry several:

| Code | Occurrences among final responses |
| --- | ---: |
| `invented_name` | 63 |
| `invented_position` | 52 |
| `missing_required_fact` | 8 |
| `invented_number` | 3 |
| `hero_vocative` | 1 |
| `invented_lead` | 1 |
| `two_front_polarity_conflict` | 1 |

For 53 of the 65 fallbacks, the final response is rejected only by `invented_name` and/or `invented_position`.

Two deterministic conflicts explain most of this:

1. `_PROPER_TOKEN` treats generated position/sector tokens such as `P13` and `S1` as possible proper names. `_invented_name()` exempts only exact `P` and `S`, not `P13`/`S1`.
2. `_token_set()` checks positions in the generated text only against the anchor skeleton. It does not allow a position explicitly supplied in selected optional facts. The prompt asks the model to use those optional facts, while the validator then rejects them.

This is why whole event families fail systematically:

- `POSITION_LOST`: 12/12 fallback,
- `INCIDENT_AFTERMATH`: 5/5 fallback,
- `FINISH`: 3/3 fallback,
- `LEADER_CHANGE`: 3/3 fallback,
- `SECTOR_BEST`: 3/3 fallback.

By contrast, all five `HUNTED`, all four `PARADE_PAD` and all three `PACE_HUNT` attempts succeeded. Qwen is capable of the desired richer style when the validator contract is internally consistent.

### Proposition-level semantic audit

The final LLM response from every polish operation was manually compared with its anchor, `REQUIRED_FACTS` and selected `OPTIONAL_FACTS`. `ALLOWED_NAMES` and `ALLOWED_NUMBERS` were treated only as token whitelists, not as evidence that an arbitrary relationship between those tokens is true.

The audit uses three grades:

- **strictly grounded**: every factual claim is supplied or is a direct paraphrase;
- **core-correct with unsupported colour**: required facts and direction are preserved, but the model adds soft claims such as “steady”, “in the midfield” or “with precision” that are not propositions in the fact pack;
- **materially wrong**: a new number, position, relationship, trend, event or temporal state is asserted, a material magnitude is mischaracterized, a required beat is lost, or no text is returned.

| Final LLM output | All 106 | Accepted 41 | Rejected 65 |
| --- | ---: | ---: | ---: |
| Strictly grounded | 59 (55.7%) | 20 (48.8%) | 39 (60.0%) |
| Core-correct with unsupported colour | 31 (29.2%) | 13 (31.7%) | 18 (27.7%) |
| Materially wrong | 16 (15.1%) | 8 (19.5%) | 8 (12.3%) |

Thus the model preserves the core fact and direction in **90/106 = 84.9%** of final outputs if controlled editorial colour is acceptable. Under the strict no-unsourced-claim standard it succeeds in **59/106 = 55.7%**.

The accepted population is not the safer population. At least 39 of 65 final rejected texts are clearly grounded false rejections; as many as 57/65 are semantically usable if controlled editorial colour is allowed. Conversely, 8/41 accepted and spoken texts contain a material semantic problem. Validator acceptance is therefore not a useful proxy for factual correctness in this recording.

#### Genuine model hallucinations and distortions

The recurring failure is composition of a new proposition from individually allowed atoms:

- Input `He completes lap 1 in 1:44.053.` becomes `... just 0.01 behind the pace.` The number `0.01` exists in the global allowed-number dump but is not a selected fact about that lap.
- Input `Gap to Leavine is 9.43 s.` gains `just 0.01 behind in sector three.` Both tokens are globally allowed; their relationship is invented.
- Input `The session gains a clear benchmark at 1:38.262.` gains `just ahead of Garner and Cross.` Their names are allowed, but no selected fact establishes that order.
- A static `8.22 s` gap gains `closing the gap slowly`; one snapshot cannot establish a trend.
- A `RIVAL_THREAT` line gains `he's ... closing in`, moving agency from the approaching rival to the hero.
- Gaps of 20.22 s and 13.58 s are described as `tight` or `close`, preserving the number while materially distorting its meaning.

Hard directionality is otherwise relatively strong. Non-null position-loss, position-gain, overtake, leader-change, hunting, hunted and two-front final responses normally retain their supplied actors and polarity. The more common error is an extra unsourced trend or magnitude, not a wholesale loss-to-gain inversion.

#### False validator rejections

Several final rejected texts are nearly exact realizations of the selected propositions:

- `Garner takes the lead from Busek. He is running P2.` is rejected for `invented_position` and `invented_name` even though both are supplied.
- `Richard drops from P7 to P8` preserves the loss and both positions but is rejected for `invented_name`.
- Two-front output preserves Karlsson ahead, Jr. behind and rounds `0.416625...`/`0.525443...` to `0.417`/`0.525`; it is rejected for invented name, position and number.

The contract is strict in the wrong place. It checks generated P/S tokens against the anchor rather than all selected propositions, treats some P/S tokens as proper names, and requires exact numeric membership rather than an explicit rounding tolerance.

#### Amount of rewriting

For the 105 operations with non-null final text:

- median character-sequence similarity to the canonical anchor is 47.3%;
- the output is median 2.10 times the anchor length;
- accepted outputs are median 2.35 times the anchor length and only 44.4% sequence-similar;
- rejected outputs are median 2.04 times the anchor length and 50.8% sequence-similar;
- median exact output-token support from the anchor plus selected required/optional facts is 66.7%, falling to 56.2% for accepted output and rising to 74.3% for rejected output.

These are lexical measurements, not semantic scores—valid synonyms count as new tokens. They nevertheless confirm that Qwen performs substantial rewriting, and that the current validator tends to accept the more novel population while rejecting output that stays closer to the supplied propositions.

#### Upstream false facts are not LLM hallucinations

Some wrong viewer statements are faithful realizations of bad supplied facts: `sof_class=0`, a `+0.000` gain, green already in `middle`, and active narrative facts in `finished`/`checkered` phase. These require fact-builder, run-lifecycle and freshness fixes. A proposition-level validator can stop the model from inventing additional claims, but cannot make a supplied false proposition true.

### Prompt size, validator threshold and causal chain

The median final request contains 861 prompt tokens for only 24 completion tokens. Much of the input is the global `ALLOWED_NUMBERS` telemetry dump rather than selected narrative evidence. The tapes do not separate prompt-evaluation and decode timing, so the exact latency saving from a smaller prompt cannot be measured from this recording. It is nevertheless a direct and testable optimization: every retry reprocesses the large prompt, while the short output contributes little of the token load.

The evidence supports this causal chain:

```text
oversized, weakly bound prompt
    -> slower inference and tempting irrelevant atoms
misaligned hard validator
    -> false rejection of valid optional facts
up to five sequential retries
    -> median 4.69 s on retry-exhausted operations
larger live-data staleness window
    -> commentary can begin after the raw situation has changed
```

Lowering validator thresholds is beneficial only when it means converting known false-positive and style-only rules from hard rejection into acceptance or warning. A global relaxation is unsafe because the current validator already accepts new propositions assembled from whitelisted names and numbers. The correct change is:

1. reduce the prompt to selected, proposition-bound facts;
2. validate material claims against those same propositions;
3. hard-reject new identity, number, position, event, polarity or temporal claims;
4. treat safe stylistic colour separately and do not retry it;
5. allow one bounded corrective retry only for a repairable hard failure.

This should improve first-pass acceptance, fallback rate, latency and freshness together. It reduces the temporal race but cannot eliminate it; live data can change during even a one-second inference, so the mini-story lifecycle remains required.

### Controlled localhost Qwen replay

The model was retested directly at `http://127.0.0.1:11434/v1/chat/completions` using the production model `qwen3:4b-instruct-2507-q4_K_M`, temperature 0.45 and repeated calls. The test used corrected facts derived from tape cases and removed the global telemetry whitelist.

| Probe | Calls | Result | Latency / prompt |
| --- | ---: | --- | --- |
| Compact structured selected facts | 40 | 35/40 factually correct; all five initial rival-threat calls reversed the subject/object wording | warm calls mostly 0.4–0.9 s; one cold call 3.21 s; 167–244 prompt tokens |
| Canonical fact sentences plus explicit style goal | 24 | 20/24 factually correct; simple beats and resolved hunt were correct, but multi-role position/gap binding still failed | median 0.47 s; P90 0.75 s; median 180 prompt tokens |
| Redundant `HERO`/`FRONT`/`REAR` role binding | 10 | 10/10 preserved core direction and position, but repeatedly added unsupported `fast`, `hard`, `steady` or a meta prefix | median 0.98 s; 166–204 prompt tokens |
| Complete canonical BASE sentence, surface polish only | 15 | 15/15 factually correct and TTS-usable; 14/15 were returned essentially unchanged | median 0.64 s; 119–135 prompt tokens |
| Canonical BASE plus explicitly allowed creative colour | 15 | only 6/15 preserved all required meaning; four two-front calls inverted the rear-gap phrasing and five rival-threat calls omitted Leavine/P14 | median 0.72 s; 140–156 prompt tokens |

A second prompt-strategy matrix explored fact splitting, self-checking, repair, fact density and in-context examples:

| Strategy | Observed result | Verdict |
| --- | --- | --- |
| One relation per request, then concatenate | Core clauses retained their facts, but every rear clause invented an extra trend such as `gap remains steady` or `gap narrows`; warm sequential wall time was about 1.4–1.5 s and concurrent calls did not reduce it | Do not split one utterance into blind independent requests; the local server effectively serialized the work and cohesion/grounding worsened |
| Sealed whole-clause placeholders | 6/6 retained factual spans, median 0.57 s and about 116 prompt tokens, but substitution produced poor grammar because the model merely placed opaque clauses next to each other | Useful only with a typed grammar/scaffold; not sufficient as a free-form solution |
| JSON commentary plus model `claim_check` | Median 2.76 s; all three two-front commentaries reversed Karlsson's direction while their own JSON check reported the correct relation | Model self-check is not an independent validator and adds excessive output/latency |
| Creative draft plus low-temperature repair | Two-front repaired correctly 3/3, rival threat only 2/3; one repair retained an invented `desperate bid to overtake`; total 1.2–2.34 s | Better than five retries, but still not reliable enough as the default path |
| Resolved arc with only two required beats | 5/5 natural and grounded when gap/P13 were optional; median 0.54 s | Strong fit for story-director-selected resolved mini-stories |
| One family-specific few-shot example | Two-front 5/5 and rival threat 5/5 correct; median 0.83 s/0.66 s with 251/241 prompt tokens | Best general result for the 4B model |
| Three family-specific style cards | 9/9 correct across fact-first, tension-first and road-and-mirrors forms; median 0.78–0.99 s with 161–167 prompt tokens | Best combination of factual binding, genuine language realization and controlled variety |

The successful style-card outputs were materially different while preserving the same two-front truth:

> Richard runs P15, 0.42 seconds behind Karlsson, while Jr. applies pressure from 0.53 seconds back.

> Pressure at both ends for Richard in P15: Richard is 0.42 seconds behind Karlsson, with Jr. applying pressure from 0.53 seconds behind.

> Richard runs P15, 0.42 seconds behind Karlsson, Jr. is 0.53 seconds behind Richard and applying pressure—the track and mirrors demand equal attention.

All nine style-card calls were correct. Qwen did not merely repeat a supplied target sentence; it transferred a tested sentence structure from different example drivers/numbers to the current facts.

Temperature was not the main source of variety in a well-constrained prompt. The same lean rival-threat request was run four times each at 0.2, 0.45, 0.65 and 0.9. All 16 outputs were grounded and nearly identical. For this model, family-specific examples and selected content density dominate sampling temperature.

Generic textual style levels were less reliable than style cards. `neutral` and `broadcast` were mostly usable, while a generic `narrative` instruction became repetitive, omitted actors and reintroduced current-tense action. A level must therefore select a tested prompt contract/example, not merely add an adjective such as “narrative” to the instruction.

Representative successful resolved mini-story:

> Richard closed on Gjoel, but the move never materialized — the chance is gone for now. Richard remains P13.

Representative multi-role failure despite correct input:

- supplied: Karlsson is 0.42 s ahead of Richard; Jr. is 0.53 s behind Richard;
- generated repeatedly: `Richard ... 0.42 behind Karlsson, 0.53 behind Jr.`

The second clause places Richard behind Jr. and reverses the rear relationship. This is a model binding error, not a validator false positive or bad live data.

Repeated calls at temperature 0.45 are also highly correlated. Many cases returned exactly the same sentence on every call, including the same mistake. Blindly repeating the same prompt is therefore not an effective repair strategy; it mainly adds latency. A retry is useful only when its input contract changes in a targeted way.

The supported design boundary is now clearer:

- the graph/story director owns race truth, story identity, actor binding, direction, fact density and required-versus-optional selection;
- the director selects a tested family-specific style card rather than one global instruction prompt;
- Qwen transfers that example's sentence structure and approved colour to the current selected facts in one request;
- simple volatile beats use a lean fact-first card; multi-role beats use a relation-specific card; resolved arcs use ordered required beats and optional context;
- creative colour is an explicitly selected editorial proposition, with required-fact coverage and actor/relation direction revalidated after generation;
- every microplan retains a complete canonical fallback, but the canonical sentence is not the normal Qwen input/output target;
- complex relation output falls back immediately when it fails the dedicated binding check; a repeated identical request and model-generated self-check are not repair mechanisms.

This retains useful LLM polish without pretending that prompt reduction alone makes the 4B model propositionally reliable in every event family.

## 2. Global stream story, mini-stories and freshness

The initial review suspected a large commentary queue backlog. The tape disproves that as the general cause.

The estimated wait from commentary selection until the LLM worker starts is normally negligible:

- median below 0.01 s in every session,
- P90 at or below 0.053 s,
- one race outlier of approximately 3.8 s.

The `tts_final` timestamp is emitted after `speak_text()` returns, so selection-to-`tts_final` includes the duration of the spoken audio and must not be interpreted as start latency. The normal pre-speech delay is dominated by LLM generation, especially the 4.69 s median for retry-exhausted calls.

The stream should be treated as one global story composed of editorial mini-stories. A raw ENTER/ACTIVE/EXIT relation supplies live evidence to a mini-story; it is not itself the lifetime of the narrated story.

The real live-data defect is the absence of that editorial lifecycle and of revalidation after LLM work. Examples from the race tape:

1. At `t_mono=467.81`, HUNTING enters for Gjoel with gap 1.168 s and positive closing rate 0.391 s/s. The relation exits at 471.29, but the LLM finishes at 472.43 and the now-obsolete “closing” call still proceeds to TTS.
2. At `t_mono=487.36`, HUNTING enters at gap 1.318 s and closing rate 0.108 s/s. It exits at 489.75; retry processing finishes only at 492.28 and the skeleton is still spoken.

Therefore the detector was often correct at event time. The false present-tense statement heard by viewers is created because a volatile relationship can resolve while the LLM is working, and neither the polish worker nor TTS rechecks correlation identity, target, run epoch, current facts or resolution before committing the narration.

The required lifecycle is:

```text
CANDIDATE -> BUILDING -> READY -> COMMITTED/SPEAKING -> COMPLETED
                 |          |
                 |          +-> INVALIDATED before commit: discard
                 +-> RESOLVED: incorporate the outcome and finish the mini-story

COMMITTED/SPEAKING -- hero order change --> INTERRUPTED
```

While a mini-story is `BUILDING`, its fact ledger remains live. If the gap stops closing before the LLM returns, that natural resolution should update the ending and tense; it should not automatically delete the editorial story or allow stale present-tense copy to start. An invalid identity, changed run epoch or unusable data is different: that invalidates an uncommitted draft.

The transition from `READY` to `COMMITTED/SPEAKING` is the narrative commit point. It must verify the current hero order, target identity, run epoch and resolution. Once speech begins, a normal raw EXIT does not abort the story: commentary and the associated visual story get a narrative lease and finish the mini-story. Under the stated product rule, only a hero order change is a normal editorial hard preemption; it interrupts speech and immediately starts the gained/lost-position story.

After completion, the next mini-story must be selected from current authoritative state. Uncommitted candidates should be coalesced by semantic identity rather than retained in a stale FIFO queue.

Reducing prompt size and eliminating validator-driven retries materially shortens the `BUILDING` window and will prevent many observed stale calls. It does not replace this lifecycle. Even the measured 1.23 s median first inference is long enough for a battle relation to change, and an already committed story must have different semantics from a draft that has not started speaking.

## 3. Dynamic overlay correctness

### Invalid signed gaps

Across HUNTING, HUNTED, APPROACH, ATTACK_RANGE and RIVAL_THREAT ENTER/ACTIVE envelopes:

- 122 relation envelopes were created,
- 82 of them carry a negative gap,
- **67.2% of relation activations are therefore directionally invalid.**

Breakdown:

| Event | Negative / total ENTER+ACTIVE |
| --- | ---: |
| APPROACH | 14/14 |
| ATTACK_RANGE | 12/12 |
| RIVAL_THREAT | 10/10 |
| HUNTED | 20/24 |
| HUNTING | 26/62 |

The emitter checks `gap < enter_gap` but not `gap >= 0`. A value such as `-37.74` therefore qualifies as very close and is promoted through HUNTING to APPROACH/ATTACK_RANGE. The renderer formats the magnitude and viewers see `37.74 s` or `62.75 s` as a plausible-looking positive value.

This directly explains the impossible large battle cards visible in Practice and Qualifying.

### EXIT correlation mismatch

When a target disappears, the exit payload is built from the new empty target instead of the active relation retained by the state machine.

Concrete Qualifying example:

- active story: `battle:front:0:28:8` for Garner,
- gap at the end: approximately `-38.98 s`,
- emitted EXIT: `battle:front:player:unknown:0`.

Because the IDs differ, `EventManagerV2._remove_active_v4()` cannot remove the active story.

The same problem affects the meta battle:

- active story: `battle:two-front:0:20:26:19:12`,
- emitted EXIT: `battle:two-front:player:unknown:unknown:0:0`.

The race tape ends with stale authoritative stories for P15, P14 and a RIVAL_THREAT carrying gap `-12.36 s`. This matches the P14 battle card still visible when iRacing shows P30 near the end of the VOD.

### Empty state snapshots are not broadcast

`OverlayBus.set_active_stories_v4()` replaces the list but does not mark a dirty domain. `flush_state()` therefore does not broadcast an authoritative `STATE_SNAPSHOT`, including the empty list created by `SessionReset`.

Additionally, a new WebSocket client receives `STATE_SNAPSHOT` only when the server list is non-empty. An empty authoritative state never explicitly clears an existing renderer.

The client implementation can clear correctly—`applyStateSnapshot()` first calls `clear()`—but it does not receive the empty snapshot. Client `maxHoldMs` is only a safety timer; a stale authoritative story can reappear after reconnect/reload.

### Renderer copy

`battle_for_position` always fills its meta field from manifest sample text (`stack centre`). This is design-time copy leaking into production. Missing real metadata should render as empty or as a deliberately authored viewer label, not sample fixture text.

## 4. Race restart and phase semantics

The Race tape contains two starts inside the same iRacing `sessionId=0:2`:

1. first green at `t_mono=106.01`,
2. replay/lobby transition at 279.46–286.37,
3. `SessionTime` rewinds from about 279.65 s to 0.35 s,
4. the car returns to RACE mode at 291.97,
5. a second green commentary event occurs later.

Only one tape `green` marker exists because the green origin is never reset inside an unchanged subsession/session number. The same missing run reset can preserve event identities, stories, recent commentary and race-phase context across a restart.

The “middle phase” call immediately at green is also deterministic. `build_situation_payload()` computes timed-session progress from `SessionTime / SessionTimeTotal`. At green the tape contains roughly 106/480 = 22.1%, just above the 20% threshold for `middle`. Formation and aborted-start time has consumed the opening phase before the race actually starts.

Race phase for commentary must be based on green-relative race progress or completed racing laps, not the raw session clock that includes formation and restart time.

## 5. Chapter clock

The incorrect YouTube chapters are now fully explained by tape evidence:

| Chapter | Tape header `t_stream` | Published chapter |
| --- | ---: | ---: |
| Practice | 16.137 s | 00:16 |
| Qualifying | 66.229 s | 01:06 |
| Race | 125.004 s | 02:05 |

They are exact matches. Each session tape attaches to a newly reset `Metrics.stream_started_ts`, although the YouTube broadcast remains one continuous VOD. The final `Stream end 21:39` is likewise the duration of the last local stream segment, not the VOD.

`StreamChapterTracker` debounces short false streaming states, but `Metrics.set_streaming(False)` resets `stream_started_ts` immediately. When streaming resumes within the chapter debounce window, chapter history is retained while its duration clock has restarted. The two components therefore implement incompatible flicker semantics.

The server already receives OBS `outputDuration`; chapter offsets should use that authoritative duration when monotonic and fall back to a non-decreasing cumulative broadcast clock. A chapter offset must never move backwards during one retained chapter history.

## 6. Static overlay

The static system bar is the strongest part of the stream:

- stable placement and rendering,
- no material obstruction of gameplay,
- CPU/GPU/RAM/FPS values remain coherent,
- unavailable heart-rate data is shown as `--` rather than a stale measurement.

No corrective work is required here beyond ordinary readability testing at YouTube playback scale.

## Refined fix list

This is a prioritized defect list, not yet the implementation plan.

### P0-A — compact grounded generation and bounded latency

1. **Introduce a graph-owned commentary microplan.** For each mini-story, select a bounded set of required facts, optional context, story state (`live`/`resolved`), complexity class, a tested style-card ID and a complete canonical fallback. The graph/director owns actor binding, direction, values and outcome; optional facts such as P14/P15 or a second gap are included only when they improve this spoken beat rather than because they are available.
2. **Use family-specific few-shot style cards and explicit safe colour.** Maintain tested cards such as fact-first, tension-first, road-and-mirrors and resolved-arc per compatible event family. Each card contains one short example with different placeholder drivers/values; Qwen transfers its sentence structure to the microplan's facts. Magnitude, trend, order, timing and causality remain facts and require evidence; `20.22 s` may not become `tight`, and a single gap sample may not become `closing slowly`.
3. **Make validator severity explicit.** Hard rejection is reserved for a missing required proposition or a new material name, number, position, sector, event, relation, polarity, magnitude, cause or temporal state. Safe style variance is accepted; presentational issues that can be sanitized deterministically do not trigger another inference.
4. **Repair known false-positive rules.** Exempt `P<number>` and `S<number>` from name detection; validate positions, sectors, names and numbers against all selected required/optional propositions; allow configured numeric rounding tolerance; validate two-front direction against structured subjects rather than phrase proximity.
5. **Validate propositions, actor binding and required coverage—not global token membership.** A number or name appearing in a whitelist is not permission to claim a delta, sector result or race-order relationship. Verify that every required actor/value survives, every generated relation has the same subject/object direction, and no safe-colour rewrite drops the core beat. This closes both the old false-acceptance path (`0.01 behind in sector three`) and the controlled-replay failures (`0.53 behind Jr.` or omitted Leavine/P14).
6. **Bound retries after the contract repair.** Default to one style-card generation. Style-only warnings never retry. A hard actor/relation failure normally uses the canonical microplan fallback immediately; permit one corrective retry only when it changes to a known stricter card/contract. Never repeat an identical prompt and never trust a model-authored self-check as validation.
7. **Instrument prompt and inference cost.** Record prompt/completion tokens and, where the backend exposes them, prompt-evaluation time, decode time and per-attempt latency. Replay the same 106-operation corpus before and after the change rather than assuming prompt reduction alone explains every millisecond.

Expected causal result: prompts around the measured 160–250-token style-card range, less prompt evaluation, fewer tempting irrelevant atoms, much higher first-pass acceptance, no five-call retry loops, lower fallback, controlled linguistic variety and a shorter window in which live facts can age before narrative commit.

### P0-B — editorial mini-story lifecycle

8. **Introduce an editorial `MiniStory` independent of raw event lifetime.** Track semantic identity, run epoch, hero order baseline, live fact ledger, resolution and lifecycle state: `CANDIDATE`, `BUILDING`, `READY`, `COMMITTED/SPEAKING`, `COMPLETED`, plus pre-commit `INVALIDATED` and normal `RESOLVED` outcome.
9. **Keep facts live while building.** Refresh volatile values and relation state during LLM work. A natural event EXIT resolves the mini-story and supplies its ending; it does not automatically delete the story. If necessary, finalize it in past/result framing before commit rather than speaking an obsolete present-tense sentence.
10. **Add a narrative commit gate immediately before TTS.** Verify target identity, run epoch, hero order and current resolution. Discard only technically invalidated drafts. Do not implement the earlier blanket rule that every exited correlation is dropped.
11. **Give committed narration a narrative lease.** Once speech starts, finish the mini-story despite ordinary raw EXIT. Keep the visual mini-story aligned with the same lease and allow it to show a resolved/result state while speech completes.
12. **Use hero order change as the normal hard preemption.** Interrupt current TTS and visual narration, invalidate uncommitted candidates based on the previous order, and immediately narrate the gained/lost-position beat. Session teardown remains technical cancellation rather than a competing editorial story.
13. **Coalesce uncommitted candidates by semantic identity.** After a story completes, choose from the latest authoritative state rather than an old FIFO item. Do not begin a new mini-story whose target, run or facts are no longer current.

### P0-C — live relation and overlay correctness

14. **Reject invalid relation gaps.** Require finite, non-negative gaps for front/rear battle and rival-threat activation; validate that front/rear class positions agree with the claimed direction. Never promote negative gaps through the intensity ladder.
15. **Make relation identity stable through EXIT.** Retain target car, relation epoch and two-front key in `_Track`/meta state. Every EXIT must reuse the exact active `correlationId`/`storyKey`, including target loss, session finish, pit abort and target change.
16. **Broadcast authoritative story snapshots, including empty.** Mark stories dirty, send `STATE_SNAPSHOT` after every authoritative change and reset, and always send an empty snapshot to a newly connected client.
17. **Detect a restarted run inside the same iRacing session.** A material `SessionTime` rewind or equivalent restart transition must increment a run epoch and reset event managers, green origin, editorial narrative state, active stories and uncommitted commentary.

### P1 — source-fact and eligibility quality

18. **Make race phase green-relative.** Formation and aborted-start time must not produce `middle` at green; reset phase on every run epoch.
19. **Suppress invalid facts.** Do not emit SoF/class strength when value is zero/unknown; do not verbalize a delta whose absolute value is below a meaningful epsilon.
20. **Tighten post-finish eligibility.** After FINISH/mute, allow only result/wrap content and required cleanup; suppress generic field facts and low-value incident aftermath.

### P1 — chapter correctness

21. **Use a non-decreasing broadcast clock.** Prefer OBS `outputDuration`; preserve a monotonic VOD offset through status flicker/reconnect; never combine retained chapter history with a reset current-session duration.
22. **Confirm stream end against the same lifecycle.** Append `Stream end` only after a confirmed broadcast stop, not after a transient OBS status loss.

### P2 — presentation and observability

23. **Remove manifest sample copy from live cards.** Replace `stack centre` and similar fixture metadata with real event data or empty viewer-safe copy.
24. **Strengthen tape observability.** Log the resolved absolute tape path on open, retain `lastPath` after close, expose last successful write/error time and do not report `recording` after a failed header write.
25. **Add VOD/tape acceptance metrics.** Track strict semantic grounding, material false acceptance, technical fallback, first-pass acceptance, prompt tokens, per-attempt latency, mini-story resolution/invalidations, hard preemptions, unmatched EXIT count, negative-gap rejection and chapter-clock regressions.

## Recommended acceptance targets

These targets should be converted into implementation-plan acceptance criteria later:

- median prompt size reduced by at least 50% from the 861-token baseline on the same replay corpus,
- first-pass technical acceptance at or above 85%, with no operation making more than two model calls,
- technical LLM fallback below 15% on the same replay corpus,
- zero accepted output with a material new number, name relationship, position, direction, event or temporal claim,
- at least 95% of accepted output either strictly grounded or within the explicitly approved safe-colour policy,
- every style card passes actor/position/direction and required-coverage checks in at least five repeated generations per compatible event family,
- at least three approved style cards produce materially distinct grounded realizations for the same representative two-front microplan,
- median polish completion below 2 seconds and P90 below 3 seconds on the same machine and replay corpus,
- no ENTER/ACTIVE battle relation with a negative or non-finite gap,
- every active story removed by a matching EXIT or authoritative empty snapshot,
- no green call with phase `middle` before green-relative progress reaches the threshold,
- no uncommitted mini-story starts with stale present-tense facts after resolution,
- a normally resolved mini-story that has been committed finishes without interruption,
- hero order change preempts the active mini-story and invalidates stale queued candidates,
- chapter offsets strictly non-decreasing and aligned with the continuous VOD clock,
- zero/unknown SoF and zero deltas never reach commentary,
- no sample/fixture text in the live renderer.

## Implementation-plan boundary

The test-first implementation sequence, workstream dependencies, acceptance criteria,
regression scope, replay verification and docs/config impact are specified in
[Overlay and Commentary Test 6 — Fix Implementation Plan](overlay_commentary_test_6_fix_implementation_plan.md).
