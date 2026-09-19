# Race run epoch and green-relative phase

## Problem

The recorded stream contained two race starts under one iRacing session key. The producer treated both as one lifecycle, so stale observer state could cross the restart and the race phase included formation or a failed start.

## Implemented contract

- A material `SessionTime` rewind over five seconds must persist for at least 100 ms before it is accepted as a restart. One stale sample and small SDK jitter are ignored.
- A confirmed same-session restart increments `RaceState.run_epoch` and resets run-scoped observers before the first sample of the new run is observed.
- Context identity, situation, story facts, event metrics, correlation IDs and tape rows carry the same run epoch.
- V4 correlation IDs are namespaced as `run:<epoch>:<correlation>`; legacy overlay payloads receive a top-level `runEpoch`, while V4 payloads receive `metrics.runEpoch`.
- The tape remains one session/VOD timeline. It emits `run_reset`, preserves `t_mono` and `t_stream`, and restarts only `t_green`.
- Race progress uses a witnessed green transition. Formation time is excluded. A mid-race attach does not invent a green timestamp and falls back to authoritative remaining-time or lap progress.
- Finish facts include a classification only when the player finish is confirmed; switching sessions cannot invent a finishing position.

## Evidence

`tests/test_race_run_epoch.py` covers rewind confirmation, jitter, late join, green-relative progress, stream identity, invalid scalar rejection, finish semantics and runtime reset ordering. Existing race pipeline, fixture, tape and narrative tests are also run as the regression set.
