# In-flight: Track Excursion I3 — ScenarioEngine publisher

**Status:** kód na `feat/scenario-and-prepared-graph`, **ne** na `master`.
**Issue:** [#216](https://github.com/Buchtanen/ir-obs-switcher/issues/216).
**Po merge:** přesunout do [domeny/events.md](../domeny/events.md) + [domeny/race.md](../domeny/race.md) a tuhle stránku smazat.

## Delta oproti masteru

Master: `RaceState → TrackExcursionDetector → RaceObserver._scenario_pending` (detektor mluví v `active`).

Tato větev: detektor zůstává feature source; **řeč** jen přes `ScenarioEngine` + `events/scenarios/data/track_excursion_v1.json`.

- `active` — publikuje detector envelopes, jejichž `beatId` engine pustí
- `shadow` — engine tiká (tape `engine_transition`), nemluví
- `legacy` — beze změny
- fail-soft enginu = ticho, ne druhý publisher
- `cause` / `damage` = `unknown`; taxonomie příčin se řeší jinde
- `docs/scenarios/track_excursion_story_v1.json` se nespouští

## Testy

`tests/test_track_excursion_engine.py`, stávající `tests/test_track_excursion_live.py`.

## Living spec

[track_excursion_live_test.md](../../track_excursion_live_test.md)
