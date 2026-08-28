# Plan: SoF card + Race remaining

**Status:** ready to implement **after** Event Engine V4 remainder (#114) merges  
**Spec (product contract):** [`EVENT_ENGINE_V4_SOF_REMAIN_SPEC.md`](EVENT_ENGINE_V4_SOF_REMAIN_SPEC.md)  
**Suggested branch:** `cursor/ee-sof-remain-65db` (base: `master` after #114)  
**Out of scope here:** S3d legacy removal, bio composure/high_load, new theme art pack

This plan turns the spec into ordered work packages with file touchpoints, tests, and merge gates. Do not start until #114 is signed off or explicitly parallelized on a clean branch from post-#114 master.

---

## 0. Preconditions

- [ ] #114 merged (or branch rebased onto its merge commit)
- [ ] Product answers from spec §10 (or accept v1 defaults below)
- [ ] Flags ship **default off**

**v1 defaults if product silent:**

| Question | Default |
| --- | --- |
| SoF trigger | car entry only (`sof_on_pit_entry=false`) |
| SoF formula | mean iRating of racing drivers |
| Race remain | once per race after `lap_completed >= 2` |
| Multiclass | always show overall line under class SoF |

---

## 1. Work packages

### P1 — Telemetry + RaceState plumbing

**Goal:** `SessionTimeRemain` and session-format hints available to emitters.

| Change | Path / notes |
| --- | --- |
| Add `SessionTimeRemain` to `TELEMETRY_VARS` + snapshot | `src/irswitch/iracing/telemetry.py` |
| Plumb into `RaceState` (or session snapshot field) | `logic/` race/session state |
| Unit tests: missing var → `None`, present → float seconds | `tests/` |

**Done when:** emitters can read time remain without Session Info parse.

---

### P2 — DriverInfo iRating extract + SoF helper

**Goal:** deterministic overall + class SoF from Session Info.

| Change | Path / notes |
| --- | --- |
| Parse `DriverInfo` iRatings / `CarClassID` (cache per session key) | session-info adapter under `iracing/` |
| Pure helper `compute_sof(drivers, player_class_id) → SofResult` | `logic/` (no I/O) |
| Multiclass detect: ≥2 classes with ≥1 driver | same helper |
| Unit tests: empty, single class, multiclass, spectators excluded | `tests/` |

**Done when:** helper covered; no EventEngine wiring yet.

---

### P3 — `SofEmitter` + adapter + catalog + golden

**Goal:** RESULT card for SoF behind flags.

| Change | Notes |
| --- | --- |
| Flags | `sof_card`, `sof_on_car_entry`, `sof_on_pit_entry` (CONFIG.md) |
| Emitter | rising-edge car entry; optional pit_entry; `reset()` on session key; fail-soft |
| Adapter → V4 envelope | family `session` (preferred); state id `sof` |
| Catalog + i18n EN/CS | titles/meta tokens only |
| Golden fixture | reuse session layers; multiclass + single-class variants if cheap |
| Register in EventEngine | only when flag on |

**Copy:** spec §4.2.

**Done when:** golden shows SoF; flag off = no emit.

---

### P4 — `RaceRemainEmitter` + prediction + catalog + golden

**Goal:** RESULT card after N laps in RACE mode.

| Change | Notes |
| --- | --- |
| Flags | `race_remain`, `race_remain_after_laps=2`, `race_remain_cooldown_sec` |
| Emitter | gate on `overlay_mode=RACE` + laps; once/session v1 |
| Prediction helper | `ceil(time_remain / avg_lap)` when avg valid; else omit |
| Session format pick | laps / time / hybrid → copy mode |
| Catalog state `race_remain` | family `session` |
| Golden | lap-limited + time-limited fixtures |
| i18n EN/CS | `LAPS TO GO` / `TIME LEFT` / predicted meta |

**Done when:** both formats covered in tests + golden.

---

### P5 — Replay + docs + DoD

| Change | Notes |
| --- | --- |
| Replay scenarios | +1 SoF, +1 race remain (or combined) |
| CONFIG.md | flag block + SoF formula note |
| API.md / CHANGELOG | short metrics note if public |
| Cross-link | remainder plan §12 already points at spec; add plan link |

**Done when:** replay green; docs match flags.

---

## 2. Suggested PR sequence

Prefer **one branch / one PR** if small; else split:

1. **PR-A:** P1 + P2 (data only, no UX)  
2. **PR-B:** P3 SoF  
3. **PR-C:** P4 + P5 remain + polish  

Do not open S3d on the same branch.

---

## 3. Layer rules (non-negotiable)

- `iracing/` — extraction only (telemetry vars, Session Info parse)
- `logic/` / emitters — decisions, cooldowns, SoF math
- `obs/` — untouched
- `server/` — glue / flag registration only
- Async-first; emitters fail-soft; never crash main loop
- No new dependencies

---

## 4. Graphics

- Reuse V4 **session** (or timing) family plates — **no new art for v1**
- Optional later: dedicated `sof.png` / clock icon under `session/icons/`
- cyber_racing icon wells already recentered to glyph mid (post-#114 fix); new icons must be authored on 420×140 with glyph center ~(62, 70)

---

## 5. Acceptance checklist (merge gate)

- [ ] All new flags default **false** / documented
- [ ] SoF: single-class + multiclass layout correct
- [ ] Race remain: lap vs time session copy correct; prediction omitted when avg invalid
- [ ] Catalog + golden + i18n EN/CS
- [ ] Replay scenario(s) green
- [ ] Emitter `reset()` on session change; fail-soft
- [ ] Ruff/black/mypy + targeted pytest green
- [ ] No S3d / no bio composure/high_load scope creep

---

## 6. Estimation (technical, not calendar)

| Package | Invasiveness | Risk |
| --- | --- | --- |
| P1 | Low — one telemetry var + plumbing | Low (SDK field may be absent in some sessions) |
| P2 | Medium — Session Info YAML shape | Medium (driver list edge cases) |
| P3 | Medium — emitter + adapter + catalog | Low if flags off |
| P4 | Medium — format branching + prediction | Medium (hybrid sessions) |
| P5 | Low — replay/docs | Low |

Highest risk: Session Info iRating coverage and hybrid remain display — keep prediction optional and copy conservative.

---

## 7. Kickoff commands (when starting)

```bash
git fetch origin master
git checkout -b cursor/ee-sof-remain-65db origin/master
# implement P1 first; keep flags off until P3/P4 adapters land
```
