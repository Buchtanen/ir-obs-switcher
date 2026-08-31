# N6 — Practice/Quali: hunt by lap time, leader pace 5 min

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §3.3, §6  
**Depends on:** P2 (`StoryContext` / stream memory), existing `TimingStore` / quali projection  
**Branch hint:** `feat/pq-pace-hunt`  
**Parallel with:** N3/N5 if files stay `race/observer/timing_hunt.py` + battle **gate** only

## Context

In Practice/Quali the viewer cares about **the time that holds a position**, not the bumper gap. Current `BattleEmitter` hunting is gap/closing for all sessions. Leader time as vata must not repeat more than **once per 5 minutes**.

Sector/lap improvement already exists (`PracticeEmitter`, `LapEmitter`, quali projection) — do not duplicate; only fill gaps (e.g. speak position change **with time** if the slot is missing).

## Owns / must not touch

- **Owns:** `TimingHuntWatch`, leader-pace field-fact policy (cooldown 300 s), config to **suppress gap-hunt TTS** in P/Q, tests  
- **May touch:** `events/battle.py` only behind a session-mode gate (or commentary ignore list) — smallest possible diff  
- **Must not:** race battle HUD, incident FSM, overlay widgets for hunting in P/Q unless already shown  

## Acceptance criteria

- [ ] `PACE_HUNT` (name TBD) when hero best or projected time is within a threshold of the time currently in P{n} (n = hero class pos − 1, or target locked)  
- [ ] Uses lap time / projected, **not** `gap_ahead`  
- [ ] Quali: prefer projected when confidence ≥ existing quali threshold; else best lap  
- [ ] Practice: best valid lap vs class position times (document source: `CarIdx` best from DriverInfo/telemetry — **verify field exists** in N1 follow-up if missing; do not guess a var name in code)  
- [ ] Gap-hunt commentary suppressed in PRACTICE and QUALIFYING by default; race unchanged  
- [ ] Leader pace filler: max 1× / `leader_pace_cooldown_s` (default 300); skipped if a higher-priority timing/incident beat spoke recently  
- [ ] Position gained/lost after a pass still uses existing emitters; add `lap_time` slot if cheap and tests show it is unbound today  

## Test plan

- [ ] Unit: hero projected 0.05 s from P4 time → hunt P4 once; cooldown  
- [ ] Unit: gap_ahead tiny in practice + flag off → no hunting TTS envelope from battle  
- [ ] Unit: leader fact twice in 100 s → second suppressed  
- [ ] Race: battle hunting still emits  

## Docs impact

- [ ] Matrix battle vs timing-hunt rows  
- [ ] `CONFIG.md` + example.ini  
- [ ] Epic §6  

## Config impact

- `event_engine.gap_hunt_tts_in_practice` default `false`  
- `event_engine.gap_hunt_tts_in_qualifying` default `false`  
- `race_observer.leader_pace_cooldown_s` default `300`  

If DriverInfo does not expose others’ best laps, **stop and document** — do not invent; fall back to quali projection only.
