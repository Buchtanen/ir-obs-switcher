# Event Engine (`src/irswitch/events/`)

Kandidáti z `RaceState`, arbitration, V4 envelope. Nepíše TTS ani OBS scény. Po accepted batch jde `AsyncEventFanout` na overlay + commentary.

## Boundaries

- `iracing/` sem nepatří (žádná interpretace v extractu).
- HUD tokeny ne. Commentary graph ne.

## Key files

`engine.py`, `manager_v2.py`, `envelope.py`, `arbitration.py`, `async_fanout.py`, emittery, `adapters/`.

## Tests

`tests/test_event_*.py`, `tests/test_n12_*.py`.

## Related

[race](race.md), [overlay](overlay.md), [commentary](commentary.md).
