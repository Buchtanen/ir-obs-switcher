# GPT brief — irswitch commentary Wave W6a (CS mock/pit)

**Paste START→END into GPT.** Czech parity for in_car / lap / pit family (19 cells).
EN is already filled — included as meaning reference only.

---

## START OF PROMPT

### Role

Jsi autor **českých** radio-komentářů závodního inženýra pro simracing (iRacing → TTS).
Mluvíš **na jezdce** (tykání). Krátké, přirozené mluvené věty. Jedna výdechová věta.
Intenzita emocí je ve volbě slov, ne v křičení / CAPS.

### Tato úloha (Wave W6a)

Doplň **pouze češtinu (`cs`)** pro 5 eventů (mock/pit). Angličtina už existuje — slouží jen jako významová reference.

Napiš **přesně těchto 19 buněk** (1–3 řádky každá):

1. `in_car` / cs / neutral
2. `in_car` / cs / calm
3. `in_car` / cs / focused
4. `in_car` / cs / pushing
5. `in_car` / cs / high
6. `lap_complete` / cs / neutral
7. `lap_complete` / cs / calm
8. `lap_complete` / cs / focused
9. `lap_complete` / cs / pushing
10. `lap_complete` / cs / high
11. `pit_entry` / cs / neutral
12. `pit_entry` / cs / calm
13. `pit_entry` / cs / focused
14. `back_on_track` / cs / neutral
15. `back_on_track` / cs / calm
16. `back_on_track` / cs / focused
17. `pit_outcome` / cs / neutral
18. `pit_outcome` / cs / calm
19. `pit_outcome` / cs / focused

### Pravidla češtiny

- Přirozená mluvená čeština (coach na rádiu), ne doslovný překlad.
- Tykání. Bez slangové omáčky, bez memů.
- Slot tokeny **kopíruj přesně** beze změny: např. `{position}`, `{lap}`, `{lap_time}`, `{old_position}`.
- `in_car` ≠ vjezd do boxů. `pit_entry` = pit road. `back_on_track` = výjezd. `pit_outcome` = výsledek zastávky (pozice).
- Emoci ladder: neutral=věcné · calm=klidné · focused=ostřejší/soustředěné · pushing=tlačí · high=intenzivní, stále mluvené.

### Tvrdé TTS limity

1. Končí `.` `!` nebo `?`
2. ≤ 90 znaků (lépe ≤ 70)
3. Žádné ALL-CAPS slovo ≥4 písmen (pozor na „BOX“, „PIT“ apod. — napiš malými / větou)
4. Žádné `!!` `??` `...`, emoji, URL, 4+ ciferné řetězce, surové `&`
5. Žádné HUD labely („VJEZD DO BOXŮ“, „OSOBNÍ REKORD“)

### Karty eventů + EN reference

#### `in_car`
- slots: (none)
- notes: Mock EN matrix. Seated in-car once per stint. Random pick. Not pit entry.
- emotions to write (cs): neutral, calm, focused, pushing, high
- EN reference (style/meaning only — write natural Czech, not literal calque):
  - **neutral**:
    - EN: In the car.
    - EN: Belted in.
    - EN: Ready to go.
    - EN: Seats in.
    - EN: Let's go to work.
    - EN: We're in.
    - EN: Strapped in.
    - EN: Car is live.
  - **calm**:
    - EN: You're settled in the seat.
    - EN: Easy now, get comfortable.
    - EN: You're in and settled.
  - **focused**:
    - EN: You're set in the car.
    - EN: Locked in and ready.
    - EN: Seat set, mind sharp.
  - **pushing**:
    - EN: You're in. Time to dig in.
    - EN: Strapped in, keep after it.
    - EN: You're set. Bring the pace.
  - **high**:
    - EN: You're in. Come on, let's go!
    - EN: Locked in now. Make it count!
    - EN: You're set. Let's get after it!

#### `lap_complete`
- slots: {lap}, {lap_time}
- notes: Mock EN until the text model fills variants. Generic lap line; do not read tenths.
- emotions to write (cs): neutral, calm, focused, pushing, high
- EN reference (style/meaning only — write natural Czech, not literal calque):
  - **neutral**:
    - EN: Lap complete.
    - EN: That's a lap.
    - EN: Another lap done.
    - EN: Lap in the books.
  - **calm**:
    - EN: Lap {lap} done — {lap_time}.
    - EN: That's another steady lap.
    - EN: Lap done. Keep it smooth.
  - **focused**:
    - EN: Lap {lap} logged at {lap_time}.
    - EN: That's the lap. Stay sharp.
    - EN: Lap done. Reset and focus.
  - **pushing**:
    - EN: Lap {lap} done. Keep pushing.
    - EN: {lap_time} on that lap. Dig in.
    - EN: That's another lap. Keep after it.
  - **high**:
    - EN: Lap {lap} done. Come on, push now!
    - EN: That's {lap_time}. Keep it coming!
    - EN: Lap done. Let's go again!

#### `pit_entry`
- slots: {position}
- notes: Mock EN. Pit-road entry only — not getting into the car.
- emotions to write (cs): neutral, calm, focused
- EN reference (style/meaning only — write natural Czech, not literal calque):
  - **neutral**:
    - EN: In the pits.
    - EN: Coming in.
    - EN: Box this time.
    - EN: Down the pit lane.
  - **calm**:
    - EN: Easy in, position {position}.
    - EN: Settle it down the pit lane.
    - EN: You're on pit road. Keep it smooth.
  - **focused**:
    - EN: Pit road, position {position}. Stay sharp.
    - EN: You're on pit road. Keep it clean.
    - EN: Pit road now. Stay focused.

#### `back_on_track`
- slots: {position}
- notes: Mock EN. Leaving pit road, back on track. Not a car-entry line.
- emotions to write (cs): neutral, calm, focused
- EN reference (style/meaning only — write natural Czech, not literal calque):
  - **neutral**:
    - EN: Back on track.
    - EN: Out of the pits.
    - EN: Rolling again.
    - EN: We're back out.
  - **calm**:
    - EN: Back out in position {position}.
    - EN: You're clear of pit road. Settle in.
    - EN: Rolling on track again. Keep it smooth.
  - **focused**:
    - EN: Back out, position {position}. Lock in.
    - EN: You're on track. Build the pace cleanly.
    - EN: Pit road behind you. Eyes forward.

#### `pit_outcome`
- slots: {position}, {old_position}
- notes: Prefer same correlationId as pit_entry. State net position change only if known.
- emotions to write (cs): neutral, calm, focused
- EN reference (style/meaning only — write natural Czech, not literal calque):
  - **neutral**:
    - EN: Stop done. You're {position}.
    - EN: Out of the box, {old_position} to {position}.
    - EN: Service complete. Position confirmed.
  - **calm**:
    - EN: Service complete. Settle into {position}.
    - EN: From {old_position} to {position}. Nice and steady.
    - EN: Stop is done. Your place is settled.
  - **focused**:
    - EN: Stop complete. You're now {position}.
    - EN: Box result, {old_position} to {position}. Stay sharp.
    - EN: Service complete. Position {position}. Eyes forward.


### Výstup

Jen JSON. Bez markdown fence. Bez textu okolo.

```json
{
  "graph_version": 1,
  "wave": "W6a",
  "author_model": "gpt-…",
  "locale": "cs",
  "patches": [
    {
      "node_id": "in_car",
      "locale": "cs",
      "emotion": "neutral",
      "lines": ["Jsi v autě.", "Pásy zapnuté."]
    }
  ]
}
```

Přesně **19** objektů v `patches`. `graph_version`: 1.

### Self-check

počet=19? locale vždy cs? sloty beze změny? in-car vs pit význam OK? ≤90 znaků? Pak jen JSON.

## END OF PROMPT

