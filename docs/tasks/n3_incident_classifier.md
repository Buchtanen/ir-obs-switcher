# N3 — Incident v1: off_track vs unknown + Speed on P3 FSM

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §2.3, §3.4  
**Depends on:** N1 (`speed_mps` on `RaceState`), N2 (branch pick), N6a (`[race_observer]` settings already exist), P3 `race/aftermath.py` on #179  
**Extends:** P3 — do **not** add `race/observer/incident.py` or `INCIDENT_RECOVERED`

## Context

P3 already classifies stalled/rolling from TrkLoc + LapDistPct and emits `INCIDENT_AFTERMATH` / `BACK_UNDER_WAY`. Generic `incident` also speaks (delta ≥ `incident_min_delta`, default 2). Aftermath fires on **any** count rise.

v1 does **not** claim car vs object or lost-control on air (5 Hz).

## Owns

- extend `race/aftermath.py` (Speed as **motion**, surface-first classify, LapDistPct fallback)
- `events/incident.py` **or** adapter: `metrics.branch` = `off_track` | `unknown` on INCIDENT
- tests (`test_incident_aftermath.py` + classify tests)
- Must not: new recovery event name; graph mass texts (N11)

## Acceptance criteria

- [ ] Classify `off_track` when surface is OffTrack around the tick; else `unknown`
- [ ] Nearby car is a **metric** only, never a spoken kind
- [ ] Tests: no neighbor + on-track + tick → `unknown` (not `contact_object`)
- [ ] **Classify stays surface-first** (`_looks_stalled`: OffTrack / not-on-track / tow → `stalled` even if Speed > 0). Do **not** reclassify a moving off-track car as `rolling` (that skips `BACK_UNDER_WAY`)
- [ ] Speed + LapDistPct = motion for (a) **on-track** stalled vs rolling and (b) stalled → `BACK_UNDER_WAY`. Speed missing → current LapDistPct only
- [ ] Test with Speed **set**: off-track + Speed 15 m/s still `stalled`, then on-track + moving → one `BACK_UNDER_WAY`
- [ ] Keep `BACK_UNDER_WAY`; no recovered TTS in PRACTICE/QUALIFYING
- [ ] Same-tick **INCIDENT** (engine, delta≥2, prio 90) vs **INCIDENT_AFTERMATH** (derived, any rise, prio 72, fan-out bypass): speak at most one. Branch on INCIDENT is not a second competitor
- [ ] Document `incident_min_delta` vs aftermath-any-rise: default leave delta=2; optional later commentary-only 1x off-track with cooldown (not this slice unless AC added)
- [ ] Flag `race_observer.incident_classify` default `false` (key on the dataclass **N6a already created**; do not create a second settings type)

## Test plan

- [ ] Off-track + tick → branch off_track
- [ ] On-track + tick → unknown
- [ ] On-track + Speed 0 held → stalled; speed recover → BACK_UNDER_WAY once
- [ ] Off-track + Speed > 0 → still stalled (regression vs Speed-primary)
- [ ] Existing P3 tests still pass with Speed unset (fallback)
- [ ] Same tick: INCIDENT + INCIDENT_AFTERMATH → only one spoken (scheduler or director test)

## Docs impact

- [ ] Epic refuse list stays accurate
- [ ] CONFIG.md + example.ini if flag added

## Config impact

- `race_observer.incident_classify` default `false`
- crawl/roll m/s thresholds
