# GPT brief — irswitch commentary Wave W4

**Paste START→END into GPT.** Timing / quali / practice EN cells (30).  
Do not rewrite W1–W3 nodes (in_car, lap_complete, pits, race beats, pit_outcome).

---

## START OF PROMPT

### Role

You write short **race-engineer radio lines** for a sim-racing coach (iRacing → TTS). Speak to the driver. One breath. Intensity via word choice, never ALL-CAPS.

### This job (Wave W4 only)

Fill **English** for **9 timing / quali / practice** events. Include `neutral` and listed emotions.

**Exactly 30 cells** (1–3 lines each):

- `personal_best` — neutral, calm, focused, pushing, high  
- `gain_found` — neutral, calm, focused  
- `time_lost` — neutral, calm, focused  
- `target_locked` — neutral, calm, focused  
- `projected_lap` — neutral, focused, pushing  
- `hot_lap` — neutral, focused, pushing, high  
- `position_attack` — neutral, focused, pushing  
- `clean_streak` — neutral, calm, focused  
- `rival_threat` — neutral, focused, pushing  

### Meanings

| id | Context | Must | Must NOT |
| --- | --- | --- | --- |
| `personal_best` | New personal best lap | Brief celebrate; may use `{lap}`, `{lap_time}`, `{delta}` | Long hype; claim race win |
| `gain_found` | Practice: found time in a segment | Name the gain (`{delta}`, `{segment}`) | Race battle / overtake talk |
| `time_lost` | Practice: lost time in a segment | Calm correction | Panic / blame |
| `target_locked` | Practice target time set | `{target_time}` locked | Invent grid position |
| `projected_lap` | Quali projection | `{projected_time}`, optional `{confidence}` | Invent P1/grid claim |
| `hot_lap` | Quali flyer started / called | Short; lap `{lap}` | Mid-corner chatter |
| `position_attack` | Quali place under threat | Threat to `{position}` | Race overtake narration |
| `clean_streak` | Clean laps streak | Low urgency `{streak}` | Overhype |
| `rival_threat` | Faster car closing, not yet hunted | `{gap}` / `{target_name}` pressure building | Full hunted/defend speech |

### Slots (verbatim only)

- `personal_best`: `{lap}`, `{lap_time}`, `{delta}`  
- `gain_found` / `time_lost`: `{delta}`, `{segment}`  
- `target_locked`: `{target_time}`  
- `projected_lap`: `{projected_time}`, `{confidence}`  
- `hot_lap`: `{lap}`  
- `position_attack`: `{position}`  
- `clean_streak`: `{streak}`  
- `rival_threat`: `{gap}`, `{target_name}`  

### Hard TTS rules

End with `.!?`. ≤90 chars (prefer ≤70). No ALL-CAPS ≥4, no `!!`/`??`/`...`, no emoji/URL, no 4+ digit runs, no raw `&`. No HUD labels (“PERSONAL BEST”, etc.).

### Emotion ladder

neutral=factual · calm=quiet · focused=crisp · pushing=sharper · high=intense wording still spoken

### Good vs bad

**Good:** `New best — {lap_time}.` / `You found {delta} in {segment}.` / `Target locked at {target_time}.` / `{target_name} is closing, gap {gap}.`  
**Bad:** `PERSONAL BEST!!!` / inventing “you're on pole” on projected_lap / race pass language on gain_found

### Output

JSON only:

```json
{
  "graph_version": 1,
  "wave": "W4",
  "author_model": "gpt-…",
  "locale": "en",
  "patches": []
}
```

Exactly **30** patch objects covering every cell above.

### Self-check

30 patches? Correct emotions per node? Only allowed slots? Practice nodes not sounding like race overtakes? ≤90 chars? Then JSON only.

## END OF PROMPT

---

## Engineer notes

- After W2 unfilled=132; W3 drops 3 → 129; W4 drops 30 → 99 (EN remaining ≈ CS+leftovers)  
- Merge order: apply W3 then W4 (or either if no overlap)
