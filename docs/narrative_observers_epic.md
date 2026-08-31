# Narrative observers epic (stream → practice → quali → race → finish)

**Status:** product + engineering plan (docs only)  
**Date:** 2026-08-31  
**Depends on:** [scenario_coverage_matrix.md](scenario_coverage_matrix.md), [observers_decoupling_plan.md](observers_decoupling_plan.md)  
**Umbrella:** P0–P5 joint test [#179](https://github.com/Buchtanen/ir-obs-switcher/pull/179) (`feat/observers-decoupling-joint-test`) — this epic stacks **on that branch**, does not fork it.  
**Task slices:** [docs/tasks/](tasks/) (`n1`…`n11`) — later commits on the same umbrella after #179 is the base; not 11 PRs to `master`.

This epic expands the locked decoupling plan with the **broadcast story** we actually want: what speaks, what the overlay shows, and which watchers own which session.

---

## 0. Product story (what we want)

One stream, one voice, session-specific density. Watchers log what they saw. The sequence graph gets **depth** (mode + branch + edges), not a 5-D cell explosion.

```text
OBS stream goes live
  → long welcome TTS (context) + optional big overlay cover/summary
Get in the car (often still in pit)
  → Practice: next run / what this session is for
  → Quali: why the lap matters
  → Race: grid / start
Practice / Quali
  → incidents (off-track / contact car|object / lost-control)
  → sector + lap-time improvement
  → position gain/lost after a pass, with time
  → hunt a *position by lap time*, not the bumper gap
  → leader pace as vata, at most 1× / 5 min
Race (different sport)
  → short Quali recap while waiting for green
  → rolling-start padding (new texts + maybe new beats)
  → full battle + incident firehose
  → aftermath: stalled/slow → rolling again = recovered
  → chains: lost-control / off-track can become contact
Flags in every session + graph branches
Finish ≠ checkered announcement
  → first: s/f crossing after checkered, or pit entry after checkered
```

Voice stays **viewer-facing third person** (`COMMENTARY_ENGINE.md`). Overlay HUD priorities stay visual; voice has its own graph priorities + scheduler (P1).

---

## 1. Relation to the decoupling plan

| Plan item | This epic |
| --- | --- |
| P0 fan-out | Keep (already in stack). Overlay and commentary are peers. |
| P1 SpeechScheduler | Keep. Defer / hard_interrupt / 33 s silence. |
| P2 RaceObserver MVP | Keep as **kernel**: `StoryContext` 2+2, weather, field facts, session reset. |
| P3 incident aftermath | **Keep** (`INCIDENT_AFTERMATH` / `BACK_UNDER_WAY` on #174). **N1** adds `Speed`; **N3** adds kinds / chain / recovered copy on top of that FSM. |
| P4 session wrap/preview | **Keep** (`SESSION_WRAP` / `SESSION_PREVIEW` on #176). **N7** adds grid/rolling; **N8** adds stream-start + in-car flavor. |
| P5 content gaps | **Keep** (#179 / #178 `ATTACK_RANGE` + `PIT_STOPPED`). **N2** + **N11** add further graph layers/texts. |
| Locked: near field 2+2, hard_interrupt ini, LLM past-only, finish still highest HUD prio | Unchanged. |

P0–P5 live on umbrella **#179**. This epic stacks on that branch. Do not fork P3/P4/P5.

---

## 2. iRSDK: what we can actually know

Do **not** invent telemetry names. Extraction stays in `iracing/` (no policy).

### 2.1 Already on `TelemetrySnapshot`

| Var | Use |
| --- | --- |
| `PlayerCarMyIncidentCount` | Incident **counter only** — no type enum |
| `PlayerTrackSurface` / `CarIdxTrackSurface` | `OffTrack=0`, `InPitStall=1`, `ApproachingPits=2`, `OnTrack=3` |
| `CarDistAhead` / `CarDistBehind` / `CarIdxLapDistPct` | Nearby-car heuristic |
| `OnPitRoad`, `PlayerCarTowTime` | Pit vs tow vs stalled |
| `SessionFlags` | Present, **unused by emitters today** |
| `SessionState` | 1 GetInCar, 2 Warmup, 3 **ParadeLaps**, 4 Racing, 5 Checkered, 6 CoolDown |
| Weather live vars | Session briefs / P2 weather watch |

### 2.2 Must extract (N1) — official names

| Var | Unit | Why |
| --- | --- | --- |
| `Speed` | m/s | Aftermath: stopped / crawling / rolling |
| `Yaw` / `YawRate` | rad / rad·s⁻¹ | Lost-control |
| `VelocityX`, `VelocityY` | m/s | Heading vs velocity slip |
| `LatAccel`, `LongAccel` | m/s² | Spin / impact spike |
| `SteeringWheelAngle` | rad | Optional support for lost-control |

Optional later (not required for N1): `PlayerCarInPitStall`, `YawNorth`.

### 2.3 Incident kinds — **heuristic, not an SDK enum**

iRacing does **not** publish “off-track vs car vs wall” as a typed incident. `PlayerCarMyIncidentCount` just ticks. Classification is a **confidence-tagged watch** over a short window (≈1–4 s) around the increment:

| Kind | Evidence (priority order) | Confidence |
| --- | --- | --- |
| `off_track` | `PlayerTrackSurface == OffTrack` held ≥ N ms around the tick | **high** (direct TrkLoc) |
| `lost_control` | On-track (or just leaving): `YawRate` spike and/or velocity-heading mismatch + speed still material | **medium** |
| `contact_car` | Increment + another car within distance/lap-pct gate (and/or tiny `CarDistAhead/Behind`) | **medium** |
| `contact_object` | Increment + **no** nearby car + not a clean off-track story (wall / unknown) | **low–medium** |
| `chain` | `lost_control` and/or `off_track` in window **then** contact | **medium** (composition) |

If evidence conflicts, emit the **most specific** kind plus `metrics.chain` / `metrics.confidence`. Never claim car-vs-wall as fact when confidence is low — graph lines must have a slot-free / vague fallback.

Practice copy: **more text** on off-track; contact split when confidence allows; lost-control as its own branch.

### 2.4 Flags

Decode `SessionFlags` bits in `iracing/` (pure helper). Speak on **rising edges** with per-flag cooldown. Product-relevant bits:

| Bit (hex) | Name | Speak? |
| --- | ---: | --- |
| `0x00000001` | checkered | **yes, as flag** — not finish |
| `0x00000002` | white | yes (race; rare elsewhere) |
| `0x00000004` | green | yes (start / restart) |
| `0x00000008` / `0x00000100` | yellow / yellowWaving | yes |
| `0x00000010` | red | yes |
| `0x00000020` | blue | yes (being lapped) |
| `0x00004000` / `0x00008000` | caution / cautionWaving | yes (often with yellow) |
| `0x00010000` | black | yes |
| `0x00020000` | disqualify | yes, rare |
| `0x00100000` | repair (meatball) | yes |
| `0x10000000`…`0x80000000` | startHidden / Ready / Set / Go | rolling/standing start padding |
| `0x00040000` | servicible | no TTS (pit service permission) |

Same watcher in Practice/Quali/Race; **graph nodes** differ by `overlay_mode` (N2).

### 2.5 Finish (today vs wanted)

Today (`race/context.py`): `session_finished = SessionState in {5, 6}` and `SessionEmitter` fires `finish` on that edge. `filter_post_race` then mutes almost everything.

Wanted:

| Signal | Meaning |
| --- | --- |
| Field checkered | `SessionState == 5` (or checkered flag bit) — **flag beat**, not hero finish |
| Player finished | first of: **lap complete / s/f crossing** while field is checkered, **or** pit-road entry after checkered |
| Fallback | `SessionState == 6` CoolDown if the hero never crossed (DNF / tow / DC) — still emit finish once |

Split the boolean. Do **not** keep using `session_finished` as both “mute the field” and “hero done”. See **N4**.

---

## 3. RaceObserver — proposed shape (the strong one)

Not an LLM loop. Not a second EventEngine. A **stateful interpreter** next to emitters: memory + derived candidates + watcher logs. Emitters keep atomic edges (lap, gap hunt in race, pit FSM). The observer owns **arcs** that need memory.

```text
TelemetrySnapshot
        │
RaceContextAnalyzer → RaceState          (hero, 1+1 HUD neighbors, lap flags)
        │
        ├─ EventEngine emitters          (atomic: lap, battle-gap, pit, …)
        │
        └─ RaceObserver                  (this epic)
              StoryContext (P2): hero + 2+2, weather, stream memory
              watches (N3–N7): incident, flags, pace, timing-hunt, grid, finish
              session policy: Practice | Quali | Race
              → derived CandidateEvent[]  (COMMENTARY_ONLY unless HUD is explicit)
        │
        ▼
Shared arbitration → fan-out → OverlaySink | CommentaryPath | Tape
```

### 3.1 Kernel (issue #170 / P2 — do not redesign)

- `StoryContext`: hero + **2 ahead + 2 behind**, names, gaps, class positions  
- Bounded stream memory keyed by `(SubSessionID, SessionNum)` plus a small **weekend bag** (last quali result → race recap)  
- Weather thresholds → `WEATHER_CHANGE`  
- Field facts for 33 s silence (P1), **except** leader-pace which is capped **1× / 5 min** (N6 policy)  
- Fail-soft; never throw into the race loop  

Battle HUD may stay 1+1. Observer 2+2 is for story / filler / chains.

### 3.2 Watches (new)

| Watch | Emits | Session |
| --- | --- | --- |
| `IncidentWatch` | kind, chain, aftermath, recovered | all (copy differs) |
| `PaceWatch` | stalled / slow / rolling using `Speed` | mainly race aftermath; practice recovery optional |
| `FlagWatch` | rising-edge flags | all |
| `TimingHuntWatch` | hunt **position by lap/projected time** | Practice + Quali only |
| `GridWatch` | wait-for-green, parade/rolling padding, quali recap | Race |
| `FinishWatch` | player finished (cross or pit) | Race (and timed quali if we ever need it) |

Each watch: `tick(ctx, state, snap, now) -> list[DerivedEvent]`. Shared monotonic clock. Each decision **logged** (N10).

### 3.3 Session policies (strategy, not a 2000-line `if`)

**Practice** — viewer cares about the run, not bumper wars:

- Incident branches with **longer off-track** copy  
- Sector gain/loss and lap PB (existing `PracticeEmitter` / `LapEmitter` — do not duplicate)  
- After a **pass**: position gained/lost + time (existing position path; observer may add a “with time” slot if missing)  
- **Hunting** = “this lap/best is attacking P{n}’s time”, **not** `gap_ahead`  
- Gate or ignore `BattleEmitter` gap-hunt in PRACTICE (config, default: suppress gap-hunt TTS in P/Q)  
- Leader reference time: filler, **≤ 1× / 5 min**, never on cooldown of a better beat  

**Quali** — same skeleton as practice, plus existing projection / hot lap / position attack. Timing-hunt aligns with “can this lap take P{n}”. Gap-hunt still off for TTS.

**Race** — different sport:

- Gap hunting / hunted / SBS / overtake: **keep BattleEmitter** (this is real traffic)  
- Observer adds: quali recap on grid, rolling-start vata, flag story, incident chains + recovered, finish crossing  
- Full comment density; P1 scheduler + hard_interrupt is the safety valve  
- After lost-control or incident: PaceWatch until rolling `BACK_UNDER_WAY` / `INCIDENT_RECOVERED`  

### 3.4 Incident arc FSM (N3)

```text
IDLE
  → LOST_CONTROL? (physics, optional)
  → OFF_TRACK?    (TrkLoc)
  → CONTACT?      (count↑ + car|object)
  → AFTERMATH     (speed < crawl for T_stop, or slow < T_slow)
       → RECOVERED (speed ≥ roll for T_hold) 
       → TOWED     (PlayerCarTowTime > 0)
       → RESET     (ESC teleport / session change)
```

Windows are time-based (monotonic), not frames. A chain is one `correlation_id`. Practice may speak the first kind loudly and skip recovered; race speaks recovered when the car actually goes again.

### 3.5 What RaceObserver must not do

- Call TTS or know overlay widgets  
- Re-implement lap/sector math (`TimingStore` already exists)  
- Re-implement gap hunting for race HUD  
- Unbounded transcript  
- LLM to decide event types  

---

## 4. Sequence graph — more layers without combinatorics

Today: `node → variants[locale][emotion]` (graph v1). Edges are weak preferences.

**Do not** add `emotion × mode × branch × locale` cells. That is unauthorable.

**Do** add **selectable nodes** (graph v2, additive):

```text
nodes_for(event_type, phase, mode, branch) →
  1. event + phase + mode + branch
  2. event + phase + branch
  3. event + phase + mode
  4. event + phase          (today)
```

- **Mode layer:** `overlay_mode` filter on the node (`PRACTICE` / `QUALIFYING` / `RACE`).  
- **Branch layer:** `metrics.branch` (`off_track`, `contact_car`, `contact_object`, `lost_control`, `recovered`, `yellow`, …).  
- **Sequence layer:** edges between those nodes (`lost_control` → `contact_car`, `incident` → `incident_recovered`).  
- **Length layer:** per-node `tts.max_seconds` / `max_chars` (already exists). Stream welcome uses a **long** cap (e.g. 18 s / ~280 chars); race incidents stay short.

New node families (content in N11, schema in N2):

| Node id (proposal) | Event | Notes |
| --- | --- | --- |
| `stream_start` | `STREAM_START` | Long welcome; context slots |
| `in_car_practice` / `_qualify` / `_race` | `ENTER_CAR` | Replace generic-only `in_car` via mode select |
| `incident_off_track` | `INCIDENT` branch | More text in P/Q |
| `incident_contact_car` / `_object` / `_lost_control` | `INCIDENT` | Fallback generic `incident` remains |
| `incident_recovered` | `INCIDENT_RECOVERED` | Race |
| `flag_*` | `SESSION_FLAG` | One node per speakable flag, mode-filtered lines |
| `rolling_start` / `grid_wait` | `ROLLING_START` / `GRID_WAIT` | Race padding + quali recap slots |
| `pace_hunt` | `PACE_HUNT` | P/Q position-by-time |
| `leader_pace` | `FIELD_FACT` branch `leader` | 5 min cap in observer, not graph |
| `finish` | `FINISH` | Only player finished (N4) |
| `flag_checkered` | `SESSION_FLAG` | Checkered **flag**, not finish |

`ATTACK_RANGE` TTS stays a small P5 leftover unless a node is cheap once N2 exists.

---

## 5. Stream start + overlay cover

Two consumers, **one snapshot** (`StreamStartContext`): track, session type, field size, SoF if known, weather one-liner, weekend name.

| Surface | Behavior |
| --- | --- |
| TTS | Longer commentary; trigger from existing OBS edge `obs_stream_started` in `main.py` (fail-soft if overlay runtime missing). Feature flag default **off**. |
| Overlay | Optional **full-bleed cover + summary** (N9). Not an OBS scene switch. Auto-hide after timeout or `ENTER_CAR`. |

Cover is optional (“mohl”). TTS welcome is in-scope for N8 even if N9 slips.

In-car in the pit is **not** stream start: `InCarDetector` already fires once per seated stint; N8 adds **mode-specific copy** (next practice attempt / quali stakes / race start). Session intros (`session_briefs`) stay the once-per-session track/SoF/weather pack — do not merge them into in-car.

---

## 6. Hunting: two different sports

| Session | “Hunting” means | Owner |
| --- | --- | --- |
| Practice / Quali | Hero lap or projected vs the time that currently holds P{n} | `TimingHuntWatch` (N6) |
| Race | Gap + closing on the car ahead/behind | existing `BattleEmitter` |

Leader time in P/Q is **not** hunting. It is filler, max **1× / 5 minutes**, skipped if a better timing/incident beat is fresh.

---

## 7. Parallel plan (do not launch agents until this is approved)

### sequential (dependencies)

```text
Umbrella #179 (P0–P5 joint test)
  → this docs epic (stacked here)
  → N-tasks as later commits on the same umbrella (not extra PRs to master)
```

Do **not** start N-task implementation until umbrella #179 is the base (joint test). Then sequential commits on that same branch.

### commit slices on the umbrella (not extra PRs to master)

| Slice | Owns | Must not clash in the same commit |
| --- | --- | --- |
| **N1** iRSDK extract | `iracing/telemetry.py` additive vars, `overlay/models.py` additive fields, new `iracing/session_flags.py` | emitters / director |
| **N2** graph select | `commentary/graph.py`, validator | director until texts exist |
| **This docs slice** | `docs/narrative_observers_epic.md`, `docs/tasks/*` | runtime |

### skip / later

- OBS scene for cover (stay overlay browser source)  
- Official iRacing incident-type enum (does not exist)  
- LLM event picker  
- New TTS engine / new pip deps  
- Past-tense duplicate graph cells  

---

## 8. Config impact (planned, not in this PR)

| Key | Default | Task |
| --- | --- | --- |
| existing `[commentary.scheduler].*` | safe/off | P1 |
| `commentary.stream_start` | `false` | N8 |
| `overlay.stream_cover` | `false` | N9 |
| `event_engine.gap_hunt_in_practice` / `_qualifying` | `false` (TTS suppress) | N6 |
| `race_observer.leader_pace_cooldown_s` | `300` | N6 |
| `race_observer.incident_classify` | `true` once shipped | N3 |
| flag speak cooldowns | per flag | N5 |

No default chatter increase on existing installs until flags are opted in (same posture as `commentary.enabled`).

---

## 9. Docs / test posture

- This PR: **docs only**. TDD-exception: no runtime.  
- Each N-task: unit tests with fake clock + synthetic snapshots (mandatory for FSMs).  
- Live iRacing: manual on stream PC after flags on; never required to merge a slice.  
- Update `CONFIG.md` + `config.example.ini` + `COMMENTARY_ENGINE.md` + this epic’s status when a slice ships.  
- `API.md` only if watcher log or cover state is exposed.

---

## 10. Issue-ready task index

| ID | Doc | Issue when approved |
| --- | --- | --- |
| N1 | [n1_irsdk_dynamics_flags.md](tasks/n1_irsdk_dynamics_flags.md) | extract Speed/yaw/flags |
| N2 | [n2_graph_mode_branch.md](tasks/n2_graph_mode_branch.md) | graph select layers |
| N3 | [n3_incident_classifier.md](tasks/n3_incident_classifier.md) | kinds + chain + recovered |
| N4 | [n4_finish_semantics.md](tasks/n4_finish_semantics.md) | finish ≠ checkered |
| N5 | [n5_flags_observer.md](tasks/n5_flags_observer.md) | flags all sessions |
| N6 | [n6_practice_quali_pace.md](tasks/n6_practice_quali_pace.md) | hunt-by-time + leader 5 min |
| N7 | [n7_race_start.md](tasks/n7_race_start.md) | quali recap + rolling start |
| N8 | [n8_stream_start_incar.md](tasks/n8_stream_start_incar.md) | welcome TTS + in-car flavor |
| N9 | [n9_overlay_cover.md](tasks/n9_overlay_cover.md) | optional big cover |
| N10 | [n10_watcher_log.md](tasks/n10_watcher_log.md) | observer decision log |
| N11 | [n11_content_fill.md](tasks/n11_content_fill.md) | EN+CS lines for new nodes |
