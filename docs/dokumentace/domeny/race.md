# Race interpretation (`src/irswitch/race/`)

`RaceState` + observer ve **všech** overlay modech (ne jen Race session). Gapy, flags, aftermath, finish semantics, P/Q hunt, grid story.

Track excursion: `observer.py` tiká `TrackExcursionDetector` (feature source) a `TrackExcursionEngine` (jediný publisher `TRACK_EXCURSION`). `[race_scenarios] mode`: `active` mluví jen to, co engine pustí; `shadow` tiká + tape, nemluví; `legacy` detektor vypnutý, aftermath ON. Fail-soft enginu = ticho, ne dual-publish. `cause`/`damage` = `unknown`.

## Boundaries

- Nepředpokládej Race-session-only.
- Nepřepíná OBS.
- Public watcher API (N10) **není** — jen debug `watcher_log.py`.
- Detektor není druhý speaker. Pole `excursion` zůstává `TrackExcursionDetector` (tape drain).

## Key files

`runtime.py`, `pipeline.py`, `observer.py`, `context.py`, `opponents.py`, `flags.py`, `aftermath.py`, `session_end.py`, `ministory.py`, `editorial_stage.py`, `prepared_facts.py`, `order.py`, `run.py`, `timing/`. Stream outro after iRacing QUIT lives in `runtime.py` (speak, then OBS stop).

## Tests

`tests/test_race_*.py`, `tests/test_flags_observer.py`, `tests/test_incident_aftermath.py`, `tests/test_timing_hunt.py`, `tests/test_track_excursion_live.py`, `tests/test_track_excursion_engine.py`.

## Related

[events](events.md), [iracing](iracing.md), [CONFIG.md](../../../CONFIG.md) (`race_scenarios.mode`).
