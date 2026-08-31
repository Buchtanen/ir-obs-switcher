# Commentary engine (Phase 0)

**Status:** structure + TTS + `/commentary` test page + **English mock lines** on four events. Default **off** for the live race feed.  
**Branch base:** `master`. Mock texts are placeholders until another model fills the graph.

## Why

Overlay copy is i18n **tokens** (`PŘEDJETÍ`), not speech. Event Engine already decides *what happened* and *who won arbitration*. Commentary sits **after** that and decides *whether to speak* and *which sequence node* to use.

Texts are filled later by another model. This repo owns the graph, validator, assignment briefs, and director.

## Voice (viewer-facing)

Commentary is **for the stream audience**, not pit-wall radio to the driver.

- EN: third person / broadcast, mixing the driver's name or nickname with he/him/his (“Richard is closing on Rossi.” / “That's a lap for Buchtanen.”)
- CS: třetí osoba / komentář pro diváky, jméno nebo přezdívka namíchaná s zájmeny (“Richard uzavírá kolo.” / “Buchtanen. Kolo je hotové.”)
- Never second person to the driver (“You take P5”, “Jsi pátý” as address)
- Light viewer asides OK; keep one breath; slots unchanged

## Pipeline

```text
iRacing / BLE HR
    → EventEngine emitters → CandidateEvent
    → EventManager / V2 (priority, cooldown, pit guard)
    → accepted EventEnvelope
    → CommentaryDirector (sequence graph + HR emotion)
    → validate_utterance
    → TtsSink (Windows SAPI / espeak-ng / NullTtsSink)
```

**Experiment (wired, default off):** optional remote LLM *skeleton polish* (style only, facts from app) — see [docs/commentary_llm_skeleton_poc.md](docs/commentary_llm_skeleton_poc.md). Live serve stays A1000 Ollama `qwen2.5:3b`.

Rules:

- Hook **accepted envelopes only**. Raw candidates are too noisy.
- Works with **legacy** EventManager (`v2_payload=false`, default) via a speech map for `lap_complete` / `pit_entry` / `pit_exit`. V2 envelopes are used when present; the map fills gaps (basic pit has no V2 adapter).
- `in_car` is a commentary sidecar (`player_car_idx` rising, event type `ENTER_CAR`). It is **not** an overlay HUD catalog entry and is **not** pit entry.
- Session intros / SoF / weather are commentary sidecars (`SessionBriefsDetector`, gated by `commentary.session_briefs`). They are **not** overlay HUD catalog entries.
- `STREAM_START` is a commentary-only envelope from the OBS streaming rising edge (`commentary.stream_start`, default off). Graph node `stream_start` is a long slot-free welcome (`tts.max_seconds` ≥ 15); the process timeout uses that node cap so `commentary.max_utterance_s` (default 6) stays unchanged. An **opener mutex** (120 s) plus director `_busy_until` lets at most one of stream start / in-car / session intro / preview speak.
- Mode-specific `in_car_practice` / `in_car_qualify` / `in_car_race` nodes outrank generic `in_car` when `envelope.mode` matches. Generic `in_car` remains for warmup until those lines migrate.
- Gap-hunt TTS (`HUNTING` / `HUNTED`) is off in practice/qualifying unless `commentary.gap_hunt_tts_in_practice` / `gap_hunt_tts_in_qualifying` is on. HUD hunting is unchanged. Race still speaks.
- P/Q hunt-by-time is COMMENTARY_ONLY `PACE_HUNT` (`race/timing_hunt.py`): hero projected/best vs `CarIdxBestLapTime` of class P{n}. Unset times → silence. Quali HUD `position_attack` remains hero own PB.
- `INCIDENT` `metrics.branch` is `off_track` or `unknown` only when `race_observer.incident_classify` is on (default off). Nearby cars are metrics, not spoken kinds. Same tick: speak at most one of engine `INCIDENT` (delta ≥ `incident_min_delta` default 2) and derived `INCIDENT_AFTERMATH` (any rise); INCIDENT wins. Aftermath classify is surface-first (off-track stays stalled even if Speed > 0). Speed is motion for on-track stalled/rolling and `BACK_UNDER_WAY`. No `INCIDENT_RECOVERED`.
- Overlay priorities stay visual. Voice has its own `speak_priority` + `commentary.cooldown_s`.
- BLE HR is optional emotion. Missing sensor → `unknown` / `neutral`. Empty emotion cells fall back to `neutral` (mock stays audible with HR connected).
- Fail-soft: graph load / observe errors must not break the race loop.

## Sequence graph (not Neo4j)

`src/irswitch/commentary/data/sequence_graph.json` is a **graph-shaped JSON** (nodes + edges). Stdlib only — no new database dependency.

| Field | Role |
| --- | --- |
| `nodes.*.event_types` / `phases` | Match catalog event + wire phase |
| `nodes.*.modes` | Optional. `practice` / `qualify` / `race` / `warmup`. Empty = all sessions. Envelope `PRACTICE`/`QUALIFYING`/`RACE`/`GENERIC` map onto those tokens. |
| `nodes.*.branch` | Optional. Matches `envelope.metrics.branch` (e.g. `off_track`). Missing branch = generic fallback. |
| `speak_priority` / `cooldown_s` | Voice budget (independent of `[events.priorities]`). After mode/branch filter, highest `speak_priority` wins. `_follow_edge` runs **only on the filtered set**. |
| `slots` | `{position}`, `{gap}`, … bound from envelope metrics. Timing slots (`lap_time`, `gap`, `delta`, `segment_time`, `target_time`, `projected_time`) are spoken via `sdk_units`-style formatters in `slot_format.py`; sentinel / invalid values leave the slot unbound so that candidate line is skipped (re-draw). |
| `hr_states` | Which BLE bands may pick this node |
| `variants.{locale}.{emotion}` | Spoken lines. EN mock filled on `in_car`, `lap_complete`, `pit_entry`, `back_on_track`. CS empty (falls back to EN). |
| `edges` | Preferred next line (e.g. hunting → side_by_side → overtake) |

Visual-only catalog events (`CPU_TEMP_HIGH`, `LINK_DROP`, `BLE_LOST`, gap `UPDATE`s) are **not** in the speak graph.

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

## Assignments for the text model

```python
from irswitch.commentary import render_assignments
print(render_assignments())  # markdown briefs, unfilled cells only
```

Each brief includes event types, slots + examples, emotion bands, previous/next nodes, overlay tokens (do not copy as speech), and TTS limits.

## TTS

- **Windows:** SAPI synthesizes into memory, then `winmm` plays to `commentary.audio_device` only (e.g. `CABLE Input`). Empty device uses the Windows default (you will hear it). 16ch tokens are skipped when a stereo match exists.
- **Linux:** `espeak-ng` / `espeak` if installed; otherwise `null`.
- Live speak is **serialised** on one daemon worker: `ProcessTtsSink.enqueue` never blocks the race loop. At most **one waiter** behind the in-flight line (replace-by-priority; no deep TTS backlog). Director busy is estimate **or** `sink.is_busy()` so defer stays honest while audio/LLM polish runs (#180). Optional LLM polish restyles the authored skeleton at **similar length** (same sentence count, skeleton-relative char cap) on LAN Ollama `qwen2.5:3b` (RTX A1000). A 4090 is optional later fine-tune only, not a second live model. A second invented sentence, `Welcome back` / `Stay tuned`, second-person to the driver (`you`/`jsi`), or a fact-lock hit (invented lead/pole, chase→lead, West→westward, seconds→cm) retries the **same skeleton** up to `llm_max_attempts` inside `llm_timeout_s` — it does not re-walk the sequence graph. If every attempt fails → `retry_exhausted` and **TTS is skipped** (skeleton is not spoken). Node TTS (~160 chars / 13 s) is the authored ceiling, not a dump budget. Before polish/TTS, digit tokens **and compact units** (`m/s`, `°C`/`23 C`, gap `s`, `%`, `bpm`) are expanded to locale words (`speech_numbers.numbers_to_words`, EN/CS). The featured driver's name/nickname is mixed into he/him/his (`speech_hero.mix_hero_name`; config `driver_name` / `driver_nickname`, else iRacing UserName) — EN prefix `Name.` is skipped when the line already names another person. Duck enter/exit still uses the shared nested-safe `VolumeDucker`.
- **Browser preview** on `/commentary` uses Web Speech API (best short test on the gaming PC).

## Short test

1. Open `http://127.0.0.1:17321/commentary`
2. Click **Mluvit v prohlížeči** — you should hear the sample line
3. Click **Mluvit na serveru** — Windows SAPI (or espeak). If backend is `null`, the page says so
4. **Uložit nastavení** writes `commentary.*` via `PUT /api/config`

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
audio_device =
duck_input =
duck_ratio = 0.25
duck_fade_ms = 750
decision_log_size = 32
```

`audio_device` empty = you hear SAPI on the default headset. Set `CABLE Input` and capture `CABLE Output` in OBS (Monitor Off) for stream-only audio.

`duck_input` is the OBS source to lower while speaking (e.g. `Zvuk plochy`). Empty `duck_input` skips ducking. `duck_ratio` is the fraction of the original volume (0.25 = 25%). `duck_fade_ms` (default 750) ramps volume down before the line and back after; `0` is an instant jump. Overlapping lines share one ducker: the pre-duck volume is saved once and kept until fade-in **finishes**. A new line during fade-in must not re-read OBS (that stacked `duck_ratio` into silence). Shutdown/`atexit` force-restores if a fade was still in flight.

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
| Intro | Once when `session_type` resolves to Practice / Qualify / Race |
| SoF | Once when race is active, intro already attempted, and racing roster ready (`field_size > 0`); arithmetic-mean interim (not official iRacing SoF) |
| Weather | Once after intro, preferring live snapshot (`extract_weather(..., prefer="live")`) |
| Reset | `(SubSessionID, SessionNum)` change or disconnect |
| Arbitration | At most one brief envelope per tick; if a brief speaks, `ENTER_CAR` is deferred to the next tick |

Slots bound from envelope metrics: `track`, `field_size`, `sof`, `sof_class`, `skies`, `air_temp`, `track_temp`, `wind_speed`, `precipitation` (H1/H2/H3 formatters). Slot-light variants still speak when optional fields are missing.

Migration: optional key default `false`. Requires `commentary.enabled=true` for audible output.

**Audio path (stream PC):** SAPI → VB-CABLE (`audio_device = CABLE Input`) + OBS capture of `CABLE Output` (Monitor Off). That is OS/OBS routing; code sink stays `sapi`/`espeak`/`null`. See product suite T0/T1 and P4 note.

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

`CommentaryDirector` remembers each spoken line and clears the ring on `reset()`.

## English + Czech content

Spoken lines live in `variants.{en|cs}.{emotion}`. The director picks **one fully-bound line** from the matching bucket, with anti-repeat preference above (`rng.choice` among the preferred pool). Empty cells fall back `emotion→neutral` then `locale→en`.

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
