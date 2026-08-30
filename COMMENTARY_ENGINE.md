# Commentary engine (Phase 0)

**Status:** structure + TTS + `/commentary` test page + **English mock lines** on four events. Default **off** for the live race feed.  
**Branch base:** `master`. Mock texts are placeholders until another model fills the graph.

## Why

Overlay copy is i18n **tokens** (`PŘEDJETÍ`), not speech. Event Engine already decides *what happened* and *who won arbitration*. Commentary sits **after** that and decides *whether to speak* and *which sequence node* to use.

Texts are filled later by another model. This repo owns the graph, validator, assignment briefs, and director.

## Voice (viewer-facing)

Commentary is **for the stream audience**, not pit-wall radio to the driver.

- EN: third person / broadcast (“He's closing on Rossi.” / “That's P5.”)
- CS: třetí osoba / komentář pro diváky (“Dotahuje na Rossiho.” / “Bere páté místo.”)
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

Rules:

- Hook **accepted envelopes only**. Raw candidates are too noisy.
- Works with **legacy** EventManager (`v2_payload=false`, default) via a speech map for `lap_complete` / `pit_entry` / `pit_exit`. V2 envelopes are used when present; the map fills gaps (basic pit has no V2 adapter).
- `in_car` is a commentary sidecar (`player_car_idx` rising, event type `ENTER_CAR`). It is **not** an overlay HUD catalog entry and is **not** pit entry.
- Overlay priorities stay visual. Voice has its own `speak_priority` + `commentary.cooldown_s`.
- BLE HR is optional emotion. Missing sensor → `unknown` / `neutral`. Empty emotion cells fall back to `neutral` (mock stays audible with HR connected).
- Fail-soft: graph load / observe errors must not break the race loop.

## Sequence graph (not Neo4j)

`src/irswitch/commentary/data/sequence_graph.json` is a **graph-shaped JSON** (nodes + edges). Stdlib only — no new database dependency.

| Field | Role |
| --- | --- |
| `nodes.*.event_types` / `phases` | Match catalog event + wire phase |
| `speak_priority` / `cooldown_s` | Voice budget (independent of `[events.priorities]`) |
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
- **Linux:** `espeak-ng` / `espeak` if installed; otherwise `null`.
- Speak runs in a worker thread / executor. The race loop only enqueues.
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
max_utterance_s = 6.0
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

Migration: new optional keys keep defaults. Existing `config.ini` stays silent until `enabled=true`.

**Audio path (stream PC):** SAPI → VB-CABLE (`audio_device = CABLE Input`) + OBS capture of `CABLE Output` (Monitor Off). That is OS/OBS routing; code sink stays `sapi`/`espeak`/`null`. See product suite T0/T1 and P4 note.

## Anti-repeat + filler-tail quota (M2)

After densify, `rng.choice` alone can loop the same ~8 lines or shared Czech filler endings. Selection policy (constants in `anti_repeat.py`, not config keys):

| Constant | Default | Role |
| --- | --- | --- |
| `DEFAULT_HISTORY_SIZE` | 16 | Global ring of recently spoken normalized lines |
| `DEFAULT_TAIL_TOKENS` | 4 | Last *N* tokens compared for shared filler tails |
| `DEFAULT_MAX_SIMILAR_TAILS` | 2 | Cap similar tails inside the ring before deprioritize |
| `DEFAULT_TAIL_RATIO` | 0.82 | `SequenceMatcher` threshold for near-duplicate tails |

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

## Tests

- `tests/test_commentary_graph.py`
- `tests/test_commentary_validator.py`
- `tests/test_commentary_assignments.py`
- `tests/test_commentary_director.py`
- `tests/test_commentary_http.py`
- `tests/test_commentary_mock.py`
- `tests/test_commentary_live_slots.py`
- `tests/test_commentary_anti_repeat.py`
