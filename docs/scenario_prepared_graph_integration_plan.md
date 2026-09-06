# Integration plan — Track Excursion (#216) + prepared graph (#217)

**Branch:** `feat/scenario-and-prepared-graph`  
**Base:** `origin/master` @ `79a15d7` (#226 squash)  
**Issues:** [#216](https://github.com/Buchtanen/ir-obs-switcher/issues/216) open; [#217](https://github.com/Buchtanen/ir-obs-switcher/issues/217) closed (on master)  
**Status:** I0 + I1 done. I2 dropped (not a gate). I3 wired (engine is the sole publisher).

This is the living index. Detailed contracts stay in the #216 docs.

## 1. Why this branch exists

#216 native subset + #217 prepared graph landed on master via #226 (`79a15d7`).
This branch is only for #216 I3 (ScenarioEngine as the sole publisher).

## 2. What is already on master (`79a15d7`)

### #216 — native Track Excursion subset

Wired: `RaceState → TrackExcursionDetector → RaceObserver → N12 → graph v3 → Director → MiniStory → TTS`.

Spoken facts: off-track, stopped, rejoin, motion restored, Race tow, driven pit, S7a pace
loss / normal running. `[race_scenarios] mode=legacy|shadow|active` (dev default `active`).
Numeric INCIDENT points-only. Vocabulary gates. Episode/parent identity.

Not production: generic `ScenarioEngine` + JSON `track_excursion_story/v1` as the sole publisher.

### #217 — prepared graph (automated cut claimed complete on Test 7)

53-node core + graph v4 contracts, plan builder/scoring off the generic gateway, EN/CS
anchors, relation/forbidden-claim validation, fatal node, current/next reservation.
`prepared_filler.mode` default `active`. #217 closed.

Canonical files (on master):

- `docs/track_excursion_story_spec.md`
- `docs/track_excursion_implementation_plan.md`
- `docs/track_excursion_implementation_progress.md`
- `docs/track_excursion_live_test.md`
- `docs/race_scenario_engine_spec.md`
- `docs/prepared_graph_completion_plan.md`
- `src/irswitch/events/scenarios/*`
- `src/irswitch/commentary/prepared_filler.py`

## 3. I0 — absorb #226 (gate, no new product work)

Preferred: merge #226 to `master` (rebase first onto current master: #213/#227/#228;
drop `recordings/*.jsonl`; add `semver:minor`), then rebase this branch onto that master.

Fallback if #226 stays open: merge `feat/commentary-finish-episodes` into this branch
and keep #226 as the review vehicle. Do not fork a third copy of overlay/commentary.

I0 exit (done 2026-09-06):

- [x] #226 merged to master (`79a15d7`)
- [x] #215 / #218 / #217 / #225 closed
- [x] This branch rebased onto `79a15d7`

## 4. After I0 — remaining implementation

Work is sequential on shared files (`observer.py`, `director.py`, `consumer.py`,
`sequence_graph.json`, `ministory.py`). Do not parallelize 216 vs 217 on those paths.

### I1 — #217 — done

On master via #226. Issue closed. No second graph. No listen gate.

### I2 — not a work item

I2 was never new code. It meant: sit in iRacing, go off-track, keep tape + video, check the native subset already on master. Optional listen, not a merge gate.

### I3 — #216 — plug ScenarioEngine in now

No cause-threshold defaults. Log observations/transitions; retune from tests and tapes.

**Publisher**

- [x] Production path: `ScenarioEngine` + named guards/actions for facts the native reducer already knows
- [x] Native `TrackExcursionDetector` becomes a feature source or `legacy`; **one** speaking publisher
- [x] `legacy|shadow|active` fail-soft; shadow publishes no new scenario facts
- [x] Existing excursion unit/replay tests stay green for connected facts (off-track, stop, rejoin, motion, tow, pit, S7a pace)

**Causes — observe, do not invent**

Do not ship yaw/sideslip/contact/brake defaults. Missing evidence stays `CAUSE_UNKNOWN` / omitted noun.

| Runtime ID | Now |
| --- | --- |
| `LOSS_OF_CONTROL`, `SLIDE`, `SPIN` | log candidates only; no speak |
| `CONTACT_*`, `BRAKING_OVERSHOOT`, `AVOIDANCE_MANEUVER` | log candidates only; no speak |
| `CONTROL_REGAINED` | not `MOTION_RESTORED`; no speak |
| `DAMAGE_*` / `PIT_FOR_REPAIRS` | pace loss ≠ damage; no speak |
| `RESET_TO_PITS` | log until ESC/teleport is proven |

## 5. Out of scope on this branch

| Item | Owner |
| --- | --- |
| Session-long hunting / history stories | #220 |
| Prompt profiles factual vs color | #222 |
| Multi-sentence one-duck playback | #223 |
| Overlay HUD / `display-v4.js` / i18n tokens | overlay agent only, not here |
| iRacing Data API / OAuth | #217 backlog |
| Sampling runtime (TelemetrySampler / LiveStateHub) | #212 after this spec |
| Finish/outro/stale revision | already in #226; do not re-open |

## 6. Test and docs contract

After I0, keep using the existing plans:

- #216: `docs/track_excursion_implementation_plan.md` + live test + progress
- #217: `docs/prepared_graph_completion_plan.md` + `docs/commentary_prepared_active_test.md`

This file only records integration order and the master-vs-#226 gap.

Every behavior change: tests or explicit TDD-exception (live iRacing/OBS listen).  
Config: `[race_scenarios].mode` and `[commentary.prepared_filler].*` already specified on #226 — no new keys in I1/I2. Slice B/C may add evidence keys only with CONFIG + example INI.

## 7. Suggested next action

1. I3 code path is wired. Live listen is not a merge gate.
2. Remaining to ship: PR to `master` (`semver:minor`) and restart the local service.
