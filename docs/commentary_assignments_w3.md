# GPT brief — irswitch commentary Wave W3

**Paste START→END into GPT.** Tiny wave: only `pit_outcome` (3 EN cells).  
W1 already filled `pit_entry` / `back_on_track` / `in_car` — do **not** rewrite them.

---

## START OF PROMPT

### Role

You write short **race-engineer radio lines** for a sim-racing coach (iRacing → TTS). Speak to the driver. One breath. Intensity via word choice, never ALL-CAPS or shouting.

### This job (Wave W3 only)

Fill **English** lines for **one** event: pit stop **outcome** after a box (net position change when known).

Write **exactly these 3 cells** (1–3 lines each):

1. `pit_outcome` / en / neutral  
2. `pit_outcome` / en / calm  
3. `pit_outcome` / en / focused  

No pushing/high for this node. No Czech. No other nodes.

### Meaning

| id | When | Must mean | Must NOT |
| --- | --- | --- | --- |
| `pit_outcome` | After pit service / correlated with pit entry | Net result of the stop: now `{position}`, was `{old_position}` if useful | “Getting into the car”; restaging pit-lane entry; claiming an on-track overtake |

Sequence context: often follows `pit_entry` on the same story. `back_on_track` may already have said “out of the pits” — this line is about **place gained/lost in the box**, not the exit itself.

### Slots

- `{position}` (int, e.g. 11) — current place after the stop  
- `{old_position}` (int, e.g. 8) — place before the stop  

Mix slotted and unslotted lines. If both slots appear, the net change should make sense (up or down). Do not invent `{target_name}` or `{gap}`.

### Hard TTS rules

1. End with `.` `!` or `?`  
2. ≤ 90 chars (prefer ≤ 70)  
3. No ALL-CAPS word ≥4 letters, no `!!`/`??`/`...`, no emoji/URL, no digit runs of 4+, no raw `&`  
4. Prefer plain text  
5. Never say HUD labels like “PIT OUTCOME”

### Good vs bad

**Good:** `Stop done. You're {position}.` / `Out of the box — {old_position} to {position}.` / `Service complete. Settle into {position}.`  
**Bad:** `Belted in after the stop.` (car-entry) / `You overtook them in the pits!!!` (wrong + caps/punct)

### Output

JSON only. No markdown fences. No prose.

```json
{
  "graph_version": 1,
  "wave": "W3",
  "author_model": "gpt-…",
  "locale": "en",
  "patches": [
    {
      "node_id": "pit_outcome",
      "locale": "en",
      "emotion": "neutral",
      "lines": ["Stop done. You're {position}."]
    }
  ]
}
```

Exactly **3** patch objects. `graph_version`: 1.

### Self-check

patches=3? emotions exactly neutral/calm/focused? slots only position/old_position? not in-car wording? ≤90 chars? Then JSON only.

## END OF PROMPT
