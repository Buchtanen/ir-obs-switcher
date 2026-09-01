# N7 — Race start: quali recap + rolling padding

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md)  
**Status:** **shipped** on `cursor/narrative-observers-epic-4749` (listen later; user chose to land the option).

## Why it waited

P4 wrap/preview + session intros/SoF already occupy pre-green. `StreamMemory` had **no quali result bag**. `commentary.session_briefs=false` silences wrap/preview. Stacking recap + rolling novel on top of intro/in-car/stream-start needs the **opener mutex** (N8) first.

## Product gate

Dedicated **`race_observer.grid_story`** (default **false**), **not** `session_briefs`. Director skips `SESSION_INTRO_RACE` with `grid_story_replaces_intro` when the flag is on **and** the stream quali bag exists. Missing bag → skip recap; race intro still allowed if `session_briefs` is on.

## Owns

- `StreamMemory` quali bag (class position + `LapBestLapTime` seconds). Never YAML `ResultsPositions` / DriverInfo times.
- `race/grid_story.py` — `QUALI_RECAP` (opener) + `PARADE_PAD` (not opener)
- Formatter EN/CS fallback (no graph densify; N11 D still optional)
- Stop padding on `SessionState == 4` **or** green flag (N5 still owns green speak)
- At most two parade pads, 25 s cooldown. Not a rolling-start screenplay.

## AC

- [x] At most one quali recap from weekend bag; missing bag → skip
- [x] ParadeLaps padding with cooldown; stop on SessionState 4 **or** N5 green
- [x] Recap **instead of** a second `SESSION_INTRO_RACE`, not after intro+SoF+in-car
- [x] Default off; `session_briefs` does not unmute recap
