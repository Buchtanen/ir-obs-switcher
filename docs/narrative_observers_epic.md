# Narrative observers epic (stream → practice → quali → race → finish)

**Status:** landing on `master` after umbrella [#179](https://github.com/Buchtanen/ir-obs-switcher/pull/179) merged (2026-09-01). Rebased + adapted finish/checkered vs `SessionEndTracker`.  
**Depends on:** [scenario_coverage_matrix.md](scenario_coverage_matrix.md), [observers_decoupling_plan.md](observers_decoupling_plan.md)  
**Umbrella:** P0–P5 [#179](https://github.com/Buchtanen/ir-obs-switcher/pull/179) — merged. This epic targets **`master`**.  
**Layout:** extend flat `src/irswitch/race/*.py` (`observer.py`, `aftermath.py`, `narrative.py`, `session_end.py`, `story.py`, `grid_story.py`). There is **no** `race/observer/` package.  
**Task slices:** [docs/tasks/](tasks/) — sequential commits on this branch. N7 landed as opt-in (`race_observer.grid_story`); live listen still decides density.

This epic expands the locked decoupling plan with the **broadcast story**. v1 is a **narrow landing** on the umbrella. Later kinds/cover/flag trees wait for a live listen. Commentary Director V2 async isolation is captured as follow-up **N12**; it does not widen the current landing.

---

## Review incorporated (2026-08-31)

Two independent reviews (code vs P0–P5, product vs iRSDK). Verdict: **reshape, do not implement N1–N11 as originally written.**

| Finding | Plan change |
| --- | --- |
| P3 already has stalled/rolling + `BACK_UNDER_WAY` | N3 **extends** `aftermath.py`; no second FSM; no `INCIDENT_RECOVERED` |
| `IncidentEmitter` delta ≥ 2 vs aftermath any rise | Explicit policy: do not double-speak; document 1x off-track |
| `session_finished` is mute + finish + wrap | Split **three** booleans (N4) |
| Checkered **bit** ≠ `SessionState` 5 | Do not OR them into one `field_checkered` |
| 5 Hz poll | No spoken `lost_control` / `contact_object` in v1 |
| `CarIdxBestLapTime` is official, missing | N1 **required**; `DriverInfo` is **not** a lap-time source |
| Four openers (stream / intro / in_car / preview) | **Opener mutex** — not “both can fire” |
| P2–P4 derived types are template-only | N11 does not need to graph them first |
| P5 `ATTACK_RANGE` / `PIT_STOPPED` already filled | Out of N11 |
| Overlay cover is HUD/theme | **N9 cut** from this epic |
| `session_briefs=false` silences wrap/preview | Product decision required before N7 |
| N1 “parallel with P0” vs umbrella | N-tasks only on #179 |
| Config key clash | One name: `gap_hunt_tts_in_practice` |

### Second review (code, 2026-08-31)

Independent pass against P0–P5 symbols. Incorporated below.

| Finding | Plan change |
| --- | --- |
| §1.1 put N8 before N2; unknown `STREAM_START` fails `parse_sequence_graph` and kills all commentary | Landing: **N1 → N2 → N4 → N8 → N11 A** |
| N8 “≥15 s” has no node yet; formatter fallback caps at 4 s; `director._speak` holds `_busy_until` for the node duration | N8 = bridge + mutex + type; **long copy is N11**; document busy-hold vs `commentary.max_utterance_s` |
| `_looks_stalled` is **surface-first** (off-track ⇒ stalled even if moving); Speed-primary would drop `BACK_UNDER_WAY` | N3: Speed is motion **inside** stalled recovery / on-track classify — **not** a reclassify of off-track cars to `rolling` |
| §1.1 `field_checkered` vs §2.5 `session_checkered` | Canonical: **`session_checkered`** (`SessionState == 5`). `field_checkered` = rejected OR'd name |
| `event_engine.gap_hunt_tts_*` lives in HUD feature flags | Keys move to **`[commentary]`** (TTS gate; HUD may still hunt) |
| `[race_observer]` does not exist; `RaceObserver()` takes no settings | **N6a** bootstraps section + dataclass + `OverlayRuntime` wiring (first `race_observer.*` in landing) |
| N4 grep missed `events/target_locked.py`, `overlay/mock.py` | Listed in N4 |
| Pit-rise: `bool(None)` is False; disconnect `reset()` drops latch; ESC teleport | N4 must reuse `is_esc_teleport` and define latch vs `RaceContextAnalyzer.reset()` |
| Double-speak is **INCIDENT** (engine, delta≥2, prio 90) vs **INCIDENT_AFTERMATH** (derived, any rise, prio 72, fan-out bypass) — not generic vs branch on one envelope | N3 AC targets that pair |
| `as_speed_mps` does not exist; helpers live in `sdk_units.py`; `reader.py` has duplicate var lists | N1 owns those files |
| Matrix §4.3/§4.5/§6 still said attack_range/pit_stopped/chain gaps | Matrix re-pinned in this commit |
| N2 `speak_priority` vs `director._follow_edge` | Filter mode/branch **first**, then edge-follow on the filtered set |

---

## 0. Product story (what we want)

Still the north star. **v1 ships only the bold parts.**

```text
OBS stream goes live
  → long welcome TTS with context          [v1, mutex]
  → overlay cover                          [CUT — HUD follow-up]
Get in the car (often pit)
  → Practice / Quali / Race flavor         [v1, mutex vs intro]
Practice / Quali
  → off-track vs generic incident          [v1]
  → contact car vs object, lost-control    [NOT v1 — refuse on air]
  → sector / lap improvement               [already shipped]
  → hunt position BY LAP TIME, not gap     [v1 if CarIdxBestLapTime works]
  → leader filler ≤ 1× / 5 min             [v1: extend P2 FIELD_FACT]
Race
  → quali recap + parade padding      [opt-in `grid_story`; not a rolling novel]
  → battles                                [keep BattleEmitter]
  → Speed-based recovered on P3 FSM        [v1]
  → yellow / green / checkered flags       [v1]; full flag tree later
Finish ≠ checkered announcement            [v1]
```

Voice: viewer-facing third person. HUD priorities stay visual.

---

## 1. Relation to the decoupling plan

| Plan item | This epic |
| --- | --- |
| P0 fan-out | Keep. Peers, not chain. Matrix §1 re-pinned in this commit. |
| P1 SpeechScheduler | Keep. |
| P2 RaceObserver | Keep kernel. Leader 5 min = **extend** `next_filler_envelope`, do not add a second filler path. |
| P3 aftermath | **Keep event names.** N1 `Speed` is motion (not classify-primary). N3 classify is **pre-step** on incident rise, not a parallel FSM. |
| P4 wrap/preview | Keep. Wrap must **not** fire on field checkered after N4. Gated by `commentary.session_briefs` today — do not assume they are audible. |
| P5 ATTACK_RANGE / PIT_STOPPED | **Done.** Not N11. |
| V2 async consumer isolation | **Follow-up N12.** One producer / RaceObserver, one accepted stream, independent overlay and commentary queues/tasks. Not part of #181 landing. |
| `RIVAL_REAPPEARS` | Unused in code. **Cut** from this epic (delete or park in decoupling plan). |

---

## 1.1 First landing (ordered commits on this branch)

Parent is **`master`** (#179 merged 2026-09-01). Finish/checkered adapted onto `SessionEndTracker` (three booleans; no `SESSION_CHECKERED` emit; fillers mute on `mute_field` only). #179 graph fillers and TTS 14 s / 13 s node ceiling stay.

N2 **must** land before any new `event_types` string in `sequence_graph.json`. Unknown types fail `parse_sequence_graph` and `OverlayRuntime._build_commentary` returns `None` (all commentary dies).

1. This docs reshape (this commit).
2. **N1 extract:** `Speed` → `RaceState.speed_mps` via new `as_speed_mps` in `sdk_units.py` (0 valid, negative → None). `CarIdxBestLapTime` / `CarIdxLastLapTime` via `as_completed_lap_time`. `session_flags.py` decode. Also update `iracing/reader.py` duplicate var lists. **No** Yaw/accel. No speak.
3. **N2** additive `modes` / `branch` + director pick. Register `STREAM_START` and `SESSION_FLAG` in `COMMENTARY_ONLY_EVENTS` here (nodes/copy come later). Mode/branch filter **before** `_follow_edge`.
4. **N4 finish split** (wide audit): `session_checkered` / `player_finished` / `mute_field`. See §2.5.
5. **N8 opener mutex + stream bridge** (no cover, no long copy). Default `commentary.stream_start=false`. Hook `obs_stream_started` → `get_overlay_runtime()`. Fail-soft.
6. **N11 wave A only:** long `stream_start` node (`tts.max_seconds` ≥ 15, validator exception vs `commentary.max_utterance_s`) + mode `in_car`. Do not delete generic `in_car` until lines migrate.
7. **N6a:** suppress gap-hunt **TTS** in P/Q (`commentary.gap_hunt_tts_in_practice` / `_qualifying` default `false`). Bootstrap `[race_observer]` + settings wiring. Leader fact 300 s. Race unchanged. HUD may still hunt.
8. **N6b:** hunt-by-time **only if** N1 fixtures show usable `CarIdxBestLapTime`. Else skip speak. Fix or quarantine `QualiEmitter.position_attack` (hero PB as `P{n}`, not rival time).
9. **N3 v1:** `off_track` vs `unknown` on INCIDENT; Speed as motion on P3 **without** flipping off-track→rolling; scheduler must not speak INCIDENT + INCIDENT_AFTERMATH the same tick. `BACK_UNDER_WAY` only.
10. **N5 v1:** race yellow (coalesce caution family) / green / checkered as `SESSION_FLAG`. Ignore start lights. Default off.
11. Live listen (density). N7 one-liner recap + parade pad is **opt-in** (`race_observer.grid_story`). Then research lost-control, then HUD cover.

---

## 1.2 Cut from this epic / this landing

- Spoken `contact_car`, `contact_object`, `lost_control`
- Overlay cover (N9) — HUD/theme follow-up
- Leader-pace as its own graph node (P2 `FIELD_FACT` + 300 s cooldown)
- Rolling-start “scenarios”
- N10 as public API (debug ring is in the FSM/director; no GET / admin page)
- Yaw/Velocity/Accel extract until a research slice exists
- `DriverInfo` as lap times
- `race/observer/` package

## 1.3 Follow-up after live listen — N12

[N12](tasks/n12_async_consumers.md) replaces the remaining synchronous
`OverlayRuntime` orchestration with one producer and two independent async
consumers. It explicitly includes direct commentary sidecars and derived
RaceObserver events, so the result is not another partial fan-out.

N12 is sequential because it touches `main.py`, `events/`, `race/`, `overlay/`,
and `commentary/` ownership boundaries. It must start from the then-current
`master` after #181; do not stack the runtime refactor into this landing.

---

## 2. iRSDK

Do **not** invent telemetry names. Extraction in `iracing/` only.

### 2.1 Already on `TelemetrySnapshot`

| Var | Use |
| --- | --- |
| `PlayerCarMyIncidentCount` | Counter only — no type enum |
| `PlayerTrackSurface` / `CarIdxTrackSurface` | OffTrack=0 … OnTrack=3 |
| `CarDistAhead` / `CarDistBehind` / `CarIdxLapDistPct` | Nearby metric only — **not** proof of contact |
| `OnPitRoad`, `PlayerCarTowTime` | Pit vs tow |
| `SessionFlags` | Extracted, unused by emitters |
| `SessionState` | 3 ParadeLaps, 4 Racing, 5 Checkered, 6 CoolDown |
| `LapBestLapTime` / `LapLastLapTime` | **Player only** |
| `CarIdxClassPosition` | Already extracted |

`DriverInfo` in this repo = names / iRating / class / spectator. **Not** a lap-time table.

### 2.2 Landing extract (N1) — official

Verified against irsdkdocs. None of these names are invented.

| Var | Unit | Landing |
| --- | --- | --- |
| `Speed` | m/s (0 valid) | **required** — `speed_mps` on snapshot + `RaceState`; aftermath **motion** (see N3, not classify-primary) |
| `CarIdxBestLapTime` | s, disconnected `-1` | **required** — N6; sanitize with `as_completed_lap_time` |
| `CarIdxLastLapTime` | s, `-1` | **required** companion |
| `SessionFlags` decode | bits | **required** helper; no speak |

**Not in landing:** `Yaw`, `YawRate`, `VelocityX/Y`, `LatAccel`, `LongAccel`, `SteeringWheelAngle`. 5 Hz (`iracing.poll_hz`) cannot catch a yaw spike; `LatAccel` includes gravity. Research later.

Optional later (not v1): YAML `SessionInfo.Sessions[].ResultsPositions[].FastestTime` / `LastTime` if live arrays are all `-1`.

### 2.3 Incident kinds — **on-air refuse**

No SDK incident-type enum. `IncidentEmitter` default `incident_min_delta = 2` → many 1x off-tracks **never emit**. Aftermath FSM today fires on **any** count rise. Plan must not ignore that mismatch.

| Kind | v1 speak? | Evidence |
| --- | --- | --- |
| `off_track` | **yes** (high) | `PlayerTrackSurface == OffTrack` around a tick |
| `unknown` | **yes** (generic incident) | everything else |
| nearby car | **metric only** | never “he hit X” |
| `contact_car` / `contact_object` | **refuse** | 5 Hz correlation, not fact |
| `lost_control` | **refuse** | undersampled; banked `LatAccel` lies |

Chain copy, if any: “then contact” after off-track — never wall vs car.

**Double-speak (real pair):** `INCIDENT` from `IncidentEmitter` (delta ≥ `incident_min_delta` default 2, HUD prio 90, EventEngine + `filter_post_race`) vs `INCIDENT_AFTERMATH` from `IncidentAftermathFsm` (any count rise, prio 72, `take_derived_envelopes` → `EventFanout`, **bypasses** engine arbitration). A `metrics.branch` on the one INCIDENT envelope cannot compete with itself (`_pick_node` returns one node). v1: set `metrics.branch` = `off_track` \| `unknown` on INCIDENT; aftermath stays P3. Scheduler: **do not speak INCIDENT and INCIDENT_AFTERMATH in the same tick** (defer or drop the lower-prio derived).

**1x off-track:** leave `incident_min_delta` unless we add an explicit commentary-only 1x path with a hard cooldown (separate AC, default off).

### 2.4 Flags

Decode in `iracing/session_flags.py`. Bits match `irsdk_Flags`.

**Checkered flag bit** = this client is **shown** the flag. **`SessionState == 5`** = session in checkered. **Do not OR** them into one field used for hero finish.

v1 speak (N5): race **yellow** (coalesce `yellow` / `yellowWaving` / `caution` / `cautionWaving`) / **green** / **checkered**. Start lights stay silent. Default off.

### 2.5 Finish — three booleans

Today `session_finished = SessionState in {5, 6}` and that one flag:

- fires `FINISH` (`SessionEmitter`)
- mutes field (`filter_post_race`)
- aborts hunting (`BattleEmitter`)
- silences P/Q/sectors/pits
- fires `SESSION_WRAP`
- stops timing ingest

Product: checkered is a **flag**, not hero result. Finish = first **s/f crossing after the session is checkered**, or **pit-road rising after checkered if the car was not already on pit road**. CoolDown without those = DNF fallback.

| Boolean | Meaning |
| --- | --- |
| `session_checkered` | `SessionState == 5` (session, not client bit) |
| `player_finished` | hero done (cross / eligible pit / cooldown fallback) |
| `mute_field` | post-race filter + battle abort — **must follow `player_finished`**, not checkered |

`session_finished` is deprecated as a dual-use name. N4 must grep every call site: `race/context.py`, `events/session.py`, `events/session_phase.py`, `events/engine.py`, `events/battle.py`, `events/practice.py`, `events/quali.py`, `events/sector_split.py`, `events/pit_story.py`, `events/target_locked.py`, `race/narrative.py`, `overlay/mock.py`, plus tests that construct `session_finished=`.

Pit-rise finish: only if `OnPitRoad` was **false** when checkered started (otherwise no rising edge, or false finish for cars already in pits). Latch rules N4 must write:

- `bool(snap.on_pit_road)` today turns `None` into `False` — a dropout looks like “on track”; recovery then looks like pit-rise finish. Treat `None` as unknown (do not arm / do not fire).
- Reuse `iracing.trk_loc.is_esc_teleport` (already used by `should_begin_pit_cycle`) so ESC/teleport is not a finish.
- `RaceContextAnalyzer.reset()` on disconnect must **drop** the checkered/pit latch; do not finish across a reconnect.

`SESSION_WRAP` moves off the checkered edge → `player_finished` or session-key change (P4 already wraps on key change).

HUD finish plate stays highest prio when `player_finished` fires. N5 checkered flag is a different beat.

---

## 3. RaceObserver — extend what shipped

Not a second EventEngine. Not an LLM. Watches are extra ticks inside existing `RaceObserver.observe()` (`aftermath.tick`, `narrative.tick` today). New modules stay **flat** under `race/`.

Derived COMMENTARY_ONLY envelopes **bypass EventEngine arbitration** (drain → fan-out). Plan must set speak_priority/cooldowns knowing incident HUD is 90 and aftermath is 72.

### 3.1 Kernel (P2 — do not redesign)

`StoryContext` 2+2, weather, `StreamMemory` (sessions + rivals + **quali bag**: class position + best lap seconds). Field facts 15–20 s rotation. Leader 5 min = extra cooldown on the **leader** fact, not a new event type.

### 3.2 v1 watches

| Watch | Module | Session |
| --- | --- | --- |
| Aftermath (P3) + Speed | `aftermath.py` | all; recovered TTS race-only |
| Flags rising-edge | new `race/flags.py`, called from observer | v1: race yellow/green/checkered |
| Finish (N4) | `context.py` state + `session.py` | race |
| Timing hunt | new `race/timing_hunt.py` **iff** N1 times work | P/Q |
| Stream start | new bridge `main.py` → overlay runtime (does **not** exist today) | once per OBS rising edge |
| Grid/rolling | N7 `grid_story.py` | race; opt-in |

Signature: match shipped `tick(state, now)` plus fields copied onto `RaceState` by N1. Do not invent `tick(ctx, snap)` until a dedicated observer refactor (not in landing).

### 3.3 Session policies (v1)

**Practice / Quali:** gap-hunt **TTS** off by default; HUD may still hunt. Timing-hunt (`PACE_HUNT`) = hero best/projected vs `CarIdxBestLapTime` of the car in P{n}. If array is all None, **silence** (no DriverInfo fallback). Quali `position_attack` stays **own PB only**, not hunt-P{n}.

**Race:** keep `BattleEmitter` gap hunt. Speed on P3 recovered. Flags v1. N7 recap + parade pad when `grid_story` is on (not a rolling novel).

### 3.4 Incident arc

P3 FSM is authoritative (`idle → classify → stalled | rolling → BACK_UNDER_WAY`). **Classify stays surface-first:** `_looks_stalled` today is True on OffTrack / not-on-track / tow **without reading motion** — that is the only path that can later emit `BACK_UNDER_WAY`. N3 must **not** make Speed primary if that reclassifies a still-rolling off-track car as `rolling` (idle, no recovery beat). Speed + LapDistPct = motion for (a) on-track stalled vs rolling and (b) stalled → `BACK_UNDER_WAY`. Speed missing → keep current LapDistPct. No rename to `INCIDENT_RECOVERED`.

---

## 4. Sequence graph

Today: `nodes_for(event, phase)` only. P2–P4 derived types often have **no graph node** — they speak via `format_filler_text`. P5 attack_range / pit_stopped **are** filled.

v1 N2: optional `modes` + `branch` on nodes; director match ladder. **Trap:** generic `incident` must not outrank `off_track` via `speak_priority` — branch match wins the tier, then priority.

v1 content (N11 A): `stream_start` (long `tts.max_seconds` ≥ 15) + `in_car` mode filters. `hr_states: ["unknown"]` for those. Keep generic `in_car` until migrated.

Do not cartesian-product flags × modes × emotions.

---

## 5. Opener mutex (required)

Today they are separate machines and **will talk over each other** if N8 “both can fire” stands. Runtime already defers `ENTER_CAR` when a session brief speaks.

| Situation | One winner |
| --- | --- |
| OBS live, not seated | `STREAM_START` only |
| Seated, same session, no stream-start this tick | `ENTER_CAR` **or** session intro, not both |
| Session change, stream already live | `SESSION_WRAP` then **one** of preview **or** intro |
| Race pre-green | recap **instead of** a second race intro (N7, `grid_story`) |
| Stream start while already in car | welcome only; **do not** replay in-car |

N8 must **add** `main.py` → overlay/commentary bridge (`obs_stream_started` today only refreshes YouTube). Use existing `overlay/http.py` `get_overlay_runtime` / `set_overlay_runtime` — no new global. Fail-soft.

Cover (N9) is **out**. Auto-hide vs 15 s TTS would desync anyway.

---

## 6. Hunting: two sports

| Session | Meaning | Owner |
| --- | --- | --- |
| P/Q | time that holds P{n} | N6b + `CarIdxBestLapTime` |
| Race | gap + closing | `BattleEmitter` |

Leader time: P2 field fact, **1× / 300 s**, skip if a better beat just spoke.

---

## 7. Sequencing

N1–N11 are on `cursor/narrative-observers-epic-4749` (base #179). See §1.1. No parallel PRs to `master`. Shared files (`context.py`, `observer.py`, `graph.py`, `runtime.py`) = sequential commits. N12 is a later, dedicated refactor branch from updated `master` after the live listen.

---

## 8. Config (planned)

| Key | Default | When |
| --- | --- | --- |
| `[commentary.scheduler].*` | safe/off | P1 shipped |
| `commentary.stream_start` | `false` | N8 |
| `commentary.gap_hunt_tts_in_practice` | `false` | N6a — TTS only; not `[event_engine]` (HUD feature flags) |
| `commentary.gap_hunt_tts_in_qualifying` | `false` | N6a |
| `race_observer.leader_pace_cooldown_s` | `300` | N6a — **N6a creates** `[race_observer]` + settings dataclass + `OverlayRuntime` wiring (`RaceObserver()` today takes no settings) |
| `race_observer.incident_classify` | `false` until trusted | N3 (add key to the N6a dataclass) |
| `race_observer.flags` | `false` | N5 |
| `race_observer.grid_story` | `false` | N7 recap + parade pad; independent of `session_briefs` |
| `commentary.session_briefs` | already `false` | wrap/preview stay silent unless on |

No `overlay.stream_cover` in this epic. No `gap_hunt_in_practice` alias. No `event_engine.gap_hunt_tts_*`.

`STREAM_START` node `tts.max_seconds` ≥ 15 **holds** `director._busy_until` for that duration (opener mutex). Master already ships `commentary.max_utterance_s` default **14** and graph `default_tts.max_seconds` **13** (#179 polish). `speak_timeout_s()` still exempts `STREAM_START` only so the 16 s welcome node is not clipped. Do not raise the global cap further for other nodes.

---

## 9. Docs / test

- Behavior change → tests with fake clock + synthetic snapshots.
- N4: hunting still emits after `SessionState=5` until `player_finished`.
- N3: delta=1 aftermath-only vs delta≥2 incident+aftermath policy test.
- N12: identical event-id sequences for both consumers, slow/failing consumer
  isolation, ordered reset, queue overflow observability, and no direct
  overlay-to-director import/callback.
- Matrix §1 / §4.3 `attack_range` / §4.5 `pit_stopped` / §6 chain item re-pinned in this commit. Later slices still tick their rows when they ship.
- TDD-exception only for this docs reshape.

---

## 10. Task index (post-review)

| ID | Doc | v1? |
| --- | --- | --- |
| N1 | [n1_irsdk_dynamics_flags.md](tasks/n1_irsdk_dynamics_flags.md) | yes — Speed + CarIdx times + flag decode |
| N2 | [n2_graph_mode_branch.md](tasks/n2_graph_mode_branch.md) | yes — schema + director pick; **before N8** |
| N3 | [n3_incident_classifier.md](tasks/n3_incident_classifier.md) | reduced — off_track vs unknown; Speed = motion not classify-primary |
| N4 | [n4_finish_semantics.md](tasks/n4_finish_semantics.md) | yes — three booleans |
| N5 | [n5_flags_observer.md](tasks/n5_flags_observer.md) | reduced — Y/G/checkered race |
| N6 | [n6_practice_quali_pace.md](tasks/n6_practice_quali_pace.md) | split a/b; N6a bootstraps `[race_observer]` |
| N7 | [n7_race_start.md](tasks/n7_race_start.md) | **yes** — opt-in `grid_story`; no rolling novel |
| N8 | [n8_stream_start_incar.md](tasks/n8_stream_start_incar.md) | yes — mutex + bridge; copy in N11 |
| N9 | [n9_overlay_cover.md](tasks/n9_overlay_cover.md) | **CUT** |
| N10 | [n10_watcher_log.md](tasks/n10_watcher_log.md) | **debug ring shipped**; public API deferred |
| N11 | [n11_content_fill.md](tasks/n11_content_fill.md) | A + sparse B/C/D |
| N12 | [n12_async_consumers.md](tasks/n12_async_consumers.md) | follow-up — Commentary Director V2 async isolation |
