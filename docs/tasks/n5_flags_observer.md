# N5 — Flags v1 (race yellow / green / checkered)

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §2.4  
**Depends on:** N1 decoder + flags on `RaceState`, N2 for `SESSION_FLAG` in `COMMENTARY_ONLY_EVENTS`, N6a for `[race_observer]` settings dataclass  
**v1 reduced:** not all sessions, not full tree

## Context

`SessionFlags` is extracted and ignored. v1 speaks three race beats. Start lights are **not** this task (N7 deferred). Checkered flag ≠ finish (N4).

## Owns

- new `race/flags.py` (flat), called from `RaceObserver.observe`
- formatter fallback in `observer.format_filler_text` until N11
- tests
- Must not: finish semantics, startHidden/Set/Go padding, graph mass texts

## Acceptance criteria

- [ ] Rising edge only
- [ ] Coalesce yellow family → one `yellow` speak
- [ ] v1 names: `yellow`, `green`, `checkered` in overlay_mode RACE (other modes: log only / no speak)
- [ ] Ignore start family
- [ ] Per-flag cooldown
- [ ] Checkered does not set `player_finished` and does not SESSION_WRAP
- [ ] Feature flag default off
- [ ] Register `SESSION_FLAG` in `COMMENTARY_ONLY_EVENTS` (coord N2)

## Test plan

- [ ] 0 → yellow bit → one event; hold → none
- [ ] yellow+caution same tick → one
- [ ] checkered bit → SESSION_FLAG not FINISH
- [ ] cooldown

## Docs impact

- [ ] Matrix flags row when shipped
- [ ] CONFIG.md + example.ini

## Config impact

- `race_observer.flags` default `false`
