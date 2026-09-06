# Race interpretation (`src/irswitch/race/`)

`RaceState` + observer ve **všech** overlay modech (ne jen Race session). Gapy, flags, aftermath, finish semantics, P/Q hunt, grid story.

## Boundaries

- Nepředpokládej Race-session-only.
- Nepřepíná OBS.
- Public watcher API (N10) **není** — jen debug `watcher_log.py`.

## Key files

`runtime.py`, `pipeline.py`, `observer.py`, `context.py`, `opponents.py`, `flags.py`, `aftermath.py`, `session_end.py`, `ministory.py`, `editorial_stage.py`, `prepared_facts.py`, `order.py`, `run.py`, `timing/`. Stream outro after iRacing QUIT lives in `runtime.py` (speak, then OBS stop).

## Tests

`tests/test_race_*.py`, `tests/test_flags_observer.py`, `tests/test_incident_aftermath.py`, `tests/test_timing_hunt.py`.

## Related

[events](events.md), [iracing](iracing.md).
