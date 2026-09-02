# Commentary engine (Phase 0)

**Status:** EN+CS graph v2, N12 independent consumers, stateful graph runtime (`legacy | shadow | active`), bounded story history, grounded commentary planner, TTS and `/commentary`. Commentary and active graph mode both remain explicit opt-ins.
**Implementation branch:** `feat/stateful-commentary-sequence-graph`; Windows/OBS/Ollama live validation pending.

## Why

Overlay copy is i18n **tokens** (`PŘEDJETÍ`), not speech. Event Engine already decides *what happened* and *who won arbitration*. Commentary sits **after** that and decides *whether to speak* and *which sequence node* to use.

Texts are filled later by another model. This repo owns the graph, validator, assignment briefs, and director.

## Voice (viewer-facing)

Commentary is **for the stream audience**, not pit-wall radio to the driver.

- EN: third person / broadcast, mixing the driver's name or nickname with he/him/his (“Richard is closing on Rossi.” / “That's a lap for Buchtanen.”)
- CS: třetí osoba / komentář pro diváky, jméno nebo přezdívka namíchaná se zájmeny (“Richard uzavírá kolo.” / “To je kolo pro Buchtanena.”)
- Never second person to the driver (“You take P5”, “Jsi pátý” as address)
- Never a vocative opener: not `{target_name}, ...` and not `Richard, that's a lap` / `Richard. That's a lap`. Commentary talks **about** the driver, not **to** them.
- Light viewer asides OK; keep one breath; slots unchanged

## Pipeline

```text
iRacing / BLE HR
    → EventEngine emitters → CandidateEvent
    → EventManager / V2 (priority, cooldown, pit guard)
    → accepted EventEnvelope
    → CommentaryConsumer-owned SequenceGraphRuntime
       (transition + semantic/node/edge/path fatigue + SILENCE pressure)
    → CommentaryDirector (graph winner + HR emotion)
       ├─ llm_polish=false: one authored fully-bound line
       └─ llm_polish=true: microplan + selected facts + style card
    → validate_utterance
    → independent TtsSink worker (optional grounded LLM generation)
    → MiniStory commit gate against latest run/order/relation state
    → TtsSink (Windows SAPI / SuperTonic CPU / espeak-ng / NullTtsSink)
```

**Wired, default off:** optional local/LAN LLM realization receives a compact immutable microplan with selected propositions and one compatible style card, never the full graph, unrelated telemetry, authored anchor, or raw recent commentary. The default model is Ollama `qwen3:4b-instruct-2507-q4_K_M`; [the earlier skeleton PoC](docs/commentary_llm_skeleton_poc.md) remains historical context.

Local Ollama smoke (2026-09-02): grounded `HUNTING` passed in two attempts (~1.7 s) with relation + gap + remaining-laps facts; `LEADER_CHANGE` passed on the first attempt (~0.7 s) without inventing an on-track pass. Windows/SAPI/OBS live listening is still pending.

### Recorded polish evaluation

The proposition-based regression corpus in
`tests/fixtures/commentary/commentary_eval_cases.json` references concrete
`llm_polish` operations from the three `recordings/overlay-20260901T*.jsonl`
tapes. It declares required fact IDs, relation direction, forbidden claims,
source eligibility and known invalid facts; it does not require one exact
output sentence.

Run the deterministic recorded baseline from a configured development shell:

```bash
python -m irswitch.commentary.replay_eval
```

The JSON report includes operation/call/fallback counts, attempts, latency,
prompt/completion tokens and per-case hard semantic findings. To deliberately
repeat stored requests against an OpenAI-compatible local Qwen endpoint, add
`--live-url http://localhost:11434/v1` and optionally `--live-limit N`. CI and
the normal test suite never require the local model.

Rules:

- Hook **accepted envelopes only**. Raw candidates are too noisy.
- `[commentary.graph_runtime] mode=legacy` preserves the compatibility path; `shadow` records score breakdowns while legacy remains audible; `active` is authoritative for repeated live/context families and bounded filler batches.
- Graph fatigue mutates only on TTS `speaking`; scoring, rejection, parking, and pre-audio invalidation do not count as audience exposure. Completion/interruption starts `SILENCE` dwell on the consumer lane.
- In active mode RaceObserver derives at most four factual filler candidates. Producer identity and immutable batch ordering remain normal; the graph selects one rather than using observer rotation.
- Works with **legacy** EventManager (`v2_payload=false`, default) via a speech map for `lap_complete` / `pit_entry` / `pit_exit`. V2 envelopes are used when present; the map fills gaps (basic pit has no V2 adapter).
- `in_car` is a commentary sidecar (`player_car_idx` rising, event type `ENTER_CAR`). It is **not** an overlay HUD catalog entry and is **not** pit entry.
- Session intros / SoF / weather are commentary sidecars (`SessionBriefsDetector`, gated by `commentary.session_briefs`). They are **not** overlay HUD catalog entries.
- `STREAM_START` is a commentary-only envelope from the OBS streaming rising edge (`commentary.stream_start`, default off). Graph node `stream_start` is a long slot-free welcome (`tts.max_seconds` ≥ 15); the process timeout uses that node cap so `commentary.max_utterance_s` (default 6) stays unchanged. An **opener mutex** (120 s) plus director `_busy_until` lets at most one of stream start / in-car / session intro / preview speak.
- Mode-specific `in_car_practice` / `in_car_qualify` / `in_car_race` nodes outrank generic `in_car` when `envelope.mode` matches. Generic `in_car` remains for warmup until those lines migrate.
- Gap-hunt TTS (`HUNTING` / `HUNTED`) is off in practice/qualifying unless `commentary.gap_hunt_tts_in_practice` / `gap_hunt_tts_in_qualifying` is on. HUD hunting is unchanged. Race still speaks.
- P/Q hunt-by-time is COMMENTARY_ONLY `PACE_HUNT` (`race/timing_hunt.py`): hero projected/best vs `CarIdxBestLapTime` of class P{n}. Unset times → silence. Quali HUD `position_attack` remains hero own PB.
- `INCIDENT` `metrics.branch` is `off_track` or `unknown` only when `race_observer.incident_classify` is on (default off). Nearby cars are metrics, not spoken kinds. Graph nodes `incident_off_track` / `incident_unknown` (N11 B); unclassified envelopes still use generic `incident`. Same tick: speak at most one of engine `INCIDENT` (delta ≥ `incident_min_delta` default 2) and derived `INCIDENT_AFTERMATH` (any rise); INCIDENT wins. Aftermath classify is surface-first (off-track stays stalled even if Speed > 0). Speed is motion for on-track stalled/rolling and `BACK_UNDER_WAY`. No `INCIDENT_RECOVERED`.
- Race `SESSION_FLAG` (`race/flags.py`) speaks yellow (caution family coalesced) / green / checkered on rising edges when `race_observer.flags` is on (default off). Start lights ignored. Checkered bit is not `FINISH` / `SESSION_WRAP`. Graph one-liners `session_flag_*` (N11 C); formatter remains fallback. Practice/qualify do not speak.
- Race-start `QUALI_RECAP` / `PARADE_PAD` (`race/grid_story.py`) when `race_observer.grid_story` is on (default off). Recap is an opener and replaces `SESSION_INTRO_RACE` when the stream quali bag exists. Parade pads repeat until Racing or green (20 s, cap 12). Not gated by `session_briefs`. Graph copy N11 D; formatter remains fallback.
- Watcher decision ring (`race/watcher_log.py`, size 64): DEBUG + in-memory last-N for flags / incidents / aftermath / hunt / grid_story / briefs. Director records `graph_hit`, `formatter_fallback`, and `generic_suppressed` (branch incident node spoke instead of generic). No public GET; not in `/commentary` status.
- Overlay priorities stay visual. Voice has its own `speak_priority` + `commentary.cooldown_s`.
- BLE HR is optional emotion. Missing sensor → `unknown` / `neutral`. Empty emotion cells fall back to `neutral` (mock stays audible with HR connected).
- Fail-soft: graph load / observe errors must not break the race loop.

## Sequence graph (not Neo4j)

`src/irswitch/commentary/data/sequence_graph.json` is a **graph-shaped JSON** (nodes + edges). Stdlib only — no new database dependency. Schema v2 adds validated, typed `editorial` metadata to every node and edge for the stateful graph rollout. The metadata is parsed but does not change audible selection while graph-runtime mode remains legacy; schema v1 remains readable for one compatibility release.

| Field | Role |
| --- | --- |
| `nodes.*.event_types` / `phases` | Match catalog event + wire phase |
| `nodes.*.modes` | Optional. `practice` / `qualify` / `race` / `warmup`. Empty = all sessions. Envelope `PRACTICE`/`QUALIFYING`/`RACE`/`GENERIC` map onto those tokens. |
| `nodes.*.branch` | Optional. Matches `envelope.metrics.branch` (e.g. `off_track`). Missing branch = generic fallback. |
| `speak_priority` / `cooldown_s` | Voice budget (independent of `[events.priorities]`). After mode/branch filter, highest `speak_priority` wins. `_follow_edge` runs **only on the filtered set**. |
| `slots` | `{position}`, `{gap}`, … bound from envelope metrics. Timing slots (`lap_time`, `gap`, `delta`, `segment_time`, `target_time`, `projected_time`) are spoken via `sdk_units`-style formatters in `slot_format.py`; sentinel / invalid values leave the slot unbound so that candidate line is skipped (re-draw). |
| `hr_states` | Which BLE bands may pick this node |
| `variants.{locale}.{emotion}` | Spoken lines. EN mock filled on `in_car`, `lap_complete`, `pit_entry`, `back_on_track`. CS empty (falls back to EN). |
| `edges` | Temporal story transitions. They prefer the next beat and let the composer recover a bounded prior-node path (e.g. hunting → side_by_side → overtake). |
| `nodes.*.editorial` | Graph v2 policy, semantic/material-change policy, criticality, repeat weight and silence affinity. Runtime counters are never stored in JSON. |
| `edges.*.editorial` | Graph v2 transition bonus, closure marker and repeat weight. |

Visual-only catalog events (`CPU_TEMP_HIGH`, `LINK_DROP`, `BLE_LOST`, gap `UPDATE`s) are **not** in the speak graph.

### Grounded planner (`llm_polish=true`)

`RaceObserver` owns a session-scoped ring of the latest 24 accepted factual beats. The frozen N12 context carries that history to commentary; `CommentaryConsumer` never receives a live observer reference. `composer.py` still walks backwards over valid graph edges (maximum three nodes) for story identity, but it no longer joins history, position, remaining laps and phase into mandatory prose.

The composer builds a complete deterministic canonical sentence and `commentary-microplan/1`. `commentary-facts/3` carries only selected required/optional propositions, actor roles, relation, time frame and the graph-selected style card. Single-role stories select one required proposition plus at most one metric; two-front stories retain both actor directions. The authored variant remains useful for the non-LLM path but is not sent as wording for the model to copy.

The model writes one or two freshly phrased sentences inside the node TTS limit. Hard fact guards reject unsupported events, passes/leads/position gains, new P/S markers, numbers, names, role swaps and direction inversions. P/S tokens are parsed before name detection and numeric comparison preserves decimal precision. Punctuation/style warnings are normalized or accepted without retry. One hard rejection changes to a shorter fact-first request; a second rejection speaks the complete canonical fact realization. Timeout/transport outage immediately uses that canonical text, so identical calls are not repeated.

All 54 active graph nodes and all 24 edges have compatibility tests. `leader_change` (prio 75) speaks class P1 changes; do not invent an on-track pass. Parade pads repeat until green (cap 12, 20 s). `two_front_battle` is the only graph node allowed to speak an `UPDATE`; its node cooldown still controls cadence. Other UPDATE events remain silent.

### Editorial mini-story lifecycle

`MiniStoryRegistry` separates the lifetime of source telemetry from the lifetime of narration. The race producer assigns one frozen `storyId`/revision before the accepted stream fans out, so commentary and overlay consume the same identity. The shared thread-safe fact ledger remains live while Qwen runs on the serial TTS worker. Immediately after generation and before audio starts, the worker atomically checks the story token:

- unchanged live identity is committed and receives a narrative lease;
- a normal relation `EXIT` before commit becomes a short result-oriented realization (one remaining Qwen call at most, never more than two calls total), with a deterministic result sentence as fallback;
- a session/run reset, relation identity mismatch, or hero-order revision mismatch invalidates the uncommitted line;
- an ordinary `EXIT` after speech starts records resolution but lets the committed narration finish;
- an authoritative hero class-position change is the only routine hard preemption. It invalidates waiting stories, interrupts the active backend process, restores ducking in `finally`, and allows the new position story to lead.

Deferred candidates remain depth-one and replace lower-or-equal priority drafts, so an old FIFO backlog is never narrated. Replaced/dropped waiters explicitly invalidate their story lease.

The TTS worker emits `building`, `committed`, `speaking`, `completed`, `interrupted` or `invalidated` transitions. Runtime marshals them with `loop.call_soon_threadsafe()` into a bounded overlay-consumer reducer; the worker never mutates `OverlayBus` or an asyncio primitive. A leased V4 card ignores ordinary source expiry, changes to a result presentation on `EXIT`, and is removed by completion/interruption/reset. Reconnect receives the reducer's authoritative `STATE_SNAPSHOT`. Unleased HUD events retain their original lifecycle and timers.

DEBUG tape commentary rows include `storyId`, `storyRevision`, `runEpoch`, `heroOrderRevision`, `correlationId` and the actual lifecycle action.

## TTS validator

`validate_utterance()` rejects lines that will sound wrong:

- empty / emoji / URL
- missing terminal `.` `!` `?` (intonation)
- stacked `!!` `??` `...`
- ALL-CAPS words (engines shout)
- digit runs of 4+
- unknown `{slots}`
- SSML that is not well-formed, or tags outside `break` / `emphasis`
- `<break time>` over 500 ms
- estimated duration / char cap
- second-person to the driver (`you` / `jsi`)
- vocative name-slot opener (`{target_name}, ...`)

## Assignments for the text model

```python
from irswitch.commentary import render_assignments
print(render_assignments())  # markdown briefs, unfilled cells only
```

Each brief includes event types, slots + examples, emotion bands, previous/next nodes, overlay tokens (do not copy as speech), and TTS limits.

## TTS

- **Windows:** SAPI synthesizes into memory, then `winmm` plays to `commentary.audio_device` only (e.g. `CABLE Input`). SuperTonic (`tts_backend=supertonic`) synthesizes on CPU (model kept in RAM, 4/2 ONNX threads) and plays the same device at native 44.1 kHz via WASAPI shared (COM initialized on the worker thread; WDM-KS endpoints are skipped). Set CABLE Input/Output to 16-bit 44100 Hz. Empty device uses the Windows default (you will hear it). 16ch tokens are skipped when a stereo match exists. Hard interrupt stops SuperTonic playback; SAPI process kill already exists on this branch.
- **Linux:** `espeak-ng` / `espeak` if installed; otherwise `null`.
- Live speak is **serialised** on one daemon worker: `ProcessTtsSink.enqueue` never blocks the race loop. At most **one waiter** sits behind the in-flight line (replace-by-priority; no deep TTS backlog). Director busy is estimate **or** `sink.is_busy()` so defer stays honest while audio/LLM generation runs (#180). With `llm_polish=true`, LAN Ollama `qwen3:4b-instruct-2507-q4_K_M` receives the compact microplan and selected facts and may use the full node budget for one or two sentences. One hard semantic rejection may retry; timeout/transport failure and exhausted validation immediately use the complete canonical fact realization. The mini-story commit gate then checks current run, hero order and source resolution before starting audio. Before generation/TTS, digit tokens and compact units are expanded to locale words (`speech_numbers.numbers_to_words`, EN/CS). The featured driver's name/nickname is mixed into he/him/his only. Duck enter/exit still uses the shared nested-safe `VolumeDucker`.
- **Browser preview** on `/commentary` uses Web Speech API (best short test on the gaming PC).

## Short test

1. Open `http://127.0.0.1:17321/commentary`
2. Click **Mluvit v prohlížeči** — you should hear the sample line
3. Click **Mluvit na serveru** — SAPI, SuperTonic, or espeak. If backend is `null`, the page says so
4. **Uložit nastavení** writes `commentary.*` via `PUT /api/config`

Server voice dropdown lists SAPI voices (`SAPI.SpVoice` `GetDescription()`) or SuperTonic presets `M1`–`M5` / `F1`–`F5` when that backend is selected.

## Config

```ini
[commentary]
enabled = false
use_hr_emotion = true
cooldown_s = 4.0
max_utterance_s = 14.0
tts_backend = auto
tts_voice =
tts_rate = 0
tts_steps = 6
audio_device =
duck_input =
duck_ratio = 0.25
duck_fade_ms = 750
decision_log_size = 32
```

`decision_log_size` is the commentary speak/skip ring (HTTP `/commentary` decisions). Watcher FSM decisions live in a separate in-memory ring (`race/watcher_log.py`, size 64, DEBUG only) and are not exposed on that snapshot.

`audio_device` empty = you hear TTS on the default headset. Set `CABLE Input` and capture `CABLE Output` in OBS (Monitor Off) for stream-only audio.

`duck_input` is the OBS source to lower while speaking (e.g. `Zvuk plochy`). Empty `duck_input` skips ducking. `duck_ratio` is the fraction of the original volume (0.25 = 25%). `duck_fade_ms` (default 750) ramps volume down before playback and back after; `0` is an instant jump. Fade-out starts as soon as the line is ready so SuperTonic can synthesize during the 750 ms ramp; playback waits until the ramp is down (`max(fade, synth)`). Overlapping lines share one ducker: the pre-duck volume is saved once and kept until fade-in **finishes**. A new line during fade-in must not re-read OBS (that stacked `duck_ratio` into silence). Shutdown/`atexit` force-restores if a fade was still in flight.

### Sector speak (M4)

Opt-in absolute sector-time commentary (Practice/Quali HUD splits stay on `event_engine.practice` / `quali_projection`):

```ini
sector_speak = false
sector_speak_max_per_lap = 1
```

| Gate | Behavior |
| --- | --- |
| `sector_speak=false` (default) | Director skips `SECTOR_SPLIT` / `SECTOR_BEST` (`sector_speak_disabled`) |
| Notability | `SECTOR_BEST` always notable; `SECTOR_SPLIT` needs emitter `notable=true` (gain ≥ 0.05 s vs session best) |
| Per-lap cap | At most `sector_speak_max_per_lap` spoken sector lines per lap (`0` = mute) |
| Graph | One `sector_split` node; `{sector}` is `S1`/`S2`/… text — not separate S1/S2/S3 nodes |
| Time | `{segment_time}` via M1 `slot_format` (`m:ss.fff`) |

Migration: new optional keys keep defaults. Existing `config.ini` stays silent until `enabled=true`.

### Session briefs (W4/H4)

Opt-in once-per-session intro / SoF / weather commentary (COMMENTARY_ONLY sidecars, like `ENTER_CAR` — not overlay HUD catalog):

```ini
session_briefs = false
```

| Gate | Behavior |
| --- | --- |
| `session_briefs=false` (default) | Director skips intro/SoF/weather envelopes (`session_briefs_disabled`) |
| `race_observer.grid_story=true` | One `QUALI_RECAP` (opener) + ParadeLaps pads; skips `SESSION_INTRO_RACE` when the quali bag exists |
| Intro | Once when `session_type` resolves to Practice / Qualify / Race |
| SoF | Once when race is active, intro already attempted, and racing roster ready (`field_size > 0`); arithmetic-mean interim (not official iRacing SoF) |
| Weather | Once after intro, preferring live snapshot (`extract_weather(..., prefer="live")`) |
| Reset | `(SubSessionID, SessionNum)` change or disconnect |
| Arbitration | At most one brief envelope per tick; if a brief speaks, `ENTER_CAR` is deferred to the next tick |

Slots bound from envelope metrics: `track`, `field_size`, `sof`, `sof_class`, `skies`, `air_temp`, `track_temp`, `wind_speed`, `precipitation` (H1/H2/H3 formatters). Slot-light variants still speak when optional fields are missing.

Migration: optional key default `false`. Requires `commentary.enabled=true` for audible output.

**Audio path (stream PC):** SAPI or SuperTonic → VB-CABLE (`audio_device = CABLE Input`) + OBS capture of `CABLE Output` (Monitor Off). That is OS/OBS routing. SuperTonic is opt-in (`tts_backend=supertonic` + extra `.[supertonic]`); `auto` stays SAPI. See product suite T0/T1 and P4 note.

## Anti-repeat + filler-tail quota (M2)

After densify, `rng.choice` alone can loop the same ~8 lines or shared Czech filler endings. Selection policy (constants in `anti_repeat.py`, not config keys):

| Constant | Default | Role |
| --- | --- | --- |
| `DEFAULT_HISTORY_SIZE` | 24 | Global ring of recently spoken normalized lines |
| `DEFAULT_TAIL_TOKENS` | 5 | Last-N tokens compared for filler endings |
| `DEFAULT_MAX_SIMILAR_TAILS` | 1 | Max similar tails allowed in the ring before deprioritize |
| `DEFAULT_TAIL_RATIO` | 0.78 | SequenceMatcher threshold for near-duplicate tails |

Algorithm in `choose_filled_line(..., history=...)`:

1. Build fully-bound candidates (leftover `{slots}` skipped).
2. Prefer lines that are **not** an exact recent match **and** whose filler tail is under quota.
3. Else prefer any non-exact recent line (even if tail is over quota).
4. Else fall back to any bound line — never hard-fail speech forever.

`CommentaryDirector` remembers each queued authored anchor and clears the ring on `reset()`. Final generated/spoken text is recorded through the TTS tape hook for quality review; it is not copied into the next model prompt.

## English + Czech content

Spoken lines live in `variants.{en|cs}.{emotion}`. With `llm_polish=false`, the director picks **one fully-bound line** from the matching bucket, with anti-repeat preference above (`rng.choice` among the preferred pool); this path stays backward-compatible. With `llm_polish=true`, the same authored pool supplies a fresh anchor and safe fallback while explicit event/context propositions supply the factual content.

| Wave | Status |
| --- | --- |
| W0–W5 EN | Complete |
| W6 CS | Complete |
| VOICE | Stream-viewer broadcast (3rd person); ~4 lines/cell (**752** lines) |
| W7 polish | Optional |

Live speak still requires `commentary.enabled=true`. Overlay HUD / Event Engine behaviour is unchanged (`in_car` is commentary-only).

## Content DB + fill plan

Filled EN+CS (viewer voice). Return point for authoring waves:  
[`docs/commentary_content_db_plan.md`](docs/commentary_content_db_plan.md)

## Product suite (next)

Test order and packages: [`docs/commentary_product_suite.md`](docs/commentary_product_suite.md)  
Live node readiness (P1): [`docs/commentary_live_node_matrix.md`](docs/commentary_live_node_matrix.md)

| Package | Status |
| --- | --- |
| T0 SAPI→VAD mock | Manual on #120 |
| T1 content after restart | This content branch |
| P1 live matrix | Doc + slot binding proofs |
| P2 why-quiet log | `GET /api/commentary/decisions` + `/commentary` panel |
| P3–P5 | Queued |
| P6 polish | Deferred |

## Session intros / SoF extraction (W4 H1)

Fail-soft SessionInfo helpers live in `irswitch.iracing.session_context`:

- `track_display_name(weekend_info)` — `WeekendInfo.TrackDisplayName`, optional `TrackConfigName` append; never speaks `TrackID` alone
- `parse_roster(driver_info)` — racing drivers only (excludes pace car, spectators, invalid `CarIdx`); missing `IsSpectator` excludes the row
- `session_key(data)` / `SessionContextCache` — cache identity `(SubSessionID, SessionNum)`, invalidate on change
- `extract_session_context(data)` — track + roster + player car/class when available

Wired in H4 via `irswitch.commentary.session_briefs.SessionBriefsDetector` (COMMENTARY_ONLY sidecars).

## SoF helper (W4 H2)

Pure arithmetic-mean interim SoF in `irswitch.iracing.sof` (`compute_sof` / `compute_sof_bundle` / `format_sof_label`). Not official iRacing SoF. H4 emits `SOF_BRIEF` once per race session when the roster is ready.

## Weather speech formatting (W4 H3)

Fail-soft helpers in `irswitch.iracing.weather` extract current vs forecast weather and produce spoken EN/CS labels for slots `skies`, `air_temp`, `track_temp`, `wind_speed`, `precipitation`.

- `extract_weather(data, prefer="live"|"session"|"forecast")` → `WeatherSnapshot` with honest `source` (`live` / `session` / `forecast` / `mixed`) and per-field `field_sources`
- Live may fall back to `WeekendInfo.Track*` (same “current” family); forecast (`WeekendOptions`) is never mixed in silently
- `format_*` / `spoken_weather_bindings` — compact slot labels (e.g. `23 C`, `4 m/s`, `partly cloudy` / CS equivalents); precip uses a small vocab and never invents rain from `Skies` alone. `numbers_to_words` expands those units to spoken words before polish/TTS.

## Session briefs wiring (W4 H4)

Graph nodes `session_intro_practice` / `session_intro_qualify` / `session_intro_race` / `sof_brief` / `weather_brief` are in `sequence_graph.json`. Overlay runtime hooks `SessionBriefsDetector` beside `InCarDetector`. Feature flag: `commentary.session_briefs` (default off).

## Tests

- `tests/test_commentary_graph.py`
- `tests/test_commentary_validator.py`
- `tests/test_commentary_assignments.py`
- `tests/test_commentary_director.py`
- `tests/test_commentary_http.py`
- `tests/test_commentary_mock.py`
- `tests/test_commentary_live_slots.py`
- `tests/test_commentary_anti_repeat.py`
- `tests/test_commentary_session_briefs.py`
- `tests/test_session_context.py`
- `tests/test_sof.py`
- `tests/test_iracing_weather.py`
