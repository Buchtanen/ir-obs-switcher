# N10 — Watcher decision log

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md)  
**Status:** **debug ring shipped**. Public `GET` + admin page still deferred.

## Why the API stays deferred

A user-facing `GET` + admin page is a separate contract (`API.md`, schemaVersion). v1 needs log lines in tests/DEBUG, not a new endpoint.

## Debug ring (shipped)

- `src/irswitch/race/watcher_log.py` — bounded ring (64)
- fields: `watch`, `kind`, `emitted`, `reason`, `confidence`, `mono_ms`
- RaceObserver `watches` survives session reset; `reset_stream` clears
- Director mirrors speak/skip of watcher event types (`graph_hit` / `formatter_fallback` / `generic_suppressed`)
- Flags/grid skip reasons on rising edges / one-shot stop (no 5 Hz INFO)
- No INFO per-tick spam (DEBUG only)
- Not in `status_snapshot`, no `GET`, no `API.md`

Do not open `feat/observer-decision-log` until after live listen.
