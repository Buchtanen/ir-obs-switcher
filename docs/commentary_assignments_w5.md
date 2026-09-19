# GPT brief — irswitch commentary Wave W5

**Paste START→END into GPT.** Last **English** structure cells: bio + invalid lap (5 cells).  
Do not rewrite earlier waves.

---

## START OF PROMPT

### Role

You write short **race-engineer radio lines** for a sim-racing coach (iRacing → TTS). Speak to the driver. One breath. Intensity via word choice, never ALL-CAPS.

### This job (Wave W5)

Fill **English** for the last empty EN nodes:

**Exactly 5 cells** (1–3 lines each):

1. `hr_pressure` / en / pushing  
2. `hr_pressure` / en / high  
3. `invalid_lap` / en / neutral  
4. `invalid_lap` / en / calm  
5. `invalid_lap` / en / focused  

No other emotions/nodes. No Czech.

### Meanings

| id | When | Must | Must NOT |
| --- | --- | --- | --- |
| `hr_pressure` | BLE HR rising into push/high (rare spoken bio line) | Acknowledge pressure / rising effort; may use `{bpm}` | Invent BPM if unknown — only use `{bpm}` when natural; no medical alarm drama; no battle restage |
| `invalid_lap` | Practice/quali lap invalidated | Calm reset; optional `{lap}` | Blame, panic, race-overtake talk |

### Slots

- `hr_pressure`: `{bpm}` (int, e.g. 142) — optional on some lines  
- `invalid_lap`: `{lap}` (int, e.g. 4) — optional on some lines  

### Hard TTS rules

End with `.!?`. ≤90 chars (prefer ≤70). No ALL-CAPS ≥4, no `!!`/`??`/`...`, no emoji/URL, no 4+ digit runs, no raw `&`. No HUD labels.

### Good vs bad

**Good:** `Heart rate climbing, {bpm}. Steady the breath.` / `Lap {lap} is invalid. Reset and go again.`  
**Bad:** `HR CRITICAL 180!!!!` / medical panic / “you crashed like an idiot”

### Output

JSON only:

```json
{
  "graph_version": 1,
  "wave": "W5",
  "author_model": "gpt-…",
  "locale": "en",
  "patches": []
}
```

Exactly **5** patch objects.

### Self-check

5 patches? Correct emotions? Allowed slots only? Then JSON only.

## END OF PROMPT
