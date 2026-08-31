# N1 — iRSDK dynamics + session-flag decode

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md)  
**Depends on:** none (can start in parallel with P0/P1)  
**Blocks:** N3, N4, N5  
**Branch hint:** `feat/irsdk-dynamics-flags`  
**Issue:** create after plan approval

## Context

Incident classification, aftermath (stopped vs rolling), and flags need telemetry we do not extract today. `SessionFlags` is already on the snapshot but has no decoder. Policy stays out of `iracing/`.

## Owns / must not touch

- **Owns:** `src/irswitch/iracing/telemetry.py` (`TELEMETRY_VARS` + extract), `src/irswitch/overlay/models.py` additive fields on `TelemetrySnapshot` (and pass-through on `RaceState` if required), new `src/irswitch/iracing/session_flags.py`, tests  
- **Must not:** `events/`, `commentary/`, `overlay/runtime.py`, emitters

## Acceptance criteria

- [ ] Extract official vars: `Speed`, `Yaw`, `YawRate`, `VelocityX`, `VelocityY`, `LatAccel`, `LongAccel` (optional `SteeringWheelAngle`) with `sdk_units` / sentinel handling  
- [ ] Optional same PR if cheap: `CarIdxBestLapTime` / `CarIdxLastLapTime` tuples (needed by N6 pace-hunt — **only if** present in official var list; skip rather than guess)  
- [ ] `session_flags.py` maps known bits (checkered, white, green, yellow, yellowWaving, red, blue, caution, cautionWaving, black, disqualify, repair, startHidden/Ready/Set/Go) → frozen names; unknown bits ignored  
- [ ] Missing keys stay `None`; extract never raises  
- [ ] `RaceContextAnalyzer` copies new fields onto `RaceState` if downstream watches need them (additive only)  
- [ ] Unit tests: bit decode, sentinel Speed/yaw, missing vars  
- [ ] No speak / no HUD behavior change  

## Test plan

- [ ] Unit: each documented flag bit → name set  
- [ ] Unit: combined bits (green+checkered etc.)  
- [ ] Unit: `extract_telemetry` with only a subset of keys  
- [ ] Existing telemetry / race-context tests still pass  

## Docs impact

- [ ] `docs/narrative_observers_epic.md` §2 status note  
- [ ] This task file checkbox  
- [x] README / CONFIG / API — no (extract only)  

## Config impact

None.
