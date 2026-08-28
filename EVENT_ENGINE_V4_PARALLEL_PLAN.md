# Event Engine + Overlay V4 — parallel implementation plan

**Branch base:** `master`  
**Status:** planning only (revised after dual critical review)  
**Inputs:** Event Engine Spec v1.0, Graphic Event Engine addendum PDF, Overlay assets V4 (`Grafika.part1/2` + `preview.part1/2`)  
**Reviews incorporated:** Opus + GPT-5.6 red-team (2026-08-28) — false parallelism, missing adapter/session track, A6-after-emitters rework risk, V3→V4 asset underestimation, WS cutover ownership, config/YAML conflict, early replay harness

---

## 0. Current baseline

Live pipeline:

```text
iRacing SDK → TelemetrySnapshot → RaceContextAnalyzer → RaceState
         → EventEngine emitters → CandidateEvent
         → EventManager (+ channel capacity) → RaceEvent
         → OverlayBus → WS/HTTP → web/overlay Browser Source
```

| Layer | Today | Gap vs Spec / V4 |
| --- | --- | --- |
| RAW | `iracing/` → `TelemetrySnapshot` | No formal RAW stream; missing session flags/type/ids, quality/stale, driver identity fields needed by envelope |
| DERIVED | `race/context.py` gaps/closing | No timing store / minisectors / projected lap-grid / battleIntensity 0–100 / HR pressure index |
| SEMANTIC | MVP emitters (battle/lap/position/incident/pit/session) | Practice/Quali stories, overtake classifier, pit FSM, HR pressure; emitters still emit flat `CandidateEvent` |
| Arbitration | per-channel capacity + cooldown | No P0–P5, zones, story correlation, SUSPEND/RESUME, anti-spam budget |
| Presentation | V3 battle golden master (#85) | V4 family layers + distinct theme silhouettes; different text slots |
| Assets | `web/themes/*/assets/` flat V3 slots (~1.5 MiB) | V4 `themes/{theme}/{family}/…` (~5.8 MiB production); preview ~20 MiB must stay out of runtime package |

**Out of scope:** `logic/`, `obs/` (scene switcher), `server/event_log.py` (dashboard ring buffer — **not** Spec §22 DecisionLog).

---

## 0.5 Blocking decisions (must answer before any implementation PR)

One sentence each; change only via explicit plan amendment.

1. **Emitters emit `SemanticIntent`; `EventManager` builds published `EventEnvelope`.** Emitters never invent WS shape.
2. **Types live in `events/payload.py` (intent) + `events/envelope.py` (wire).** `overlay/protocol.py` stays transport helpers / legacy shim.
3. **`ACTIVE` is renderer-local** after successful `ENTER`, not a wire phase. Wire phases: `ENTER | UPDATE | COMPACT | SUSPEND | RESUME | EXIT | RESULT`. Map legacy `trigger` → `RESULT` (short-lived) unless story is persistent.
4. **V3 battle golden-master look ends in v1 cutover** (no radar rings / tech diagram shim). V4 uses `family_detail` + functional track + state icons. Product sign-off required before A5 lands in `master`.
5. **Rule thresholds stay in INI + `FieldSpec`** (existing `schema.py` / `config_io.py`). **No YAML parser, no new runtime dependency.** Optional JSON track profiles are data files only (stdlib `json`).
6. **Default copy token language for v1 = Czech** (token catalog owned by Platform; strings not baked into PNG).
7. **Dual protocol: one canonical internal V4 event; legacy WS shape is a down-converter only.** Renderer chosen once at bootstrap (`overlay.v4_renderer`), never per-event mix. Legacy path removal has an explicit merge gate (see §7).
8. **Preview packs never under `src/irswitch/web/`** (breaks EXE size + `test_web_tree_has_no_review_previews`). Store outside package data or omit from repo.

---

## 1. Revised topology: 5 tracks (not 9 agents)

Previous A0–A8 split was over-fragmented for this repo (~9 event modules, shared `engine.py` / `runtime.py` / `manager.py` / `display.js`). Real parallel width is ~2–3 after Platform lands.

```text
                 ┌──────────────────────────────────────┐
                 │  T1 Platform (contract + adapter +   │
                 │  session reset + arbitration skeleton │
                 │  + DecisionLog + input replay harness│
                 │  + flags/schema + WS cutover shim)   │
                 └──────────────────┬───────────────────┘
            ┌───────────────────────┼───────────────────────┐
            v                       v                       v
   ┌─────────────────┐   ┌──────────────────┐   ┌────────────────────┐
   │ T2 Timing +     │   │ T3 Race core     │   │ T5 V4 presentation │
   │ Practice/Quali  │   │ (gap/battle/     │   │ (assets additive + │
   │                 │   │  overtake/pos)   │   │  renderer + golden)│
   └────────┬────────┘   └────────┬─────────┘   └─────────┬──────────┘
            │                     │                       │
            │            ┌────────v─────────┐             │
            │            │ T4 Pit + HR      │             │
            │            │ (after S2)       │             │
            │            └────────┬─────────┘             │
            └─────────────────────┼───────────────────────┘
                                  v
                    sync S3 → remove legacy path
```

| Track | Absorbs old IDs | Parallel after T1? |
| --- | --- | --- |
| **T1 Platform** | A0 + A6 skeleton + adapter/session + WS cutover + early replay harness | — (first) |
| **T2 Timing + P/Q** | A1 + A2 + A3 | yes |
| **T3 Race core** | A4a + A4b (battle, overtake/position; **not** blocked on minisectors) | yes |
| **T4 Pit + HR** | A4c + A4d | after **S2** only |
| **T5 V4 presentation** | A5 + A7 (+ demo/golden) | yes (assets even during late T1); renderer needs S1 |

Old A8 (threshold tuning) is **not** a standalone track: calibration happens inside T2–T4 using T1’s input-replay harness; final per-track profiles are a late T2/T3 polish PR.

---

## 2. Sync points (mandatory)

| Gate | Definition | Unblocks |
| --- | --- | --- |
| **S0** | `SemanticIntent` + `EventEnvelope` frozen; phase map; rule FieldSpecs + flags (default off); session reset API stub; DecisionLog interface; input-replay fixture format; canonical event↔V4 state catalog test | T2–T5 start |
| **S1** | Vertical slice: one `LAP_COMPLETE` path adapter → intent → manager → reconnect `STATE_SNAPSHOT` → V4 renderer (legacy = down-converter only). Demo inject uses same catalog | T5 renderer mergeable; confidence for more emitters |
| **S2** | Battle + position/overtake pass preemption + correlation tests; pit-cycle suppression works | **T4** may start |
| **S3** | Spec §23 scenarios 1–10 (or waived with reason); 3 themes; golden URL; asset size budget; then **legacy converter + V3 battle path removed** in a dedicated PR | v1 done |

---

## 3. Track scopes

### T1 — Platform (blocks everything useful)

**Owns (sole writer):**  
`events/payload.py`, `events/envelope.py`, `events/manager.py` (v2 skeleton), `events/engine.py` (registry fan-out), `events/decision_log.py`, `overlay/models.py` (normalized fields), `iracing/telemetry.py` + extractors for new vars, `overlay/runtime.py` (session key / reset / warm-up hooks), `overlay/bus.py`, `overlay/protocol.py` (legacy down-converter), `overlay/http.py` (snapshot + inject), `overlay/settings.py`, `overlay/schema.py`, `config.example.ini`, `CONFIG.md` flag docs, `overlay/replay_input.py` (normalized-input harness — **not** today’s bus-only `replay.py`)

**Must deliver:**
- Normalized snapshot fields from Spec §4: `sessionId`/`subsessionId`, `sessionType`, `trackId`, flags, driver display identity, lap times where available, `quality`/`staleForMs`
- Session coordinator: atomic reset of timing dedupe / lap validity / active stories on track/session change; detector warm-up 3–5 s after telemetry reconnect; `GENERIC` safe profile (lap/incident/pit/finish only — Spec §21)
- `SemanticIntent` fields (minimum): `eventType`, `action` (`enter|update|exit|result|…`), `storyKey`, `correlationId`, `dedupeKey`, subject/target, metrics, confidence, relevance deadline, reason facts, priority hint
- Arbitration skeleton: zones + P0–P5 table, story correlation, anti-spam budget hook, preemption stubs, fail-soft **per emitter** (one emitter exception must not abort the whole `tick()` — finish must still emit)
- Feature flags (all default **off**), introduced in **one** T1 PR so later tracks do not fight over schema:  
  `event_engine.v2_payload`, `event_engine.practice`, `event_engine.quali_projection`, `event_engine.overtake_classifier`, `event_engine.pit_story`, `event_engine.hr_pressure`, `overlay.v4_assets`, `overlay.v4_renderer`
- Debug/demo catalog becomes **one data file** validated against V4 `manifest.json` states (CI). Explicit fallbacks for Spec events without a dedicated V4 state (`TIME_LOST`, `SECTOR_BEST`, `NO_IMPROVEMENT`, `OVERTAKEN`, `BATTLE_LOST`, …)
- DecisionLog (Spec §22) — **new module**, not `server/event_log.py`
- Sampling note: document CPU budget; raise normalized snapshot toward Spec (20 Hz target) only with evidence; do not silently assume 5 Hz is enough for SbS/crossing

**Merge gate S0:** contract tests + empty-manager tests + reset test + per-emitter isolation test. No user-visible behavior change with flags off.

---

### T2 — Timing + Practice + Qualifying

**Owns:** `race/timing/`, practice + quali emitters, timing-related FieldSpecs usage  
**Must not edit:** T1-owned files except registering emitters via registry API; no `web/` edits

**Dependencies clarified (fixes plan bug “A1 unblocks A4”):**
- Practice target lock / lap FSM / invalidation: **partially** independent of minisectors
- `GAIN_FOUND` / `TIME_LOST` / live delta / PB projection: **need** timing store
- Quali grid projection: **needs** timing + opponent valid lap times from adapter
- Race battle: **not** blocked on T2 (uses existing gap/closing; minisectors only improve confidence later)

**Scope:** Spec §6–§9; fallback 20×5% minisectors; timing store with **hard memory cap** (N laps × M cars — test required); invalid lap policy.

**v1 cut inside T2:** no hand-authored corner labels (use `MINISECTOR NN`); exact projected grid position only when confidence ≥ profile; else soft `POSITION_IN_RANGE` / silence.

---

### T3 — Race core (battle + overtake/position)

**Owns:** battle intensity ladder, position classifier, pit-cycle **suppression** (not full pit story UI)  
**Order inside track:** battle intensity/hysteresis → overtake vs `POSITION_GAINED/LOST` → multiclass traffic rules → integration tests against T1 manager

**Not blocked on T2.** May consume timing confidence later as optional signal.

**Tests:** hunting→attack→SbS→overtake; opponent pit entry ≠ overtake; multiclass pass ≠ class battle; battle score no oscillation around threshold.

---

### T4 — Pit + HR correlated stories (after S2)

**Owns:** pit FSM ENTRY→…→OUTCOME (one `correlationId`); HR baseline + `HR_PRESSURE_RISING` requiring race+bio context  
**Blocked until S2** so stories land on stable correlation/preemption (avoids Spec §24 order inversion where pit precedes arbitration).

**Requires T1** to pass combined race+bio snapshot into emitters (today `EventEngine.tick(state: RaceState)` cannot see HR — Platform must extend the tick context).

**v1 defer:** full `pressureIndex` composition polish, `COMPOSURE_TEST` niceties, momentum (§7.6), advanced traffic storytelling.

---

### T5 — V4 presentation (assets + renderer)

**Owns:** additive asset tree, new manifest-driven resolver, `web/overlay` V4 renderer path, demo/golden/debug gallery, asset CI  
**Must not edit:** emitter math / manager policy

**Asset migration (non-negotiable corrections):**
- Import production themes **additively** (e.g. `web/themes-v4/` or `web/themes/<theme>/<family>/` beside V3). **Do not** break V3 path until S3 removal PR.
- New resolver: `(theme, family, state) → layer list` from V4 `manifest.json`. Do **not** pretend V4 is a rename of `ASSET_SLOTS` (`radar_*` slots have no V4 equivalent).
- Split tests: freeze `test_overlay_assets_v3.py`; add `test_overlay_assets_v4.py`. Stop asserting `display.js` internals from asset tests.
- Preview (~20 MiB): **outside** `src/irswitch/web/` (e.g. repo-root `overlay-v4-preview/` gitignored or docs artifact, never `package-data`).
- Production pack ~5.8 MiB: commit to git OK; LFS optional. CI: aggregate/per-file size budget + refuse LFS pointer surprises + package size check.
- QA tool: either approve **dev-only** Pillow extra, or rewrite geometry/alpha checks on the existing zlib PNG reader. Decide in T5 first PR — do not drag `/workspace/scratch` hardcodes into CI.
- Update `BUILD_AND_DEPLOY.md` for EXE size impact (`package-data = ["web/**/*"]`).

**Renderer:**
- One 420×140 root per correlated story; layer order per V4 `INTEGRATION.md`
- HTML slots: title / subtitle / value / meta (V4 coordinates — replaces V3 kicker/title/meta)
- Lifecycle CSS + one-shot WebMs; reduced-motion path
- Never re-decide semantics
- Golden acceptance URL, e.g.  
  `/overlay?demo=1&renderer=v4&layout=golden&fixture=<id>&theme=<theme>&motion=off`

**Can start:** asset import in parallel with late T1. **Renderer merge** only after S1 (and product sign-off on decision #4).

---

## 4. Shared-file ownership (sole writer)

| File / area | Owner track |
| --- | --- |
| `events/payload.py`, `events/envelope.py`, `events/decision_log.py` | T1 |
| `events/manager.py`, `events/engine.py` (registry) | T1 |
| `iracing/telemetry.py`, extractors, `overlay/models.py` | T1 |
| `overlay/runtime.py`, `bus.py`, `protocol.py`, `http.py` | T1 |
| `overlay/settings.py`, `schema.py`, `config.example.ini`, `CONFIG.md` | T1 |
| `race/timing/**` | T2 |
| Practice / Quali emitters | T2 |
| Battle / position / overtake emitters | T3 |
| Pit / HR emitters | T4 |
| `overlay/display.py` asset resolution | **T5** (zones/capacity tables that remain policy stay in `events/manager.py` / T1 — split responsibilities; avoid dual editors on one file) |
| `web/themes/**`, `web/themes-v4/**`, asset tests | T5 |
| `web/overlay/js/*`, `web/overlay/css/*` | T5 |
| Input replay fixtures | T1 owns format; T2–T4 append scenario fixtures |

If a track needs a change in another track’s file: open a small owned PR or extend the registry/API — no drive-by edits.

---

## 5. Failure-mode ownership

| Failure mode | Owner |
| --- | --- |
| WS reconnect, sequence, authoritative `STATE_SNAPSHOT`, browser dedupe | T1 (+ T5 consume snapshot) |
| Telemetry reconnect warm-up 3–5 s | T1 session coordinator |
| Session/track change atomic reset | T1 (calls into timing/emitters/manager reset hooks) |
| Stale rival data → lower confidence / drop projection | T1 quality flags + T2/T3 gates |
| BLE lost — racing overlay stays up | T1/bio path + T4 only emits BLE/HR stories when valid |
| Unknown session type → `GENERIC` | T1 mode router |
| Emitter exception isolation | T1 engine registry |
| Unserializable envelope | T1 bus: drop event, keep loop alive |

---

## 6. Integration order (actually Spec §24 aligned)

1. **T1** — normalized adapter, session reset, DecisionLog, intent/envelope, arbitration skeleton, flags, input-replay harness, WS down-converter  
2. **T2 timing** ∥ **T5 asset import** ∥ **T3 race core** (battle/position; not waiting on minisectors)  
3. Practice/Quali stories inside T2 as timing lands  
4. **S2** then **T4** pit + HR  
5. **T5 renderer** after S1; visual acceptance vs preview packs  
6. Calibration on input-replay scenarios; per-track JSON profiles if needed  
7. **S3** — enable flags per mode; remove legacy converter + V3 battle path  

Deferred beyond v1 (explicit): `raceMomentum` storytelling, advanced traffic, hand-authored track labels, SUSPEND/RESUME polish if majors can simply EXIT others, second/third theme production enablement until cyber_racing renderer frozen (assets still imported for parity tests).

---

## 7. Definition of done (v1) — enforceable

- [ ] Flags exist in schema; default off; documented in CONFIG.md  
- [ ] With v2 flags on: envelope v1 on WS with wire phases; `ACTIVE` only in renderer  
- [ ] Practice / Quali / Race paths behind their flags  
- [ ] Overtake ≠ silent position change; pit-cycle suppression  
- [ ] V4 layered render for enabled theme(s); SYSINFO geometry unchanged  
- [ ] Input-replay scenarios 1–10: expected `(eventType, phase)` sequences with documented time tolerance — or written waiver  
- [ ] DecisionLog explains suppressions (`cooldown`, `lower_priority`, `stale_data`, `pit_cycle`, …)  
- [ ] Reduced-motion verified  
- [ ] Golden URL deterministic with `motion=off`  
- [ ] Asset/package size budgets green in CI  
- [ ] Per-emitter fail-soft + reset tests green  
- [ ] Legacy down-converter removal PR scheduled (criterion: S3 + one stable session week or explicit product accept)  
- [ ] Docs: API.md, theme README, BUILD_AND_DEPLOY size note  

---

## 8. Git / PR hygiene

- Short-lived branches off `master` (or off merged T1). **No deep stacks** (`A7 = A5 + A6` style bases banned).
- Prefer merge order via flags over stacked branch bases.
- Suggested branch names (suffix `-65db`):  
  `cursor/ee-platform-65db`, `cursor/ee-timing-pq-65db`, `cursor/ee-race-core-65db`, `cursor/ee-pit-hr-65db`, `cursor/overlay-v4-65db`

---

## 9. Package inventory (inputs)

Review tree (local, gitignored): `.grafika-v4-review/`

| Part | Contents |
| --- | --- |
| Grafika.part1 | docs, manifest, tools, source_materials, motion reels |
| Grafika.part2 | production `themes/**` (3×185 files) |
| preview.part1 | `states/` + `layer_breakdowns/` |
| preview.part2 | `states_no_text/`, sheets, sysinfo, three-theme comparison |

`qa_report.json` from the pack is generator output only — re-run checks after import in repo CI.

---

## 10. Immediate next actions

1. Product sign-off on §0.5 decisions (especially #4 V3 golden retirement and #6 Czech tokens).  
2. Start **T1 Platform** only.  
3. Kick **T5 asset import** (additive, no renderer) once decision #4 is accepted.  
4. Do not start T4 until S2. Do not mix V3/V4 renderers per event.
