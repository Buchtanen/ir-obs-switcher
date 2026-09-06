# Logic / scene switcher (`src/irswitch/logic/`)

Jediná cesta OBS scene switch. Debounce, cooldown, override, grace 3 s po loadu. `Policy` mapuje `DrivingMode` → název scény.

## Boundaries

Žádné HUD widgety, TTS, Event Engine. Kapitoly streamu (`stream_chapters.py`) jsou OBS-clock, ne iRacing session.

## Key files

`state_machine.py`, `policy.py`, `stream_chapters.py`, `youtube_chapters.py`, `broadcast_clock.py`.

## Tests

`tests/test_state_machine.py`, `tests/test_policy.py`, `tests/test_broadcast_clock.py`, `tests/test_stream_chapters.py`.

## Related

[iracing](iracing.md), [obs](obs.md), [runtime](runtime.md).
