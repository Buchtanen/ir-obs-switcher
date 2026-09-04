# Prepared commentary — active private-stream acceptance

## What this test proves

The live matrix is an operational acceptance run on the actual streaming PC. It is not a
replacement for pytest. Unit/replay tests prove deterministic state transitions and data guards;
this run proves that real OBS edges, iRacing timing, the configured Ollama model, Windows TTS
queueing and machine load behave together.

In `active`, the prepared pipeline builds facts, pre-generates current/next-stage variants,
validates them, selects a graph winner and sends it to TTS. This is intentionally an audible test
on a private broadcast: failures are evidence to retain and fix, not a reason to route the test
through legacy commentary first.

Each winner must name one of the concrete prepared graph nodes. A `prepared_filler` winner is a
failure of the migration; `graph_contract_missing` is a fail-soft defect that must be retained and
fixed. The matrix also checks raw-source normalization: absent circuit/weather/
roster/start fields shorten the optional chain and must never be replaced by guessed copy.

## Required configuration and evidence

Use a non-production test stream with:

```ini
[overlay]
session_tape = true

[commentary]
enabled = true

[commentary.prepared_filler]
mode = active

[commentary.graph_runtime]
mode = active
```

Set the runtime log level to `DEBUG` for the acceptance run so commentary comparison rows are
retained and `prepared_filler.generated.acceptedTexts` is available for the factuality audit. At
INFO this field is removed before writing the tape. Keep together:

1. the exact config and build/commit identity;
2. the OBS recording or private VOD;
3. all `recordings/overlay-*.jsonl` files from the run;
4. `/api/commentary/status` snapshots at lobby, in-car, green, conclusion and after stop;
5. timestamps and a short operator note for every injected failure.

Generated text, prompts and OAuth tokens must not be copied into an issue or ordinary INFO logs.
The retained acceptance package may contain spoken/generated commentary and must be handled as
test data.

## Scenario matrix

| ID | Situation | Operator action | Required observation |
| --- | --- | --- | --- |
| S1 | Practice opening | Start OBS in the lobby, wait for context, then enter the car | Prepared commentary is audible; current and next-stage counts become ready; Practice intro drains deterministically |
| S2 | Practice out laps | Leave pits twice, completing one lap first and returning/towing on the second | Exactly one out-lap epoch per pit exit; first closes at S/F, second closes on pit/tow; old plans never win |
| S3 | Qualifying cutover | Start in lobby and enter Qualifying before the stream intro completes | Current utterance may finish; remaining intro plans expire; event-intro/out-lap plans are already prefetched |
| S4 | Qualifying result | Finish with a known class position | Result uses pole/podium/top/middle/rear band from class size; no live position is called final before confirmation |
| S5 | Rolling race start | Reach ParadeLaps and green | Formation candidates are prefetched; no long prepared winner after the start guard; green/live events remain authoritative |
| S6 | Standing race start | Reach ready/set/green | Prepared filler yields to start/green; no stale grid unit begins after green |
| S7 | Race result comparison | Finish better, equal or worse than the same-stream Qualifying position | Win/podium wins first; otherwise the correct `gain/hold/loss_vs_quali` branch appears |
| S8 | Missing result identity | End P/Q without a confirmed result snapshot | No last-live-position result; after eight seconds only the generic unconfirmed close becomes eligible |
| S9 | iRacing disconnect | Disconnect while two generations are active | Generation count reaches zero, current speech may finish, queued old speech and plans disappear; reconnect creates a fresh scope |
| S10 | Run/session reset | Restart a run and then change session while one unit speaks and one waits | Speaking unit finishes; waiter and LLM jobs are cancelled; `run_epoch`/stage scope changes; no old completion closes the new stage |
| S11 | OBS stop/start | Stop while generation and TTS are active, then start again | TTS is hard-interrupted, buffer/tasks/exposure clear, status is `INACTIVE`; new start increments `stream_epoch` |
| S12 | LLM/source failures | Timeout Ollama, return invalid JSON, revoke/disable YouTube | Ready buffer remains usable; empty exhausted buffer says the fatal notice once and then stays silent; YouTube failure never becomes core fatal |
| S13 | Rollback | Reload `active -> legacy -> active` in the controlled private run | Each change cancels incompatible tasks; `legacy` restores legacy filler and `active` resumes prepared playback without service restart |
| S14 | Service/worker restart | Restart the service, then exercise a forced consumer recovery | No orphan TTS/LLM task; prepared generation becomes ready again on the same supervisor-owned consumer instance |

## Evidence to evaluate after the run

Retained evidence should show:

- zero spoken winners from an expired stream/session/run/stage/stint/class scope;
- zero prepared winner that would displace an accepted live occurrence/story;
- `readyPlans <= max_ready_plans` and `inflight <= max_inflight` throughout the run;
- exactly one exposure at `speaking`, never at generation, selection or queueing;
- every unexpected spoken/silent decision classifiable from the tape;
- every stop/reset/disconnect leaves no old generation or queued speech;
- LLM fatal, optional-source failure and immediate `legacy` rollback match the documented contract.

A failed row is not tuned away during the same run. Retain the evidence, classify it as factuality,
freshness, priority, lifecycle, capacity or operations, change one documented policy, and repeat the
affected row plus the regression rows S9–S13.
