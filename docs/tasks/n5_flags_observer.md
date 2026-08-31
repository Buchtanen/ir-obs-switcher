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

- [x] Rising edge only
- [x] Coalesce yellow family → one `yellow` speak
- [x] v1 names: `yellow`, `green`, `checkered` in overlay_mode RACE (other modes: log only / no speak)
- [x] Ignore start family
- [x] Per-flag cooldown
- [x] Checkered does not set `player_finished` and does not SESSION_WRAP
- [x] Feature flag default off
- [x] Register `SESSION_FLAG` in `COMMENTARY_ONLY_EVENTS` (coord N2)

## Test plan

- [x] 0 → yellow bit → one event; hold → none
- [x] yellow+caution same tick → one
- [x] checkered bit → SESSION_FLAG not FINISH
- [x] cooldown

## Docs impact

- [x] Matrix flags row when shipped
- [x] CONFIG.md + example.ini

## Config impact

- `race_observer.flags` default `false`
