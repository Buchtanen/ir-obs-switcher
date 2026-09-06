# Event Engine (`src/irswitch/events/`)

Kandidáti z `RaceState`, arbitration, V4 envelope. Nepíše TTS ani OBS scény. Po accepted batch jde `AsyncEventFanout` na overlay + commentary.

`events/scenarios/` je **jiný** kernel: atomické race stories. Není to `events/engine.py` (HUD emitery).

## Boundaries

- `iracing/` sem nepatří (žádná interpretace v extractu).
- HUD tokeny ne. Commentary graph ne.
- Složený `docs/scenarios/track_excursion_story_v1.json` je `design_reference` — nespouští se. Taxonomie příčin se řeší jinde.

## Key files

`engine.py`, `manager_v2.py`, `envelope.py`, `arbitration.py`, `async_fanout.py`, emittery, `adapters/`.

Scénáře: `scenarios/track_excursion.py` (holds + evidence), `scenarios/track_excursion_runtime.py` (jediný speaking publisher), `scenarios/engine.py` + `loader.py` + `registry.py`, `scenarios/data/track_excursion_v1.json`. Taxonomie příčin se řeší jinde.

## Tests

`tests/test_event_*.py`, `tests/test_n12_*.py`, `tests/test_scenario_*.py`, `tests/test_track_excursion_*.py`.

## Related

[race](race.md), [overlay](overlay.md), [commentary](commentary.md), [live test](../../track_excursion_live_test.md).
