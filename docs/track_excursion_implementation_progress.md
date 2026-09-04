# Track Excursion — implementation progress

Status: current-signal subset connected for **active development testing**, not the complete
composite taxonomy and not yet a validated Windows/OBS deployment.

Tracking: [#216](https://github.com/Buchtanen/ir-obs-switcher/issues/216).
Base: `codex/fix-overlay-commentary-test-7`, `4497040`.
The user's 2026-09-03 instruction approves connecting first, logging, then evaluating; the
earlier legacy-default/shadow-first activation sequence is superseded for this subset.

## Connected vertical slice

- Native `TrackExcursionDetector` consumes `RaceState` through `RaceObserver`.
  It emits off-track, stopped, track rejoined, renewed motion, Race tow and observed pit return.
  Incident points do not trigger or gate the excursion. Independent time-based holds and strict
  session/run/hero identity prevent duplicate or cross-run recovery.
- Modes: `[race_scenarios] mode=active|shadow|legacy`; development default **active**.
  Active disables the legacy aftermath watcher; shadow does not publish new facts.
  Numeric `INCIDENT` speech uses the `points` branch without changing the HUD wire payload.
- Shared immutable `EpisodeScope` / `ScenarioBeat` contracts produce distinct beat correlations
  under one parent. `RacePipeline` assigns accepted identity before fanout.
- Production graph v3 has six new factual nodes with parent-scoped direct/indirect closure paths.
  Director and composer pass typed selectors and check parent/session/run/hero identity.
- Scenario deferral holds at most one current beat, including with legacy graph scoring.
  New phases invalidate uncommitted old phases; current context can cancel stale pending
  stop/rejoin/motion claims. Already audible phases are not interrupted by ordinary developments.
- Authored, composed, LLM and final TTS vocabulary gates enforce off-track wording and exclude
  unsupported cause/damage words. Generic incident prose became numeric point-delta copy.
- Change-based observation, detection/invalidation and correlated TTS diagnostics enter the
  session tape at INFO. Other commentary and LLM detail remain DEBUG-only.

Exact guards, limitations, configuration and manual acceptance procedure:
[the live test contract](track_excursion_live_test.md).

## Foundation retained

- Deeply immutable evidence/guard/beat contracts, explicit UNKNOWN, scoped episode identities.
- Strict data-only atomic loader with named registries, reachability, finite time/confidence
  checks and duplicate JSON-key rejection.
- Injected-time atomic FSM kernel: ordered transitions, temporal holds, bounded facts/traces,
  transactional rollback, invalidation, disconnect grace and no ID reuse.
- Graph-v3 typed eligibility, confidence thresholds, episode semantics and explicit edge identity;
  graph v1/v2 documents remain loadable.
- Optional CandidateEvent fields exist but are not the live adapter: this slice uses the
  observer's commentary-only derived-envelope path.

The native subset **does not execute the generic atomic kernel or design JSON yet**.
Loader registry membership is not executable handler readiness. No SDK extraction or dependency
was added.

## Remaining work

| Area | Status / next evidence |
| --- | --- |
| S0 / S7 Test 7 13:44 | Original tape absent locally; video timing not verified |
| S1 / P1 generic engine | Foundation tested; composite schema/compiler and production bindings unfinished |
| S2 current signals | Connected subset; no proven Practice/Qualify ESC, repairs or prolonged damage follow-up |
| S3–S6 wiring / graph / rollout | Connected for development; synthetic E2E passes; real test/comparison pending |
| S8–S9 / P4–P7 causes and pace | No slide/spin/contact/braking/avoidance/damage classifier or calibrated confidence |

`motion_restored` is not `control_regained` or `normal_running_resumed` and currently closes the
small observable episode. `pit_return_observed` is not `pit_for_repairs` or `reset_to_pits`.
Timeout and lost evidence invalidate silently, not as asserted physical outcomes.

## Evidence

Final connected-slice verification (2026-09-03): **1,512 tests passed**, Ruff PASS,
Black PASS (336 files), Mypy PASS (183 source files), tracked diff whitespace check PASS.
Cases cover final TTS vocabulary, correlated tape, waiting-speech cancellation, change-only
logging, renewed excursions and FINISH arriving before a pending lower-tier story is flushed.

Tests began with a failing missing-detector import. Synthetic integration traverses observer,
N12 producer/consumer and fake TTS in both legacy and active graph scoring, including a busy sink.
No real iRacing/OBS connections or audible output are used. These tests do not establish empirical
precision/recall or reproduce video 13:44.

TDD-exception: Windows/iRacing/OBS live listening cannot be performed in this checkout.
Alternative verification: documented manual test with video + session tape + build/config identity.
Risk: real telemetry timing and TTS latency differ; mitigation: correlated logs, explicit unknowns,
bounded temporal guards and the legacy detector switch.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m black --check src tests
.venv/bin/python -m mypy src
git diff --check
```
