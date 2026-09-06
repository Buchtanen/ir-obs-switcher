# iRacing (`src/irswitch/iracing/`)

Jen extraction / parse shared memory. Žádný `overlay_mode`, TTS, OBS scény.

## Boundaries

- Live session type = `SessionInfo.Sessions[SessionNum].SessionType` přes `extract_session_type()`. Nikdy `WeekendInfo.EventType`.
- `DrivingMode.RACE` = on-track in-car (i Practice/Quali). Ne Race-session.
- GARAGE = `IsGarageVisible`.
- Sentinel hodnoty: skill `iracing-sdk-display-format`.

## Key files

Viz [mapa](../mapa-souboru.md#iracing). `session_flags.py` je decode bitů, ne policy.

## Tests

`tests/test_sdk_units.py`, `tests/test_session_flags.py`, `tests/test_extractors.py` (a příbuzné).

## Related

Skill `iracing-session-glossary`. [logic](logic.md) spotřebovává `DrivingMode`.
