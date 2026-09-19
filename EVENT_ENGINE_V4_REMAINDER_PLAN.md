# Event Engine + Overlay V4 — remainder plan (post S3a/b/c)

**Branch base:** `master`  
**Status:** in progress on `cursor/ee-v4-remainder-65db` (single branch, merge when whole complete)  
**Inputs:** `EVENT_ENGINE_V4_PARALLEL_PLAN.md` §7 Definition of done, merged T1–T5 + S3a/b/c  
**Constraint:** **S3d is last** — no legacy removal until all prior gates are green.

### 0.1 Product decisions (2026-08-28)

| Decision | Verdict |
| --- | --- |
| **#111** demo JS hotfix | **Merged** |
| **R0** golden glow clip | **Approved** — PR #113 |
| **SYSINFO** | **Full V4 renderer required** for v1 (1920×72, no V3 waiver) |
| **Bio emitters** `composure_test`, `high_load` | **Deferred beyond v1** — no emitter, no catalog entry, no replay scenario in v1 |
| **Bio v1 scope** | `hr_pressure` + `ble_reconnecting` only (shipped) |

**Bio deferral rationale:** `HrPressureEmitter` already covers live `pushing`/`high` via `hr_pressure`. `composure_test` (post-battle elevated BPM) and `high_load` (extreme relative surge) need new correlation logic (battle EXIT + hysteresis, absolute threshold). Assets + manifest samples stay for future; not wired in v1.

---

## 0. Snapshot (what is done)

| Area | Status |
| --- | --- |
| T1 Platform | Envelope, manager v2 skeleton, flags, i18n EN+CS, replay harness, WS down-converter |
| T3 Race core | Battle ladder, overtake classifier, position events (#105) |
| T4 Pit + HR | Pit FSM, HR pressure (#104) |
| T5 V4 presentation | Assets, renderer, motion resolver, battle stack (#103, #95+) |
| S3a | Input-replay harness + scenarios 1–10 (#109) |
| S3b | Golden gallery, 21 fixtures, `/overlay/golden` (#108) |
| S3c | i18n CS + pit/bio renderer polish (#107) |
| **Done** | **#111** demo JS hotfix merged |
| **Done** | **R0** golden glow clip (master) |
| **Branch** | `cursor/ee-v4-remainder-65db` — 33 golden, catalog, sysinfo V4, replay 1–16 |

**Coverage (branch HEAD)**

| Set | Count |
| --- | --- |
| Manifest states | 35 |
| `event_catalog.json` v1 wired states | 33 |
| Golden fixtures | 33 |
| Replay scenarios | 16 |
| Transient families with renderer + assets | 7/7 |

---

## 1. Known visual bug (P0 — R0)

**Symptom:** Initial enter glow bleeds outside 420×140 cells on **all** golden gallery fixtures (user report 2026-08-28).

**Fix:** PR **#113** (`cursor/fix-golden-glow-clip-65db`) — approved.

| Step | Status |
| --- | --- |
| R0.1 Reproduce | done |
| R0.2 CSS `isolation` + `contain: paint` on `.golden-stage` | done |
| R0.3 JS skip `syncWidgetMotion` + `glow_*` layers in golden snapshot | done |
| R0.5 Regression test | done |

**Merge gate:** Gallery visually clean at default zoom; `motion=off` deterministic; live overlay enter motion unchanged.

---

## 2. Phase map (S3d last)

```text
  P0 hotfix (#111) ──► R golden glow clip
                              │
         ┌────────────────────┼────────────────────┐
         v                    v                    v
    R4 missing           R2 P/Q + T2           R3 sysinfo V4
    manifest states      timing stories        (1920×72)
         │                    │                    │
         └────────────────────┼────────────────────┘
                              v
                    R5 replay + golden extend
                              │
                              v
                    R6 release prep (semver, docs, DoD)
                              │
                              v
                    S3d legacy removal + v1 release  ◄── LAST
```

Phases R4–R6 may run **partially in parallel** after R0; only **S3d** requires all prior merge gates.

---

## 3. R4 — Missing manifest states (12 v1) + catalog wiring (9)

**Note:** `composure_test` and `high_load` are **out of v1 scope** (§0.1). Manifest retains 35 states; v1 targets **33** wired states (21 today + 12 new).

### 3.1 Golden fixtures missing (12 states for v1)

Add to `V4_GOLDEN_CATALOG`, `GOLDEN_V4.md`, and `tests/test_golden_v4_fixtures.py`:

| State | Family | Suggested eventType | Notes |
| --- | --- | --- | --- |
| `target` | timing | `TARGET_LOCKED` | Practice target reference |
| `projected_lap` | timing | `PROJECTED_LAP` | Quali emitter exists; needs catalog entry + adapter |
| `pb_attack` | timing | `SECTOR_BEST` | Fallback target today |
| `hot_lap` | timing | `HOT_LAP` | Quali multi-lap |
| `position_attack` | timing | `POSITION_ATTACK` | Quali emitter exists |
| `gain_found` | timing | `GAIN_FOUND` | Practice emitter exists |
| `clean_streak` | timing | `CLEAN_STREAK` | Needs emitter |
| `battle_for_position` | battle | `BATTLE_FOR_POSITION` | Stack centre; renderer may exist |
| `battle_won` | battle | `BATTLE_WON` | RESULT story |
| `rival_threat` | position | `RIVAL_THREAT` | Needs emitter |
| `invalid_lap` | exception | `INVALID_LAP` | Lap validity policy |
| `link_drop` | exception | `LINK_DROP` | Telemetry stale / disconnect |

**Deferred (not in v1 golden/catalog):**

| State | Family | Reason |
| --- | --- | --- |
| `composure_test` | bio | Emitter deferred — §0.1 |
| `high_load` | bio | Emitter deferred — §0.1 |

**Merge gate:** Golden gallery covers all **catalog** states; v1 catalog target **33** states (excludes deferred bio pair).

### 3.2 Catalog entries missing (9 states — no direct or fallback in v1)

Add to `event_catalog.json` + adapters + debug inject keys:

`target`, `hot_lap`, `invalid_lap`, `clean_streak`, `battle_won`, `battle_for_position`, `rival_threat`, `position_attack`, `link_drop`

**Not in v1:** `composure_test`, `high_load` (§0.1 — deferred)

Plus promote from fallback-only to direct entries where emitters exist:

- `GAIN_FOUND` → `gain_found`
- `PROJECTED_LAP` → `projected_lap`
- `POSITION_ATTACK` → `position_attack`

**Branch:** `cursor/ee-catalog-states-65db`

### 3.3 Emitters / adapters still needed

| Event | Track | Depends on |
| --- | --- | --- |
| `TARGET_LOCKED`, `HOT_LAP`, `INVALID_LAP`, `CLEAN_STREAK` | T2 | Timing store, lap validity |
| `RIVAL_THREAT` | T3 | Opponent projected pace |
| `BATTLE_FOR_POSITION`, `BATTLE_WON` | T3 | Battle correlation / story end |
| `LINK_DROP` | T1 | `data_quality` / stale telemetry gate |

**Deferred beyond v1 (no PR in R4):** `COMPOSURE_TEST`, `HIGH_LOAD` — bio correlation emitters (§0.1)

**Branch:** `cursor/ee-timing-pq-v4-65db` (T2), `cursor/ee-race-states-65db` (T3), small T1 PR for link_drop

---

## 4. R2 — Practice / Quali V4 path (T2 completion)

**Today:** `PracticeEmitter` + `QualiEmitter` emit legacy `CandidateEvent` names (`gain_found`, `projected_lap`, …). Flags `event_engine.practice` / `quali_projection` register emitters in `runtime.py`. **No** full adapter → envelope → V4 renderer path for P/Q-specific stories.

**Must deliver:**

- Adapters for `GAIN_FOUND`, `TIME_LOST`, `PROJECTED_LAP`, `POSITION_ATTACK`, `TARGET_LOCKED`, `HOT_LAP`, `NO_IMPROVEMENT` (fallback)
- Replay fixtures: `scenario_11_practice_gain.json`, `scenario_12_quali_projection.json` (minimum)
- Manager: P/Q events respect mode router + anti-spam budget
- Renderer: timing family copy slots for new states (reuse manifest samples)
- CONFIG.md: document P/Q flags behaviour when `v4_renderer=true`

**Merge gate:** Replay scenarios pass with `v2_payload=true`; golden fixtures for timing P/Q states.

**Branch:** `cursor/ee-timing-pq-v4-65db`

---

## 5. R3 — Sysinfo V4 renderer (required)

**Product decision:** Full V4 sysinfo for v1 — **no V3 waiver** (§0.1).

**Today:** `#sysinfo-widget` still V3 (`display.js`, flat slots). Hidden in golden layout. Manifest defines `sysinfo_canvas: [1920, 72]` but no V4 sysinfo layers in production tree.

**Scope (v1):**

- Asset import: sysinfo module segments per theme (3 themes)
- `display-v4-sysinfo.js` or extend `display-v4.js` with persistent 1920×72 layer
- Geometry unchanged vs approved layout (§7 DoD)
- Golden URL optional: `/overlay?…&layout=golden&fixture=sysinfo`

**Branch:** `cursor/overlay-v4-sysinfo-65db`

---

## 6. R5 — Replay + golden extension

| Item | Action |
| --- | --- |
| Scenarios 11+ | P/Q, invalid lap, link_drop, battle_won |
| Scenario 10 polish | Mixed race beat — verify against live mock |
| Golden 3-theme pass | `stealth_graphite`, `night_attack` gallery smoke |
| Reduced motion | CI or manual checklist: `motion=off` + `prefers-reduced-motion` |
| Asset budget | Re-run `test_overlay_assets_v4.py` size gates after any new assets |

**Branch:** `cursor/ee-replay-extend-65db`

---

## 7. R6 — Release prep (pre-S3d)

**Not S3d** — prepares v1 without removing legacy.

- [x] Walk §9 Definition of done — scorecard updated on branch
- [x] Version bump (`1.1.0` → `1.2.0` in `pyproject.toml`)
- [x] CHANGELOG.md — Event Engine V4 remainder section
- [x] CONFIG.md — recommended “full V4 demo” flag block (already used in agent testing)
- [x] API.md — `STATE_SNAPSHOT`, envelope shape when `v2_payload=true`
- [x] BUILD_AND_DEPLOY.md — package size note (~5.8 MiB themes-v4)
- [ ] Product sign-off: enable flag profile for one internal session

**Branch:** `cursor/ee-v1-release-prep-65db`

---

## 8. S3d — Legacy removal + v1 done (LAST)

Per original plan §2 gate **S3** and §7:

**Preconditions (all required):**

1. #111 merged; golden glow fixed — **done on branch** (R0)
2. R4 catalog + golden **33** v1 states (bio pair excluded per §0.1)
3. R2 P/Q path green behind flags
4. Replay scenarios 1–12+ green
5. R6 release prep merged; product explicit accept for legacy removal
6. One stable internal session with full V4 flags **or** written product waiver

**S3d deliverables:**

| Item | Action |
| --- | --- |
| Remove `legacy_from_envelope` consumer path | V4-only when `v4_renderer=true`; drop V3 battle golden master from default |
| Remove dual renderer bootstrap | `overlay.js` — single renderer after cutover |
| Delete unused V3 battle assets | Only after CI + size check |
| `display.js` transient path | Gut or gate behind compile-time dead code removal |
| Final PR title | `feat!: V4 default overlay path — remove legacy converter` |
| Tag | Product-driven semver (likely **minor** if flags stay; **major** if default-on) |

**Branch:** `cursor/ee-s3d-legacy-removal-65db` — **do not open until §8 preconditions met**

---

## 9. Definition of done — current scorecard

| Criterion | Status |
| --- | --- |
| Flags in schema, default off, CONFIG.md | pass |
| v2 envelope on WS with ACTIVE | pass (behind `event_engine.v2_payload`) |
| Practice / Quali / Race behind flags | pass — emitters + V4 adapters + replay 11–12 |
| i18n EN + CS | pass (#107) |
| Overtake ≠ silent position; pit suppression | pass (#105, #104, S2 tests) |
| V4 layered render; motion vibe | pass — R0 golden glow clip on branch |
| SYSINFO geometry | pass — V4 1920×72 renderer + asset CI |
| Golden fixtures (33 v1 states) | pass — catalog-aligned registry + gallery |
| Replay scenarios 1–16 | pass — parametric harness green |
| DecisionLog suppressions | pass (manager v2 tests) |
| Reduced-motion | pass — `motion=off` golden deterministic; 3-theme + prefers-reduced-motion CI |
| Golden URL deterministic `motion=off` | pass |
| Asset size CI | pass |
| Per-emitter fail-soft + reset | pass |
| Legacy removal (S3d) | **separate track — not in this branch** |
| Docs API / theme / BUILD (R6) | pass — CHANGELOG, API, BUILD_AND_DEPLOY updated; semver 1.2.0 |
| Product sign-off (full V4 session) | open |

---

## 10. Recommended merge order

1. **#111** — demo JS hotfix  
2. **R0** — golden glow clip (`cursor/fix-golden-glow-clip-65db`)  
3. **R4.2** — catalog entries for existing emitters (low risk)  
4. **R2** — P/Q V4 adapters + replay 11–12  
5. **R4.1 + R4.3** — remaining golden fixtures + new emitters (split T2/T3 PRs)  
6. **R3** — sysinfo V4 (**required**, §0.1)  
7. **R5** — replay/golden extension  
8. **R6** — release prep  
9. **S3d** — legacy removal (**last**)

---

## 11. Parallelism (after #111 + R0)

| Agent / PR | Can run in parallel with |
| --- | --- |
| R0 glow fix | — (first) |
| R4 catalog entries | R2 P/Q adapters (no `web/` overlap if catalog-only PR is Python/JSON) |
| R2 P/Q | R3 sysinfo (disjoint files) |
| R4 emitters T3 | R2 (different emitter modules) |
| R5 replay extend | After R2+R4 land |
| R6 release prep | After R5 |
| S3d | **Nothing** — sequential last |

---

## 12. Out of scope (unchanged from original plan)

- Live OBS Browser Source QA matrix beyond golden + replay CI  
- Hand-authored corner label packs / track corner labels  
- Full INI→YAML config migration (§0.5.2 track B)  
- Removing V3 assets before S3d gate  
- `raceMomentum` advanced storytelling  
- Full SUSPEND/RESUME polish  
- Preview packs in `web/` tree  
- **Bio emitters `composure_test`, `high_load`** — deferred beyond v1 (§0.1); assets remain in manifest for future wiring  
- **Follow-up (spec + plan):** SoF card + race remaining — `EVENT_ENGINE_V4_SOF_REMAIN_SPEC.md` + `EVENT_ENGINE_V4_SOF_REMAIN_PLAN.md` (not part of this branch)

---

## 13. Immediate next actions

1. **R6** release prep (CHANGELOG, API.md, BUILD_AND_DEPLOY, DoD scorecard).  
2. **R5** polish scenario 10 + 3-theme golden smoke checklist.  
3. **S3d** legacy removal — **last**, after R6 + product sign-off.
