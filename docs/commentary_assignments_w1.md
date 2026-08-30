# Commentary text assignments — Wave W1

**Wave:** W1 — EN emotions on mock-4 (`in_car`, `lap_complete`, `pit_entry`, `back_on_track`).
**Goal:** Prove the emotion matrix without new events. Keep existing EN `neutral` mock lines; fill other emotion buckets.
**Locale:** `en` only.

Fill spoken variants only. Do not change node ids, slots, edges, or TTS limits.
Each line must pass `validate_utterance` (terminal punctuation, no ALL-CAPS,
no stacked !!/??/..., limited SSML: break + emphasis).

Graph version: 1.

## System rules (for the text model)

You fill spoken race-commentary variants for irswitch.
Output: ONLY a JSON object matching the delivery schema below.
Rules:
- Fill spoken variants only. Never change node ids, slots, edges, or TTS limits.
- Locale: en. Emotions: only those listed under each node (do not rewrite `neutral` unless asked).
- 1–3 lines per emotion cell. Second person or implied driver. One breath.
- Use slot tokens verbatim, e.g. `{lap}`, `{lap_time}`, `{position}`.
- Terminal punctuation required: `.` `!` or `?`.
- Forbidden: ALL-CAPS words, stacked !!/??/..., emoji, URLs, digit runs of 4+.
- SSML only if needed: `<break time="…ms"/>` (≤500ms) and `<emphasis>…</emphasis>`.
- Overlay HUD tokens are visual only — do not speak them as labels.
- Intensity from word choice per emotion, not shouting.
- Pit entry ≠ getting into the car; in-car ≠ pit; back_on_track = leaving pit road.

## Delivery schema

```json
{
  "graph_version": 1,
  "wave": "W1",
  "author_model": "<model-or-human>",
  "patches": [
    {
      "node_id": "in_car",
      "locale": "en",
      "emotion": "calm",
      "lines": ["Belted in and settled.", "Quiet and ready."]
    }
  ]
}
```

## Existing EN neutral (do not replace in this wave — keep as fallback)

### `in_car` neutral (8 lines)
- In the car.
- Belted in.
- Ready to go.
- Seats in.
- Let's go to work.
- We're in.
- Strapped in.
- Car is live.

### `lap_complete` neutral (4 lines)
- Lap complete.
- That's a lap.
- Another lap done.
- Lap in the books.

### `pit_entry` neutral (4 lines)
- In the pits.
- Coming in.
- Box this time.
- Down the pit lane.

### `back_on_track` neutral (4 lines)
- Back on track.
- Out of the pits.
- Rolling again.
- We're back out.

## Cells to fill

## `in_car` — en / calm, focused, pushing, high

- family: `session`
- event types: ENTER_CAR
- phases: RESULT, ENTER
- speak_priority: 38 (voice budget; overlay priorities stay separate)
- cooldown_s: 45.0
- TTS: max 90 chars, 5.5s, SSML break, emphasis
- sequence: previous (start) → next (end)

### Slots
- (no slots)

### Emotion variants to write
- **calm**: HR delta in calm band. Quiet, economical line.
- **focused**: HR in focused band. Crisp, still controlled.
- **pushing**: HR in pushing band. Sharper rhythm, still one sentence.
- **high**: HR in high band. Intensity in wording, not volume. No ALL-CAPS.

### Overlay tokens (visual only — do not copy as speech)
- `session.final_lap` → FINAL LAP
- `session.finish` → FINISH

### Author notes
Mock EN matrix. Seated in-car once per stint. Random pick. Not pit entry.

### Deliver
1–3 spoken sentences per emotion. Second person or implied driver.
Use slots verbatim (`{position}`). One breath. Terminal `.` `!` or `?`.

## `lap_complete` — en / calm, focused, pushing, high

- family: `timing`
- event types: LAP_COMPLETE
- phases: RESULT
- speak_priority: 40 (voice budget; overlay priorities stay separate)
- cooldown_s: 8.0
- TTS: max 90 chars, 5.5s, SSML break, emphasis
- sequence: previous (start) → next (end)

### Slots
- `{lap}` (int) example: 12
- `{lap_time}` (time) example: 1:32.4

### Emotion variants to write
- **calm**: HR delta in calm band. Quiet, economical line.
- **focused**: HR in focused band. Crisp, still controlled.
- **pushing**: HR in pushing band. Sharper rhythm, still one sentence.
- **high**: HR in high band. Intensity in wording, not volume. No ALL-CAPS.

### Overlay tokens (visual only — do not copy as speech)
- `lap.complete` → LAP COMPLETE
- `lap.personal_best` → PERSONAL BEST

### Author notes
Mock EN until the text model fills variants. Generic lap line; do not read tenths.

### Deliver
1–3 spoken sentences per emotion. Second person or implied driver.
Use slots verbatim (`{position}`). One breath. Terminal `.` `!` or `?`.

## `pit_entry` — en / calm, focused

- family: `pit`
- event types: PIT_ENTRY
- phases: ENTER, RESULT
- speak_priority: 55 (voice budget; overlay priorities stay separate)
- cooldown_s: 20.0
- TTS: max 90 chars, 5.5s, SSML break, emphasis
- sequence: previous (start) → next back_on_track, pit_outcome

### Slots
- `{position}` (int) example: 8

### Emotion variants to write
- **calm**: HR delta in calm band. Quiet, economical line.
- **focused**: HR in focused band. Crisp, still controlled.

### Overlay tokens (visual only — do not copy as speech)
- `pit.entry` → PIT ENTRY
- `pit.exit` → PIT EXIT
- `pit.outcome` → PIT OUTCOME

### Author notes
Mock EN. Pit-road entry only — not getting into the car.

### Deliver
1–3 spoken sentences per emotion. Second person or implied driver.
Use slots verbatim (`{position}`). One breath. Terminal `.` `!` or `?`.

## `back_on_track` — en / calm, focused

- family: `pit`
- event types: PIT_EXIT
- phases: RESULT, ENTER, EXIT
- speak_priority: 62 (voice budget; overlay priorities stay separate)
- cooldown_s: 16.0
- TTS: max 90 chars, 5.5s, SSML break, emphasis
- sequence: previous pit_entry → next (end)

### Slots
- `{position}` (int) example: 11

### Emotion variants to write
- **calm**: HR delta in calm band. Quiet, economical line.
- **focused**: HR in focused band. Crisp, still controlled.

### Overlay tokens (visual only — do not copy as speech)
- `pit.entry` → PIT ENTRY
- `pit.exit` → PIT EXIT
- `pit.outcome` → PIT OUTCOME

### Author notes
Mock EN. Leaving pit road, back on track. Not a car-entry line.

### Deliver
1–3 spoken sentences per emotion. Second person or implied driver.
Use slots verbatim (`{position}`). One breath. Terminal `.` `!` or `?`.
