# N5 — Session flags watcher (all sessions)

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §2.4  
**Depends on:** N1 (`session_flags.py`), N2 for mode-specific nodes (can ship generic EN first)  
**Branch hint:** `feat/session-flags-observer`  
**Parallel with:** N3 **if** N3 does not own `events/` flag module (N5 owns flags only)

## Context

`SessionFlags` is extracted and ignored. We want rising-edge commentary in Practice, Quali, and Race, with a graph branch per flag. Checkered flag ≠ finish (N4).

## Owns / must not touch

- **Owns:** `race/observer/flags.py` (or `events/flags.py` if kept as a thin emitter), COMMENTARY_ONLY `SESSION_FLAG` (+ `metrics.flag`), tests  
- **Must not:** finish semantics, incident FSM, `sequence_graph.json` mass text (stub node + N11)  

## Acceptance criteria

- [ ] Rising edge per decoded flag name; falling edge silent unless we later add “green after yellow” as its own edge  
- [ ] Coalesce yellow + yellowWaving + caution into one **yellow** speak (document mapping)  
- [ ] Start bits Hidden/Ready/Set/Go are **not** this task’s rolling padding (N7); either ignore or emit raw for N7 to consume — pick ignore here  
- [ ] Per-flag cooldown (yellow longer than blue)  
- [ ] Works in P/Q/R; director uses mode layer when N2 is present  
- [ ] Checkered flag event is `SESSION_FLAG` / branch `checkered`, never `FINISH`  
- [ ] Feature flag default off  

## Test plan

- [ ] Unit: 0 → yellow bit → one event; held bits → none  
- [ ] Unit: yellow+caution same tick → one coalesced event  
- [ ] Unit: checkered bit does not create `finish` candidate  
- [ ] Unit: cooldown suppresses chatter  

## Docs impact

- [ ] Matrix new “flags” subsection  
- [ ] `CONFIG.md` + example.ini  
- [ ] `COMMENTARY_ENGINE.md` COMMENTARY_ONLY set  

## Config impact

- `race_observer.flags` default `false`  
- Optional per-flag cooldown seconds  
