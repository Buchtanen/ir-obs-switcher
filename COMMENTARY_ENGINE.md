# Commentary engine (Phase 0)

**Status:** structure + TTS + `/commentary` test page + dense EN/CS viewer commentary on 26 events. Default **off** for the live race feed.
**Runtime base:** `master`; content baseline and expansion are documented in [`docs/commentary_extension_report.md`](docs/commentary_extension_report.md).

## Why

Overlay copy is i18n **tokens** (`PŘEDJETÍ`), not speech. Event Engine already decides *what happened* and *who won arbitration*. Commentary sits **after** that and decides *whether to speak* and *which sequence node* to use.

This repo owns the graph, validator, assignment briefs, authored text, and director.

## Voice contract (viewer-facing)

Commentary is for the stream audience, not pit-wall radio to the driver.

- EN uses third-person broadcast language: “He's closing on Rossi.” / “That's P5.”
- CS uses third-person viewer commentary: “Dotahuje na Rossiho.” / “Bere páté místo.”
- Never address the driver in second person: no “You take P5” or “Jsi pátý.”
- Light viewer asides are allowed; each line stays within one breath and existing slots keep their meaning.
- HR intensity comes from word choice and cadence, not ALL-CAPS or stacked punctuation.

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
- BLE HR is optional emotion. Missing sensor → `unknown` / `neutral`. Empty emotion cells fall back to `neutral`.
- Fail-soft: graph load / observe errors must not break the race loop.

## Sequence graph (not Neo4j)

`src/irswitch/commentary/data/sequence_graph.json` is a **graph-shaped JSON** (nodes + edges). Stdlib only — no new database dependency.

| Field | Role |
| --- | --- |
| `nodes.*.event_types` / `phases` | Match catalog event + wire phase |
| `speak_priority` / `cooldown_s` | Voice budget (independent of `[events.priorities]`) |
| `slots` | `{position}`, `{gap}`, … bound from envelope metrics |
| `hr_states` | Which BLE bands may pick this node |
| `variants.{locale}.{emotion}` | Spoken EN+CS lines. Every active cell has 12 variants; priority cells have 16. |
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
```

`audio_device` empty = you hear SAPI on the default headset. Set `CABLE Input` and capture `CABLE Output` in OBS (Monitor Off) for stream-only audio.

`duck_input` is the OBS source to lower while speaking (e.g. `Zvuk plochy`). Empty `duck_input` skips ducking. `duck_ratio` is the fraction of the original volume (0.25 = 25%). `duck_fade_ms` (default 750) ramps volume down before the line and back after; `0` is an instant jump. Overlapping lines share one ducker: volume is saved once, not stacked, and restored after the last line.

Migration: new optional section. Existing `config.ini` keeps defaults (off). No user action required.

## English + Czech content

The director picks one random fully bound line from the current locale and emotion bucket (`rng.choice`). The active graph contains 2,760 lines across 188 cells:

- 16 lines per priority lap, battle, position, pit, in-car, final-lap, and finish cell;
- 12 lines per other active cell;
- 37.5% name-free fallback coverage on battle/position nodes that declare `{target_name}`;
- factual, pace/pressure, opponent, viewer-aside, sequence-bridge, HR, and slot-light layers.

The expansion lowers repeat probability but does not provide a hard anti-repeat guarantee. A bounded history in `CommentaryDirector` remains an explicit engineering option.

Live speak still requires `commentary.enabled=true`. Overlay HUD / Event Engine behaviour is unchanged (`in_car` is commentary-only).

## Proposed session, SoF, and weather content

Five proposed nodes and nine proposed slots are kept outside the active graph in [`docs/commentary_extension_proposals.json`](docs/commentary_extension_proposals.json). Their runtime extraction, emitters, bindings, product decisions, and tests are specified in [`docs/commentary_extension_handover.md`](docs/commentary_extension_handover.md). They remain `needs-engineering`; no topology or wiring changes are implied by the proposal.

## Tests

- `tests/test_commentary_graph.py`
- `tests/test_commentary_validator.py`
- `tests/test_commentary_assignments.py`
- `tests/test_commentary_director.py`
- `tests/test_commentary_mock.py`
- `tests/test_commentary_content_extension.py`
