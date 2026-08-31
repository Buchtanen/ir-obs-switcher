# N4 — Finish is crossing (or pits), not checkered

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §2.5  
**Depends on:** N1 (speed/pit already exist; N1 not strictly required), careful merge after P0/P1 (`session_finished` is widely used)  
**Branch hint:** `feat/finish-after-checkered`  
**Risk:** wide behavioral change — **sequential**, not parallel with other `events/` slices

## Context

Today `RaceContextAnalyzer` sets `session_finished` when `SessionState` is Checkered (5) or CoolDown (6). `SessionEmitter` speaks `finish` on that edge. Checkered is a **flag**, not the hero’s result. Product: finish = first **s/f crossing after checkered**, or **pit entry after checkered**. CoolDown is a DNF fallback.

## Owns / must not touch

- **Owns:** `race/context.py` boolean split, `events/session.py`, `events/session_phase.py` mute policy, tests, all call sites of `session_finished` (must be audited in the PR)  
- **Must not:** classifier (N3), graph texts (N11), overlay art  

## Acceptance criteria

- [ ] Split state: `field_checkered` (state 5 or checkered bit) vs `player_finished`  
- [ ] `FINISH` envelope only on `player_finished` rising edge  
- [ ] `player_finished` if: lap complete / lap-dist wrap across s/f while field checkered, **or** `OnPitRoad` rising while field checkered  
- [ ] CoolDown without player_finished → still one `FINISH` (fallback)  
- [ ] Checkered **flag** does not emit `FINISH` (N5 owns flag TTS)  
- [ ] Post-race mute: after **player_finished** (not merely field checkered), keep finish/final EXIT; last-lap battles may continue until the hero crosses  
- [ ] `final_lap` unchanged (laps remain / white) unless tests prove a conflict  
- [ ] Audit list of `session_finished` uses in the PR description; each re-pointed to field vs player  
- [ ] HUD finish plate still highest priority when player_finished fires  

## Test plan

- [ ] Unit: SessionState 5, hero still on lap → no FINISH  
- [ ] Unit: then lap increment or dist wrap → FINISH once  
- [ ] Unit: state 5 + pit entry → FINISH once (no second on cooldown)  
- [ ] Unit: state 6 without cross → FINISH fallback  
- [ ] Unit: `filter_post_race` with field checkered but not player_finished still allows hunting/incident until policy says otherwise (document chosen mute moment)  
- [ ] Existing session emitter tests updated, not deleted  

## Docs impact

- [ ] `docs/scenario_coverage_matrix.md` finish row  
- [ ] `CONFIG.md` if mute policy is configurable  
- [ ] `COMMENTARY_ENGINE.md` finish vs checkered  
- [ ] Epic §2.5  

## Config impact

Prefer **no** new key. If mute-at-checkered vs mute-at-player-finish needs an escape hatch: `event_engine.mute_at` = `player_finish` (default) | `checkered`.
