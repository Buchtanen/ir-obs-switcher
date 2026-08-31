# N4 — Finish is crossing (or eligible pit), not checkered

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §2.5  
**Depends on:** N1 (`session_flags` on RaceState optional; **do not** OR flag bit with state 5)  
**Risk:** wide — sequential, audit every `session_finished`

## Context

One boolean today (`SessionState` 5 or 6) fires FINISH, mutes the field, aborts hunting, wraps the session. Product: checkered is a flag; hero finish is later.

**Do not** treat client checkered **bit** as session checkered.

## Owns

Mandatory grep/re-point (complete vs current readers of `state.session_finished`):

- `race/context.py` (stateful: checkered start, lap/dist wrap, pit rise)
- `events/session.py`
- `events/session_phase.py` / `engine.py` `filter_post_race`
- `events/battle.py` abort
- `events/practice.py`, `events/quali.py`, `events/sector_split.py`, `events/pit_story.py`
- `events/target_locked.py` (missed in first draft)
- `race/narrative.py` wrap trigger
- `overlay/mock.py` constructor
- tests (`test_race_context.py`, `test_session_phase.py`, `test_event_emitters.py`, `test_session_stream_narrative.py`, `test_sector_split_emitter.py`, …)

## Acceptance criteria

- [x] Three booleans: `session_checkered` (`SessionState == 5`), `player_finished`, `mute_field` (follows player_finished)
- [x] `FINISH` only on `player_finished` rising
- [x] player_finished if: lap complete / dist wrap across s/f while session_checkered, **or** `OnPitRoad` false→true after checkered **and** was not on pit road when checkered started
- [x] `on_pit_road is None` is **unknown** — do not treat as False (dropout must not arm pit-rise finish)
- [x] Pit-rise uses `is_esc_teleport` (same as `should_begin_pit_cycle`) — ESC/teleport is not finish
- [x] `RaceContextAnalyzer.reset()` drops checkered/pit latch; no finish across disconnect
- [x] CoolDown without player_finished → one FINISH fallback
- [x] `filter_post_race` + battle abort use `mute_field` / `player_finished`, **not** state 5 alone
- [x] Hunting can still emit after state 5 until player_finished (test)
- [x] `SESSION_WRAP` does **not** fire on `session_checkered`; uses `player_finished` or session key change
- [x] N5 checkered flag ≠ FINISH
- [x] PR description lists every old `session_finished` call site

## Test plan

- [x] State 5, hero mid-lap → no FINISH, hunting not aborted
- [x] Then lap/dist wrap → FINISH + mute once
- [x] Already on pit road at checkered → pit-rise does **not** finish
- [x] State 6 without cross → FINISH fallback
- [x] Existing session tests updated

## Docs impact

- [ ] Matrix finish row
- [ ] COMMENTARY_ENGINE finish vs checkered
- [ ] Epic §2.5

## Config impact

Prefer none. Escape hatch only if needed: `event_engine.mute_at` = `player_finish` (default).
