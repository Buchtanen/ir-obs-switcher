# Event Engine + Overlay V4 — parallel implementation plan

**Branch base:** `master`  
**Status:** planning only (no product code in this PR)  
**Inputs:** Event Engine Spec v1.0, Graphic Event Engine addendum PDF, Overlay assets V4 (`Grafika.part1/2` + `preview.part1/2`)

---

## 0. Current baseline (what exists today)

Live pipeline:

```text
iRacing SDK → TelemetrySnapshot → RaceContextAnalyzer → RaceState
         → EventEngine emitters → CandidateEvent
         → EventManager (+ channel capacity) → RaceEvent
         → OverlayBus → WS/HTTP → web/overlay Browser Source
```

| Layer | Today | Gap vs V4 / Event Engine Spec |
| --- | --- | --- |
| RAW | `iracing/` extract → `TelemetrySnapshot` | No formal RAW event stream; crossing/minisector infrastructure missing |
| DERIVED | `race/context.py` gaps/closing | No timing store, projected lap/grid, battleIntensity 0–100, momentum, HR pressure index |
| SEMANTIC | MVP emitters (battle/lap/position/incident/pit/session) | Practice/Quali stories, overtake classifier, pit story FSM, HR pressure, payload contract incomplete |
| Arbitration | per-channel capacity + cooldown | No P0–P5 classes, anti-spam budget, zone layout (MAJOR/EVENT/BATTLE/BIO/SYSINFO), story correlation |
| Presentation | V3 battle golden master (420×140), older plates for other widgets | V4 families/themes/layers/motion; distinct silhouettes; HTML text slots; lifecycle ENTER→…→EXIT |
| Assets | `web/themes/*/assets/` V3 slots | Import V4 `themes/`, `manifest.json`, motion WebMs, preview packs |

**Do not touch in this workstream:** `logic/`, `obs/` (scene switcher), `server/event_log.py`.

---

## 1. Shared contracts (freeze first — Agent 0)

All parallel tracks depend on a frozen contract. Land this **before** semantic emitters and V4 frontend diverge.

### 1.1 Domain snapshot (normalized input)

Stable fields from Spec §4 (`session`, car/driver, BLE HR, `quality`/`staleForMs`). Adapter-only iRacing names stay in `iracing/`.

### 1.2 Event envelope (Spec §19)

Required: `schemaVersion`, `eventId`, `sequence`, `sessionId`, `eventType`, `mode`, `phase`, `occurredAt`, `monotonicMs`, `priority`, `severity`, `confidence`, `dedupeKey`, `correlationId`, `subject`/`target`, `metrics`, `copy` (tokens), `presentation` `{widget,zone,variant,accent,preferredState,minHoldMs,maxHoldMs}`, `reason` (log always; WS optional).

Lifecycle phases: `ENTER | UPDATE | COMPACT | SUSPEND | RESUME | EXIT | RESULT`.

### 1.3 Zones & priorities (Spec §16)

| Zone | Cap | Notes |
| --- | --- | --- |
| `MAJOR` | 1 | final lap / finish / start |
| `EVENT` | 1 primary (+ optional compact queued) | timing/position/pit/exception results |
| `BATTLE` | 1 ahead + 1 behind + position badge | intensity ladder |
| `BIO_EXPANDED` | 1 | shares secondary with battle |
| `SYSINFO` | permanent | 1920×72; geometry never moves |

Priority classes P5…P0 as in Spec §16; cooldowns keyed by `eventType + subject + target`.

### 1.4 Presentation map (V4)

- Transient canvas **420×140**, no baked dynamic text.
- SYSINFO **1920×72**.
- Families: `battle`, `timing`, `position`, `exception`, `pit`, `bio`, `session`.
- Themes: `cyber_racing`, `stealth_graphite`, `night_attack` (distinct silhouettes).
- Source of truth: V4 `manifest.json` + `STATE_CATALOG.md` / `LAYER_CATALOG.md`.
- Machine mapping: semantic `eventType` → `presentation.widget/zone/variant` + state id from catalog.

### 1.5 Deliverables for Agent 0

- `docs/EVENT_PAYLOAD_CONTRACT.md` (envelope + examples)
- Typed Python models for envelope (extend `overlay/protocol.py` or new `events/payload.py`)
- YAML/JSON default rule profile stubs (Spec §20) — thresholds data-driven, not hardcoded in emitters
- Mapping table: Spec event catalog ↔ V4 state ids ↔ current MVP `CandidateEvent.name`
- Fixture golden JSON for 5 canonical stories (practice PB attack, quali projection, race overtake, pit story, finish)

**Merge gate:** contract tests green; no emitter/UI behavior change yet (compat shim keeps old WS shape until cutover flag).

---

## 2. Parallel tracks (agents)

```text
                    ┌─────────────────────────────┐
                    │  A0 Contract & fixtures     │
                    └──────────────┬──────────────┘
           ┌───────────┬───────────┼───────────┬───────────┐
           v           v           v           v           v
     A1 Timing    A2 Practice  A3 Quali   A4 Race     A5 Assets
     store/RAW    semantics    semantics  battle/     V4 import
     crossings                /grid      overtake/   + QA
           \           \         |       pit/HR         |
            \           \        |          |           |
             v           v       v          v           v
              ┌──────────────────────────────────────────┐
              │  A6 Arbitration / EventManager v2        │
              └────────────────────┬─────────────────────┘
                                   v
              ┌──────────────────────────────────────────┐
              │  A7 Overlay frontend V4 renderer         │
              └────────────────────┬─────────────────────┘
                                   v
              ┌──────────────────────────────────────────┐
              │  A8 Replay harness + threshold tuning    │
              └──────────────────────────────────────────┘
```

Tracks A1–A5 can run in parallel after A0 lands (A5 can even start immediately on asset import with manifest-only contract).

---

### Agent A1 — Timing infrastructure (RAW + DERIVED foundation)

**Owns:** `race/timing/`, crossing helpers, minisector store, segment deltas  
**Must not edit:** `web/`, emitters’ presentation strings, theme assets

Scope:
- Lap/sector crossing with unwrap + dedupe (`carId+lap+timingPoint`)
- Fallback 20×5% minisectors; track profile YAML loader
- Timing records (Spec §6.2); live cumulative delta at confirmed points
- Data-quality gates (invalid lap segments ineligible as reference)

Tests (Spec §23): wrap 1.0→0.0 single event; reverse/tow no false crossing; outlap/pit first segment ineligible.

**Depends on:** A0 snapshot fields  
**Unblocks:** A2, A3, A4 (metrics)

---

### Agent A2 — Practice semantic machine

**Owns:** practice emitter(s), target selection, PB/projection story  
**Must not edit:** battle/race overtake, frontend layout

Scope (Spec §8):
- Lap FSM: OUT_LAP → TIMED_LAP → COMPLETE / INVALID
- Target lock (no mid-lap switch)
- Events: `TARGET_SELECTED`, `PACE_UP/DOWN`, `SECTOR_BEST`, `GAIN_FOUND`/`TIME_LOST`, `PB_POSSIBLE`, `PB_ATTACK`, `INVALID_LAP`, `LAP_COMPLETE`, `PERSONAL_BEST`, `NO_IMPROVEMENT`
- Invalid policy: incident flips `invalidForOverlay`; kills projection story

Tests: PB attack → incident → invalid finish; gain threshold once per sector.

---

### Agent A3 — Qualifying semantic machine

**Owns:** quali emitter(s), projected position + confidence  
**Must not edit:** race battle ladder

Scope (Spec §9):
- HOT_LAP story + grid projection (`projectedPosition`, `positionRange`, `confidence`)
- `POSITION_IN_RANGE` / `POSITION_ATTACK` / `QUALI_POSITION_GAINED|LOST`
- Rival threat only with confidence; else soft copy or silence

Tests: P7→projected P5→valid P4; rival threat without inventing precision.

---

### Agent A4 — Race: battle, overtake, pit, HR

**Owns:** battle intensity/ladder, position classifier, pit FSM, HR pressure  
**Split into sub-PRs if needed:** A4a battle, A4b overtake/position, A4c pit, A4d HR

Scope:
- `battleIntensity` 0–100 + hysteresis (Spec §7.5, §15)
- Ladder NONE→…→SIDE_BY_SIDE→RESOLVING→WON/LOST
- Overtake vs `POSITION_GAINED/LOST` (Spec §11); pit-cycle suppression
- Pit story ENTRY→…→OUTCOME (Spec §13); one `correlationId`
- HR baseline + `HR_PRESSURE_RISING` only with race context (Spec §14)
- Multiclass: class position primary; other class → traffic, not battle

Tests: hunting→attack→SbS→overtake; pit entry opponent ≠ overtake; HR spike without battle ≠ pressure; incident coalesce.

---

### Agent A5 — V4 asset import & contract tests

**Owns:** `web/themes/`, asset manifests, `tests/test_overlay_assets.py`, vendor copy of V4 pack  
**Must not edit:** event logic

Scope:
- Import production layers from V4 package (`themes/**`, `manifest.json`)
- Keep preview packs under `web/themes/_preview/` or `assets/overlay-v4-preview/` (review-only; not Browser Source runtime)
- Update `ASSET_SLOTS` / presentation payload to family-layer model (or shim V3 slot names → V4 paths during transition)
- Port/adapt `tools/qa_overlay_v4.py` into CI-friendly checks (dims, alpha, theme pixel-diff floors)
- Preserve three-theme parity (185 files each theme in source pack)

**Source package (local review tree):** `.grafika-v4-review/` (assembled from uploads; do not commit huge binaries blindly — decide LFS/vendor policy in A5 PR description)

---

### Agent A6 — Arbitration / EventManager v2

**Owns:** `events/manager.py`, `overlay/display.py` zone rules, anti-spam, lifecycle  
**Must not edit:** detector math, theme PNGs

Scope (Spec §15–17):
- Replace channel-only model with zone + priority classes
- Story correlation: UPDATE/COMPACT/SUSPEND/RESUME/RESULT without new ENTER
- Preemption: FINISH clears non-persistent; INVALID replaces PB_ATTACK; overtake is RESULT of battle story
- Anti-spam: ≤3 new transient entries / 10 s (majors exempt)
- Reconnect: `STATE_SNAPSHOT` of active stories + last `sequence`
- Event log with reason/suppression (Spec §22)

Tests: capacity, preemption, expired queue drop, idempotent final lap/finish.

**Depends on:** A0 envelope; integrates emitters as they land behind feature flags.

---

### Agent A7 — Overlay frontend V4 renderer

**Owns:** `web/overlay/js/*`, CSS themes, DOM lifecycle  
**Must not decide** semantic meaning (no re-detect overtake/hunting)

Scope (V4 `IMPLEMENTATION_EXAMPLE.md`, `INTEGRATION.md`, `MOTION_SPEC.md`):
- One 420×140 root per correlated story; layer stack order fixed
- Mask tinting (`primary`/`warning`/`alert`); never tint base/material/frame
- Lifecycle CSS + one-shot WebM fragments; reduced-motion path
- Text only in HTML slots (title/subtitle/value/meta)
- SYSINFO strip unchanged geometry; local per-module colour only
- Consume new envelope; keep demo/debug inject working

Visual acceptance (Spec §23 + preview packs): compare against `preview/states*` and `states_no_text*`.

**Depends on:** A5 assets + A0/A6 payload phases.

---

### Agent A8 — Replay, observability, calibration

**Owns:** `overlay/replay.py`, replay fixtures, metrics dashboards/logs, threshold profiles per track/class  
**Runs mostly after** A1–A4 + A6

Scope:
- Spec §23 replay scenarios 1–10 as JSONL fixtures
- Metrics: emit/suppress rates, duplicate rate, projection error, battle oscillation
- Per-track rule profiles (data only)

---

## 3. Suggested git / PR topology

| Branch suffix | Agent | Base after |
| --- | --- | --- |
| `cursor/ee-contract-65db` | A0 | `master` |
| `cursor/ee-timing-65db` | A1 | A0 |
| `cursor/ee-practice-65db` | A2 | A0 (+ A1 for deltas) |
| `cursor/ee-quali-65db` | A3 | A0 (+ A1) |
| `cursor/ee-race-battle-65db` | A4a | A0 |
| `cursor/ee-race-overtake-pit-65db` | A4b/c | A4a |
| `cursor/ee-hr-65db` | A4d | A0 |
| `cursor/overlay-v4-assets-65db` | A5 | `master` (parallel) |
| `cursor/ee-arbitration-65db` | A6 | A0 |
| `cursor/overlay-v4-renderer-65db` | A7 | A5 + A6 |
| `cursor/ee-replay-tuning-65db` | A8 | A1–A4 + A6 |

Feature flags (config): `event_engine.v2_payload`, `event_engine.practice`, `event_engine.quali_projection`, `event_engine.overtake_classifier`, `overlay.v4_assets`.

Default: flags off on `master` until integration PR enables per-mode.

---

## 4. Integration order (Spec §24 aligned)

1. A0 contract + A5 asset import (parallel)
2. A1 timing store
3. A2 Practice
4. A3 Qualifying
5. A4 Race battle → overtake/pit → HR
6. A6 arbitration (can stub early with MVP emitters, then swap)
7. A7 frontend V4
8. A8 replay tuning

---

## 5. Non-negotiables (all agents)

- Stability > elegance; never crash the overlay/main loop.
- Monotonic time for timeouts; session time is domain data only.
- Overlay must not re-decide semantics.
- Theme config must not contain semantic thresholds.
- Evidence: unit tests for rules; replay for stories; asset QA for pixels.
- No new dependencies unless explicitly approved.
- Layer boundaries: `iracing/` extract only; `overlay/` glue; decisions in `events/` + `race/`.
- Czech UI copy via tokens/locale later; payload uses `copy.*Token` keys.

---

## 6. Package inventory (V4 inputs)

Assembled review tree: `.grafika-v4-review/`

| Part | Contents |
| --- | --- |
| Grafika.part1 | docs, manifest, tools, source_materials, motion reels |
| Grafika.part2 | `themes/**` production PNG/WebM (3×185 files) |
| preview.part1 | `states/` (with sample text), `layer_breakdowns/` |
| preview.part2 | `states_no_text/`, theme sheets, sysinfo, three-theme comparison |
| Spec MD + PDF | Event engine + graphic addendum |

QA report in pack: `qa_report.json` → `ok: true` (use as baseline, re-run after import).

---

## 7. Definition of done (v1 cut)

- [ ] Envelope v1 on WS with lifecycle phases
- [ ] Practice / Quali / Race semantic paths behind flags
- [ ] Overtake ≠ silent position change; pit-cycle suppression
- [ ] V4 themes render from layered assets; SYSINFO stable
- [ ] Replay scenarios 1–10 pass or explicitly waived with reason
- [ ] Debug event log explains suppressions
- [ ] Reduced-motion path verified
- [ ] Docs updated: API.md, theme README, CONFIG thresholds

---

## 8. Immediate next actions

1. Review/approve this plan.
2. Spin Agent A0 (contract) and Agent A5 (assets) in parallel.
3. Do **not** start A7 renderer until A5 slot/manifest mapping is agreed.
4. Keep scene-switcher (`logic/`/`obs/`) out of scope.
