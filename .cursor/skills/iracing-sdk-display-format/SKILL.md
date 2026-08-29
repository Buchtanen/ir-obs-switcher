---
name: iracing-sdk-display-format
description: >-
  Formats iRacing SDK (iRSDK) telemetry for HUD display: lap times, deltas, gaps,
  session clocks, sentinels (-1, 32767, 604800), and SimHub-compatible m:ss.fff.
  Use when working on overlay copy, telemetry extraction, lap/battle metrics,
  iRSDK units, SimHub formatting, LapCurrentLapTime, LapLastLapTime, SessionTime,
  LapDistPct, or weird raw numbers on the overlay.
---

# iRacing SDK display format

## Rule

**Wire JSON stays in SDK units. Format only in the HUD.**

- Seconds stay `float` in `metrics` (`lapTime`, `gap`, `deltaToBest`, `SessionTime`).
- Do not send `"1:52.084"` over WS.
- Python: `irswitch.iracing.sdk_units`
- JS: `src/irswitch/web/overlay/js/timing-format.js` (keep in sync)

## Why values looked broken

iRSDK times are **seconds**, not clock strings. Invalid times are often **-1.0** (sometimes **0** for best/last before the first lap). Displaying that raw gives `94.372` or `59.000` instead of `1:34.372`.

SimHub does the same conversion the F3 box uses:

```
format(secondstotimespan(seconds), 'm\:ss\.fff')
```

Invalid → placeholder (`—`), same idea as SimHub replacing `0:00:000` with `-:--:--`.

## Display formats

| Kind | Example in | HUD |
|------|------------|-----|
| Lap / projected / best | `112.084` | `1:52.084` (always `m:ss.fff`, unpadded minutes, including `0:45.100`) |
| Delta to best / sector | `-0.318` | `-0.318` / `+0.318` (3 decimals, signed) |
| Battle gap | `1.91` | `1.91 s` |
| Closing rate | `0.42` | `0.42 s/s` |
| SessionTime / remain | `3847.2` | `1:04:07` (`h:mm:ss` or `m:ss`) |
| Pit stopwatch | `12.4` | `12.4 s` (elapsed seconds, not lap format) |

Round via **total milliseconds** so `59.9996` → `1:00.000`, never `60.000` with no minute carry.

## Sentinels (drop → `None` / `—`)

| Value | Meaning | Fields |
|-------|---------|--------|
| `-1` (or `< 0`) | Not valid / not in world | times, `LapDistPct`, `CarIdxEstTime`, lap counts |
| `0` | Unset **completed** lap | `LapLastLapTime`, `LapBestLapTime` only. `LapCurrentLapTime` **0 is valid**. |
| `32767` | Unlimited laps | `SessionLapsRemain`, `SessionLapsRemainEx` |
| `604800` | Unlimited time (7 days) | `SessionTimeRemain` |
| Position `0` | Not in results | `PlayerCarPosition`, `CarIdxPosition` |

`as_float` in `telemetry.py` only strips huge sentinels (`<= -10000`). **Do not** treat every `-1` as missing (FPS, temps). Use `sdk_units` helpers per field.

## Units people mix up

| Var | Unit | Not |
|-----|------|-----|
| `Lap*Time`, `SessionTime`, `CarIdxEstTime`, `CarIdxF2Time` | seconds | clock strings; EstTime is **track time**, not gap |
| `LapDistPct` / `CarIdxLapDistPct` | **0–1** fraction | 0–100 percent |
| Speed (if ever shown) | m/s | km/h (`* 3.6`) |
| Gaps we compute | seconds from distance × ref lap | do not print `CarIdxEstTime` as interval |

Official var list: [sajax irsdkdocs](https://sajax.github.io/irsdkdocs/telemetry/). SimHub NCalc: `secondstotimespan` / `timespantoseconds` / `format`.

## Checklist when adding a telemetry field to the HUD

1. Confirm unit on irsdkdocs (do not guess).
2. Sanitize with the matching `sdk_units` helper in `extract_telemetry`.
3. Keep the number in the envelope; call `fmtLapTime` / `fmtDelta` / `fmtGap` / `fmtSessionClock` in the renderer.
4. Add a test in `tests/test_sdk_units.py` for the sentinel + the HUD string.
