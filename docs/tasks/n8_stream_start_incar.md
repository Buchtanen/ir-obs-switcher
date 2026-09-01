# N8 — Stream start TTS + in-car flavor + opener mutex

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §5  
**Depends on:** **N2** (`STREAM_START` already in `COMMENTARY_ONLY_EVENTS`; graph still loads). N11 supplies the long node.  
**v1:** bridge + mutex only. Cover is N9 **cut**. Long welcome copy is **N11**, not this task.

## Context

`obs_stream_started` in `main.py` **only** refreshes YouTube status. There is **no** commentary hook today — this task adds the bridge.

Four openers already exist (stream, intro, in_car, preview). **Mutex required.** Do not ship “both can fire (scheduler orders them).”

Generic `in_car` graph is already dense. Add mode select; do not delete generic until N11 migrates lines.

## Owns

- Bridge: `main.py` `obs_stream_started` → `overlay.http.get_overlay_runtime()` → COMMENTARY_ONLY `STREAM_START` (fail-soft if overlay down). Accessor already exists; no new global
- `StreamStartContext` module path: prefer `commentary/stream_context.py` (shared if HUD cover ever happens)
- Opener mutex in runtime or director (table in epic §5). A spoken `STREAM_START` also holds `director._busy_until` for node duration once N11 lands
- In-car: director mode pick (detector already sets `envelope.mode`)
- tests
- Must not: OBS scene table, overlay cover, RaceObserver FSMs, 15 s copy in this commit (formatter fallback is 4 s / `skipped / no_node`)

## Acceptance criteria

- [x] Mutex table implemented (one winner per situation)
- [x] Stream start while already seated → welcome only, no second in-car
- [x] Seated + intro: ENTER_CAR **or** intro, not both (existing brief-defer may be reused)
- [x] `STREAM_START` once per OBS rising edge; silent until N11 adds a node (test: envelope emitted, director `no_node` / no crash)
- [x] Do **not** add a 15 s graph node here (unknown/missing node must not fail graph load — N2 already registered the type)
- [x] `commentary.stream_start` default `false`
- [x] Fail-soft: stream still starts if commentary / overlay runtime missing

## Test plan

- [x] Stream edge → one envelope; repeat tick none; director no_node until N11
- [x] Already in-car + stream start → no ENTER_CAR this window
- [x] Existing in_car / session_briefs tests pass

## Docs impact

- [x] COMMENTARY_ENGINE STREAM_START + mutex
- [x] CONFIG.md + example.ini

## Config impact

- `commentary.stream_start` default `false`
