# N7 — Race start: quali recap + rolling-start padding

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §3.3  
**Depends on:** P4 wrap/preview ([#176](https://github.com/Buchtanen/ir-obs-switcher/pull/176) / issue #175), N2 for long-ish nodes  
**Extends:** P4 — keep `SESSION_WRAP` / `SESSION_PREVIEW`; add pre-green recap + rolling padding  
**Branch hint:** `feat/race-grid-rolling-start`

## Context

Race is a different sport. While waiting for green we want a **short Quali recap** (position, time if known). Rolling starts (`SessionState == ParadeLaps` (3) and/or start Ready/Set/Go bits) need **padding copy** and maybe extra beats. Today we have session intro + SoF + weather, then silence until green.

## Owns / must not touch

- **Owns:** `GridWatch` in RaceObserver, events `GRID_WAIT` / `ROLLING_START` (names TBD), slots for quali pos/time from weekend bag, tests  
- **Must not:** N8 stream-start, N4 finish, battle emitters  

## Acceptance criteria

- [ ] On Race session + not yet green (`SessionState` in GetInCar/Warmup/ParadeLaps, or startHidden): at most one **quali recap** line (position + optional time) from bounded weekend memory  
- [ ] Missing quali result → recap skipped (session intro still handles “it’s a race”)  
- [ ] ParadeLaps / startReady-Set-Go: low-priority padding envelopes with cooldown so P1 silence watchdog is not the only vata  
- [ ] Does not fight `SESSION_INTRO_RACE` / SoF (intro first; recap after or instead of a second intro — document order: intro → SoF → recap → rolling padding)  
- [ ] Green / startGo: stop padding; do not announce green twice if N5 flags also speak green (one owner: **N5 speaks flag**, N7 stops padding)  
- [ ] Feature flag default off  

## Test plan

- [ ] Unit: weekend bag has P12 + 1:32.1 → one recap; session change resets  
- [ ] Unit: ParadeLaps ticks do not spam (cooldown)  
- [ ] Unit: Racing state 4 → no more rolling padding  
- [ ] Unit: no quali bag → no recap envelope  

## Docs impact

- [ ] Matrix race pre-green rows  
- [ ] `COMMENTARY_ENGINE.md` sidecar/derived events  
- [ ] `CONFIG.md` if flagged  
- [ ] N11 briefs for new nodes  

## Config impact

- `race_observer.grid_story` default `false`  
- padding cooldown seconds  
