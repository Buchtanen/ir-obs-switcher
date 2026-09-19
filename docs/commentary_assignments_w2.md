# GPT brief — irswitch commentary Wave W2

**Use this file as the full prompt.** Paste everything from “START OF PROMPT” to “END OF PROMPT” into GPT (ChatGPT / API).  
No repo access needed. Do not invent new events or nodes.

Return **one JSON object only**. Engineer will validate and merge into the sequence graph.

W1 is already filled (in_car / lap / pit / back_on_track). Do **not** rewrite those.

---

## START OF PROMPT

### Role

You are a **race-engineer voice writer** for a sim-racing coach (iRacing → TTS).

Speak **to the driver** (second person / implied you). Short radio calls. One breath per line.

Heart-rate selects an **emotion bucket**. Change intensity with **word choice**, never shouting or ALL-CAPS.

### This job (Wave W2 only)

Fill **English** spoken lines for **10 high-priority race events**. These cells are empty today — including `neutral`.

Write **exactly these 40 cells** (1–3 lines each):

**finish** — neutral, calm, focused, pushing, high  
**final_lap** — neutral, focused, pushing, high  
**incident** — neutral, focused, pushing, high  
**overtake** — neutral, focused, pushing, high  
**battle_won** — neutral, focused, pushing, high  
**position_gained** — neutral, calm, focused, pushing  
**position_lost** — neutral, focused, pushing, high  
**side_by_side** — neutral, pushing, high  
**hunting** — neutral, focused, pushing, high  
**hunted** — neutral, focused, pushing, high  

Do **not** invent `calm` where it is not listed. Do **not** write Czech. Do **not** touch other events.

### Story sequences (keep wording compatible)

These often fire close together on the same battle. Lines must not contradict or fully restage the previous beat.

1. `hunting` → `side_by_side` → `overtake` → `battle_won`  
2. `hunting` → `overtake` → `battle_won` (skip side-by-side)  
3. `hunted` → `position_lost`  
4. `final_lap` → `finish`

### Event meanings (critical)

| id | When | Must mean | Must NOT mean |
| --- | --- | --- | --- |
| `hunting` | Closing on a car ahead (enter only) | You are attacking / approaching `{target_name}` | Already passed them; gap spam every tick |
| `hunted` | Someone closing from behind | You are under pressure from `{target_name}` | You already lost the place |
| `side_by_side` | Door-to-door / fight for place | Fight is live with `{target_name}` | The pass is already done |
| `overtake` | Accepted **on-track pass** | You took the place (past tense), now `{position}` | Car ahead pitted; soft “positions moved” |
| `battle_won` | Battle story closed after a pass | You secured it / hold `{position}` | Restage the overtake move |
| `position_gained` | Place improved **without** calling overtake | You are now `{position}` (was `{old_position}`) | Invent a pass / “you dove up the inside” |
| `position_lost` | Place dropped / overtaken | You are now `{position}` (was `{old_position}`) | Long blame speech |
| `incident` | Incident / contact flash | Something happened; short reset | Blame, insults, rules lecture |
| `final_lap` | Last lap starts | One lap left; you are `{position}` | Race already finished |
| `finish` | Chequered / session end | Race/session over; finished `{position}` | More race chatter after |

### Voice guide

Calm pit-wall coach. Neutral international English. No memes, no sponsor reads, no broadcast hype paragraphs.

| Emotion | Feel | Tips |
| --- | --- | --- |
| `neutral` | Baseline / no usable HR | Clear, even, factual |
| `calm` | Quiet | soft, settled, easy |
| `focused` | Crisp | clean, sharp, lock in |
| `pushing` | Sharper | dig in, keep after it, push |
| `high` | Intense wording, still spoken | now, come on — never ALL-CAPS |

Within one event, emotion variants should sound different when read aloud, but keep the same facts.

### Hard TTS rules (auto-validator)

Every line must:

1. Be non-empty.  
2. End with `.` `!` or `?`.  
3. Be **≤ 90 characters** (count the stored string, including `{slots}`). Prefer **≤ 70**.  
4. Fit roughly **≤ 5.5s** speech.  
5. No ALL-CAPS word of 4+ letters (`OVERTAKE`, `YES`, `PIT` fail).  
6. No `!!` `??` `...` ellipsis.  
7. No emoji, URLs, digit runs of 4+ (`2024` fails).  
8. No raw `&` (write `and`).  
9. Prefer plain text. Optional SSML only: `<break time="200ms"/>` (≤500ms), `<emphasis level="moderate">…</emphasis>`.  
10. Use **only** the slots listed for that event, copied exactly.  
11. Never speak HUD labels like “OVERTAKE”, “FINAL LAP”, “INCIDENT”.

### Slot reference

Use these tokens **verbatim** when you include them. Mix slotted and unslotted lines for variety.

- `hunting`: `{gap}` (e.g. 1.2), `{target_name}` (e.g. Rossi), `{position}` (e.g. 6)  
- `hunted`: `{gap}`, `{target_name}`, `{position}`  
- `side_by_side`: `{position}`, `{target_name}`  
- `overtake`: `{position}`, `{target_name}`  
- `battle_won`: `{position}`  
- `position_gained`: `{position}`, `{old_position}`  
- `position_lost`: `{position}`, `{old_position}`  
- `incident`: `{value}` (incident count / severity int — do not dramatize the number)  
- `final_lap`: `{position}`  
- `finish`: `{position}`  

Unknown tokens like `{gap_s}`, `{name}`, `{driver}` are forbidden.

### Good vs bad

**Good**

- `You're onto {target_name}, gap {gap}.`  
- `Side by side with {target_name}.`  
- `You take {position} from {target_name}.`  
- `That's yours. Hold {position}.`  
- `Up to {position} — they boxed.`  
- `Down to {position}. Stay calm.`  
- `Incident. Reset and breathe.`  
- `Last lap. You're {position}.`  
- `That's the flag. Finished {position}.`

**Bad**

- `YOU PASS HIM NOW!!!` → caps + stacked punct  
- `Overtake complete...` → ellipsis + HUD word vibe  
- `You divebomb {target_name} like a legend 🔥` → emoji / meme  
- On `position_gained`: `You overtook {target_name}.` → wrong event meaning  
- On `battle_won`: full restage of the pass already spoken on `overtake`  
- On `finish`: `Great race, see you next week at Spa 2024.` → digit run + extra chatter  

### Output format (mandatory)

Return **only** one JSON object. No markdown fences. No prose before/after.

```json
{
  "graph_version": 1,
  "wave": "W2",
  "author_model": "gpt-…",
  "locale": "en",
  "patches": [
    {
      "node_id": "finish",
      "locale": "en",
      "emotion": "neutral",
      "lines": [
        "That's the flag. Finished {position}.",
        "Session over. You finish {position}."
      ]
    }
  ]
}
```

`patches` must contain **exactly 40** objects covering every cell listed above.  
Each `lines`: **1–3** strings.  
`author_model`: your model id (e.g. `gpt-5`).  
`graph_version`: `1`.

### Self-check

1. patches count = 40?  
2. Every required emotion present; no extra emotions?  
3. Every line ends with `.` `!` or `?`?  
4. No ALL-CAPS ≥4, no `...`/`!!`, no emoji/URL/`&`?  
5. Only allowed `{slots}` per node?  
6. `overtake` ≠ `position_gained` meaning?  
7. `battle_won` does not restage the pass?  
8. `final_lap` still racing; `finish` is past/closed?  
9. Sequence-compatible across hunting → … → battle_won?  
10. Each string ≤ 90 chars?

Then output the JSON only.

## END OF PROMPT

---

## Engineer notes (do not paste to GPT)

- Plan: `docs/commentary_content_db_plan.md` — Wave W2  
- Expected unfilled drop: **40** (172 → 132 if only these EN cells fill)  
- Merge into `nodes.*.variants.en.*`; do not touch W1 mock-4 neutrals/emotions  
- Validate with `validate_utterance` + example slot bind before commit  
- Prefer PR/test update asserting director speaks for `OVERTAKE` / `FINISH` with filled neutral
