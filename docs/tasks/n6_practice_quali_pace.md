# N6 — Practice/Quali: gap-TTS off + hunt by rival lap time

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §6  
**Depends on:** N1 `CarIdxBestLapTime` on RaceState (N6b); P2 filler (N6a)  
**Hard stop:** no usable `CarIdxBestLapTime` → **do not** ship PACE_HUNT; do **not** use DriverInfo

## Context

P/Q viewer cares about the **time that holds a position**. `BattleEmitter` is gap-based for all sessions. `QualiEmitter.position_attack` labels P{n} from **hero own PB** — that is the wrong sport; quarantine or retarget, do not “reuse” it as hunt-by-time.

P2 already rotates FIELD_FACT including leader on a **15–20 s** cooldown. Leader 5 min = extra cooldown on that fact, not a new node.

## Owns

- **N6a:** director or battle-adapter filter: no hunting/hunted TTS in PRACTICE/QUALIFYING; config keys below. HUD may still show hunting. Filter lives in **commentary** (or a thin adapter) — `events/` must not know about TTS (`py-architecture-layers.mdc`)
- **N6a:** bootstrap `[race_observer]` in `config.example.ini` + `RaceObserverSettings` dataclass + loader + pass into `OverlayRuntime` / `RaceObserver()` (today: `RaceObserver()` with no settings, no re-apply in `_reset_commentary`). Later N3/N5 **add keys** to this dataclass — do not create a second type
- **N6a:** `RaceObserver.next_filler_envelope` leader fact ≤ 1× / 300 s. Rotation `break`s on first eligible kind — leader cooldown must **`continue`** to the next kind or it suppresses the whole filler
- **N6b:** `race/timing_hunt.py` only after N1 fixtures prove times; compare hero best/projected vs `CarIdxBestLapTime` of class P{n}
- Must not: second filler path; DriverInfo times; duplicate PracticeEmitter sectors; `[event_engine]` TTS keys

## Acceptance criteria

- [ ] N6a: gap-hunt TTS suppressed in P/Q when config false (default)
- [ ] N6a: race battle TTS unchanged
- [ ] N6a: leader field fact cooldown 300 s; skip if a higher-priority beat spoke recently; **continue** rotation to next kind (do not `break` and mute all filler)
- [ ] N6a: `[race_observer]` loads; `RaceObserver` constructed with settings; `_reset_commentary` re-applies
- [ ] N6b: `CarIdxBestLapTime` all None → no envelope (silence)
- [ ] N6b: never read DriverInfo for times
- [ ] Quali `position_attack` either retargeted to rival time or documented as “own PB only” and not sold as hunt-P{n}

## Test plan

- [ ] Practice + small gap_ahead + flag off → no hunting speech envelope
- [ ] Race hunting still emits
- [ ] Leader fact twice in 100 s → second suppressed; other filler kind still eligible in between
- [ ] N6b: rival best 1:32.0, hero projected 1:32.04 → one hunt; all -1 → none

## Docs impact

- [ ] CONFIG.md + example.ini
- [ ] Matrix battle vs timing-hunt
- [ ] Epic §6

## Config impact

- `commentary.gap_hunt_tts_in_practice` default `false` (TTS gate, not HUD)
- `commentary.gap_hunt_tts_in_qualifying` default `false`
- `race_observer.leader_pace_cooldown_s` default `300` (N6a creates the section)
