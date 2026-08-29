# Commentary engine (Phase 0)

**Status:** structure + TTS call + `/commentary` test page. Default **off** for the live race feed.  
**Branch base:** `master` (Event Engine + BLE HR already there). Independent of Pit Wall theme pack (`6611`).

## Why

Overlay copy is i18n **tokens** (`PŘEDJETÍ`), not speech. Event Engine already decides *what happened* and *who won arbitration*. Commentary sits **after** that and decides *whether to speak* and *which sequence node* to use.

Texts are filled later by another model. This repo owns the graph, validator, assignment briefs, and director.

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
- Requires `event_engine.v2_payload=true` (V4 envelopes). Legacy WS events are ignored.
- Overlay priorities stay visual. Voice has its own `speak_priority` + `commentary.cooldown_s`.
- BLE HR is optional emotion. Missing sensor → `unknown` / `neutral`. Never invent BPM.
- Fail-soft: graph load / observe errors must not break the race loop.

## Sequence graph (not Neo4j)

`src/irswitch/commentary/data/sequence_graph.json` is a **graph-shaped JSON** (nodes + edges). Stdlib only — no new database dependency.

| Field | Role |
| --- | --- |
| `nodes.*.event_types` / `phases` | Match catalog event + wire phase |
| `speak_priority` / `cooldown_s` | Voice budget (independent of `[events.priorities]`) |
| `slots` | `{position}`, `{gap}`, … bound from envelope metrics |
| `hr_states` | Which BLE bands may pick this node |
| `variants.{locale}.{emotion}` | Spoken lines — **empty in Phase 0** |
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

- **Windows:** `System.Speech.SpeechSynthesizer` via PowerShell. Text goes in `IRSWITCH_TTS_B64` (no shell quoting).
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
```

Migration: new optional section. Existing `config.ini` keeps defaults (off). No user action required.

## Later (not this PR)

- Author fills `variants` (EN + CS, per emotion)
- Windows SAPI / OBS media sink (still no new dep unless approved)
- Optional DecisionLog “why not spoken” on WS
- P0–P5 voice budget if overlay arbitration grows zones

## Tests

- `tests/test_commentary_graph.py`
- `tests/test_commentary_validator.py`
- `tests/test_commentary_assignments.py`
- `tests/test_commentary_director.py`
