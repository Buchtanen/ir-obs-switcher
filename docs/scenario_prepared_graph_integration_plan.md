# Integration plan — Track Excursion (#216) + prepared graph (#217)

**Branch:** `feat/scenario-and-prepared-graph`  
**Base:** `origin/master` @ `2fafdd2` (N12, stateful sequence graph, SuperTonic, sampling spec, INFO `llm_polish` tape)  
**Issues:** [#216](https://github.com/Buchtanen/ir-obs-switcher/issues/216), [#217](https://github.com/Buchtanen/ir-obs-switcher/issues/217)  
**Status:** plan only — no runtime work on this branch yet

This is the living index. Detailed contracts stay in the #216/#217 docs once I0 lands them from [#226](https://github.com/Buchtanen/ir-obs-switcher/pull/226).

## 1. Why this branch exists

#216 and #217 were implemented on `codex/fix-overlay-commentary-test-7`, now stacked in
`feat/commentary-finish-episodes` (PR #226). **None of that runtime is on `master`.**

Starting 216/217 from bare master would rewrite a tested stack. This branch is the
integration line: absorb #226 first, then finish the remaining slices.

Do not implement #216 remainder or #217 leftover against current master.

## 2. What is already done (on #226, not master)

### #216 — native Track Excursion subset

Wired: `RaceState → TrackExcursionDetector → RaceObserver → N12 → graph v3 → Director → MiniStory → TTS`.

Spoken facts: off-track, stopped, rejoin, motion restored, Race tow, driven pit, S7a pace
loss / normal running. `[race_scenarios] mode=legacy|shadow|active` (dev default `active`).
Numeric INCIDENT points-only. Vocabulary gates. Episode/parent identity.

Not production: generic `ScenarioEngine` + JSON `track_excursion_story/v1` as the sole publisher.

### #217 — prepared graph (automated cut claimed complete on Test 7)

53-node core + graph v4 contracts, plan builder/scoring off the generic gateway, EN/CS
anchors, relation/forbidden-claim validation, fatal node, current/next reservation.
`prepared_filler.mode` default `active` on that branch.

Remaining: audible stream-PC matrix (`docs/commentary_prepared_active_test.md`). Issue AC
checkboxes were never closed.

Canonical files (exist only on #226 until I0):

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

I0 exit:

- [ ] This branch contains `prepared_filler.py`, `events/scenarios/track_excursion.py`, and the six docs above
- [ ] Focused pytest green: excursion + prepared + n12 consumers
- [ ] #215 / #218 close with #226 (lifecycle + live place) — they are dependencies, not this plan
- [ ] Local `master` / this branch match the absorbed tip

Until I0 is done, do not start I1–I3 code.

## 4. After I0 — remaining implementation

Work is sequential on shared files (`observer.py`, `director.py`, `consumer.py`,
`sequence_graph.json`, `ministory.py`). Do not parallelize 216 vs 217 on those paths.

### I1 — #217 live acceptance (short)

Code cut is claimed done. This is evidence, not a second graph.

- [ ] Run `docs/commentary_prepared_active_test.md` on the stream PC (`active`)
- [ ] Tape shows concrete `preparedNodeId`, never generic `prepared_filler` for new plans
- [ ] Missing facts shorten the chain; start-ready/set stays short; live/critical still outrank prepared
- [ ] Close #217 AC or list the exact residual defects (no silent “almost”)

If the audible matrix finds a contract hole, fix it here before I2. Do not open #222/#223 on this branch.

### I2 — #216 live acceptance of the native subset

- [ ] Evidence pack from `docs/track_excursion_live_test.md`: HEAD, `/health`, overlay `?v=`, `[race_scenarios] mode`, tape, video
- [ ] Practice/Race off-track + rejoin + optional S7a; no generic incident prose; FINISH still wins
- [ ] `motion_restored` ≠ control regained; no slide/spin/contact/damage nouns

This is slice A from the 2026-09-05 #216 remainder comment. No new causes.

### I3 — #216 remainder (only after I2)

**Slice B — one publisher**

- [ ] Production path: composite `track_excursion_story/v1` through named guards/actions only
- [ ] Native detector becomes a feature source or `legacy`; no dual speaking publishers
- [ ] `legacy|shadow|active` fail-soft; shadow publishes no new scenario facts
- [ ] Replay of the I2 tape is bit-stable vs the native subset for connected facts

**Slice C — taxonomy (blocked on data)**

Do not speak these until each has an evidence contract (source, sentinel, abstention):

| Runtime ID | Why it is missing |
| --- | --- |
| `LOSS_OF_CONTROL` | No calibrated steering-vs-path detector |
| `SLIDE` / `SPIN` | Yaw / sideslip thresholds not calibrated per car class |
| `CONTACT_VEHICLE` / `CONTACT_BARRIER` | Nearby car + incident-count jump ≠ contact type |
| `BRAKING_OVERSHOOT` | No trusted local braking reference |
| `AVOIDANCE_MANEUVER` | Conflict + evasive pattern not proven |
| `CONTROL_REGAINED` | Distinct from `MOTION_RESTORED` |
| `DAMAGE_*` / `PIT_FOR_REPAIRS` | Pace loss ≠ damage |
| `RESET_TO_PITS` | Practice/Qualify ESC/teleport not classified |

Missing evidence stays `CAUSE_UNKNOWN` / omitted noun. No invented cause in graph, LLM, or TTS.

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

1. Rebase and merge #226 onto current `master`.
2. `git rebase origin/master` on this branch.
3. I1 then I2 (listen), then I3 only with data.
