# Spec: SoF card + Race remaining (follow-up)

**Status:** draft — implement **after** Event Engine V4 remainder (#114)  
**Branch suggestion:** `cursor/ee-sof-remain-65db`  
**Out of scope for #114:** no code from this spec lands in the remainder PR.

---

## 1. Product intent

Two new overlay beats for race context:

1. **SoF** — show Strength of Field when the driver enters the car / joins on-track, and/or on pit-lane entry.  
   Multiclass: **class SoF large**, overall SoF underneath.
2. **Race remaining** — after early race progress (e.g. ≥ 2 completed laps), show how much session is left:  
   laps, clock time, and/or predicted time-to-finish / laps-to-finish depending on session format.

Anti-spam: each beat is a short RESULT/ACTIVE story with cooldown; not every telemetry tick.

---

## 2. Triggers (v1)

### 2.1 SoF

| Trigger | When | Notes |
| --- | --- | --- |
| **Car entry** | Rising edge: player becomes on-track (surface / not in garage) after being out | Prefer once per session join |
| **Pit entry** | Existing pit FSM `pit_entry` ENTER (or shared edge) | Optional second surface; product may enable one or both via flags |

**Flags (proposed):**

```ini
[event_engine]
sof_card = false
sof_on_car_entry = true
sof_on_pit_entry = false
```

Defaults off until product sign-off.

### 2.2 Race remaining

| Trigger | When | Notes |
| --- | --- | --- |
| **Progress gate** | `lap_completed >= N` (default **N = 2**) in `overlay_mode=RACE` | Emit once, then cooldown |
| **Optional refresh** | Every M laps or every T seconds after first show | v1: **once per session** is enough |

**Flags (proposed):**

```ini
[event_engine]
race_remain = false
race_remain_after_laps = 2
race_remain_cooldown_sec = 120
```

---

## 3. Data sources

### 3.1 Already available

| Field | Source | Use |
| --- | --- | --- |
| `SessionLapsRemain` | telemetry (already extracted) | Lap-limited remaining |
| `lap_completed` / `lap` | telemetry → `RaceState` | Progress gate |
| `on_pit_road` + pit story | existing pit FSM | Pit entry trigger |
| `overlay_mode` | session coordinator | Race-only remain |

### 3.2 To add

| Field | Source | Use |
| --- | --- | --- |
| `SessionTimeRemain` | iRacing telemetry var | Time-limited remaining |
| Driver iRatings + class | Session Info `DriverInfo` (YAML) | Compute SoF |
| Player class id | already `PlayerCarClass` / class arrays | Multiclass split |
| Session format | Session Info (`SessionLaps` / `SessionTime` / unlimited) | Pick copy + metrics |

**SoF computation (v1):**

- Collect drivers in session with valid iRating (exclude spectator/empty).  
- **Overall SoF** = mean iRating of all racing drivers (product may later switch to official Sof formula if documented).  
- **Class SoF** = mean iRating of drivers with `CarClassID == player class`.  
- Multiclass when ≥ 2 classes with ≥ 1 driver each; else show single SoF only.

Document the exact formula in CONFIG when implementing; keep deterministic and unit-tested.

**Predicted finish (time races):**

- `predicted_laps_to_finish ≈ ceil(SessionTimeRemain / avg_lap)` where `avg_lap` = rolling mean of valid completed lap times (fallback: best lap × 1.02).  
- `predicted_finish_clock` optional later; v1 can show time remain + estimated laps.

---

## 4. Events & presentation

Reuse **existing V4 families** — no new plate art required for v1.

### 4.1 Catalog states (proposed)

| State id | Family | Lifecycle | Primary metrics |
| --- | --- | --- | --- |
| `sof` | `session` (or `timing`) | RESULT (~4–6 s) | `sofClass`, `sofOverall`, `multiclass` |
| `race_remain` | `session` | RESULT (~4–6 s) | `mode` (`laps`\|`time`\|`hybrid`), `lapsRemain`, `timeRemainSec`, `predictedLaps` |

Icons: **reuse** `session` / timing icons in v1; optional dedicated PNG later.

### 4.2 Copy (EN base; CS in same PR)

**SoF (single class):**

- title: `STRENGTH OF FIELD`  
- value: ` sofOverall ` (e.g. `2840`)  
- meta: session / class name if cheap

**SoF (multiclass):**

- title: `CLASS SOF`  
- value: ` sofClass ` (large)  
- subtitle/meta: `OVERALL  sofOverall `

**Race remain — lap race:**

- title: `LAPS TO GO`  
- value: ` lapsRemain ` (integer display)  
- meta: optional total / completed

**Race remain — time race:**

- title: `TIME LEFT`  
- value: `mm:ss` from `timeRemainSec`  
- meta: `~N LAPS TO FINISH` when prediction confident

**Race remain — hybrid / unknown:**

- Prefer whichever SDK remain value is valid; if both, show time + laps in value/meta.

i18n via `copy.*Token` only — no baked text in assets.

### 4.3 Wire shape

Standard V4 envelope (`format: "v4"`, phases RESULT). Metrics JSON only; renderer uses existing `fillSessionCopy` / small extension.

---

## 5. Architecture touchpoints

| Layer | Change |
| --- | --- |
| `iracing/telemetry.py` | Add `SessionTimeRemain` to `TELEMETRY_VARS` + snapshot field |
| Session Info adapter | Parse `DriverInfo` iRatings / classes; cache per session key |
| `RaceState` | Optional: `session_time_remain`, `sof_overall`, `sof_class`, `session_format` |
| New emitters | `SofEmitter`, `RaceRemainEmitter` (fail-soft, `reset()` on session key) |
| `EventEngine` / runtime | Register behind flags |
| Adapters | Map candidates → V4 envelopes + catalog states |
| `event_catalog.json` | +2 entries |
| Golden | +2 fixtures (reuse family layers) |
| Replay | +1–2 scenarios |
| CONFIG.md / flags | Document defaults off |
| i18n EN+CS | Tokens for titles/meta |

Layer rules unchanged: `iracing/` extraction only; decisions in `logic`/emitters; `obs/` untouched.

---

## 6. Graphics decision

**Yes — use current V4 graphics for v1.**

- Plate / layers / motion: existing `session` (preferred) or `timing` family.  
- No new glow/plate PNGs required.  
- Optional later: dedicated SoF / clock icons under `session/icons/`.

Do **not** invent a new family unless layout needs two simultaneous persistent widgets (v1 = transient RESULT cards).

---

## 7. Acceptance criteria

- [ ] Flags default **off**; no behavior change when off  
- [ ] SoF shows once per configured trigger; multiclass layout correct when ≥2 classes  
- [ ] Race remain fires after N laps in RACE; shows laps and/or time correctly for lap vs time sessions  
- [ ] Predicted laps only when avg lap is valid; otherwise omit meta  
- [ ] Golden fixtures + catalog + i18n EN/CS  
- [ ] Replay scenario(s) green  
- [ ] Per-emitter fail-soft + session reset  
- [ ] Docs: CONFIG.md flag block + short API/metrics note  

---

## 8. Non-goals (v1)

- Official iRacing Soft formula reverse-engineering beyond documented mean-iRating approach (unless product supplies formula)  
- Persistent SoF HUD / always-on remain counter  
- New theme art pack  
- S3d / legacy removal  
- Bio composure / high_load  

---

## 9. Suggested implementation order

1. Telemetry `SessionTimeRemain` + RaceState plumbing + tests  
2. Session Info iRating extract + SoF helper (unit tests)  
3. `SofEmitter` + flag + adapter + catalog + golden  
4. `RaceRemainEmitter` + prediction helper + catalog + golden  
5. Replay scenarios + CONFIG/i18n polish  

---

## 10. Open product questions

1. SoF on **car entry only**, **pit only**, or both?  
2. SoF formula: simple mean iRating OK for v1?  
3. Remain: once per race vs refresh every N laps?  
4. Multiclass: always show overall line, or only when classes differ by > threshold?  
