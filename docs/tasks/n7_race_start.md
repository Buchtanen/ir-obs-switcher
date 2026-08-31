# N7 — Race start: quali recap + rolling padding

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md)  
**Status:** **DEFER** — not first landing. Live-listen after N4/N8/N5.

## Why deferred

P4 wrap/preview + session intros/SoF already occupy pre-green. `StreamMemory` has **no quali result bag**. `commentary.session_briefs=false` silences wrap/preview. Stacking recap + rolling novel on top of intro/in-car/stream-start needs the **opener mutex** (N8) first.

## When unblocked

- N8 mutex exists
- Weekend bag in `story.py`: quali class position + best lap
- Product choice: `race_observer.grid_story` **or** reuse `session_briefs` gate (must be explicit in director)
- N5 owns green speak; this task only **stops padding**
- One recap line, not a rolling-start screenplay

Until then: do not implement.

## Parking AC (for later)

- [ ] At most one quali recap from weekend bag; missing bag → skip
- [ ] ParadeLaps padding with cooldown; stop on SessionState 4 **and** N5 green
- [ ] Recap **instead of** a second `SESSION_INTRO_RACE`, not after intro+SoF+in-car
