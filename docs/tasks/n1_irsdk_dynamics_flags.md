# N1 — iRSDK Speed, rival lap times, flag decode

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §2.2  
**Base:** umbrella #179 only (not “parallel with P0”)  
**Blocks:** N3 (Speed), N4 (flags copy), N5 (decode), N6b (CarIdx times)

## Context

Aftermath crawl/roll needs `Speed`. Hunt-by-time needs **official** `CarIdxBestLapTime` (disconnected = `-1`). Flags need a decoder; the int is already on the snapshot. Policy stays out of `iracing/`.

**Not landing:** Yaw / accel / steering (5 Hz cannot support lost-control product).

## Owns

- `iracing/sdk_units.py` + `tests/test_sdk_units.py` — **add** `as_speed_mps` here (helpers already live in this module; `as_speed_mps` does **not** exist yet). 0 is valid; negative / non-finite → None
- `iracing/telemetry.py` `TELEMETRY_VARS` + extract (`Speed`, `CarIdxBestLapTime`, `CarIdxLastLapTime`)
- `iracing/reader.py` duplicate var lists (`common_vars` and `read_mode` fallback) — add the same names so fallback reads do not drop Speed / CarIdx times / SessionFlags
- `overlay/models.py` additive snapshot **and** `RaceState` fields
- `race/context.py` **must** copy: `speed_mps`, `session_flags` (raw int + decoded bits used by N4/N5), `car_idx_best_lap_time`, `car_idx_last_lap_time`
- new `iracing/session_flags.py`
- tests (`test_race_context.py`, new `test_session_flags.py`)

Must not: emitters, director, `runtime.py`, invent DriverInfo lap times, Yaw/accel.

## Acceptance criteria

- [ ] Extract `Speed` via `as_speed_mps` in `sdk_units.py` (0 valid, negative → None). Field name on snapshot/`RaceState`: **`speed_mps`**
- [ ] Extract `CarIdxBestLapTime` / `CarIdxLastLapTime` via existing `as_completed_lap_time` per slot (`-1` / 0 → None)
- [ ] `session_flags.py` maps official `irsdk_Flags` bits; unknown ignored
- [ ] Missing keys stay None; extract never raises
- [ ] `RaceState` has the new fields (not snapshot-only)
- [ ] Unit tests: bits, combined flags, sentinel Speed/times, empty extract, `as_speed_mps` table
- [ ] No speak / no HUD behavior change

## Test plan

- [ ] Each documented flag bit → name
- [ ] `CarIdxBestLapTime` `-1` → None in tuple
- [ ] Existing telemetry / race-context tests pass

## Docs impact

- [ ] Epic §2.2 checkbox
- [x] CONFIG / API — no

## Config impact

None.
