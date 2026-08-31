# Scenario coverage matrix (overlay · commentary · OBS)

**Status:** inventory (docs only)  
**Source of truth analyzed:** `feat/ollama-vod-joint-test` @ `0997ffc` (reconciled into this docs branch)  
**Independent review:** second Cursor model vs code, confidence **96/100**  
**Related:** [observers_decoupling_plan.md](observers_decoupling_plan.md), [narrative_observers_epic.md](narrative_observers_epic.md)

## 0. Two session concepts — do not mix

| Layer | Concept | Values | Meaning |
| --- | --- | --- | --- |
| **OBS autoswitch** | `DrivingMode` | `CONNECTING`, `LOADING`, `LOBBY`, `GARAGE`, `RACE`, `REPLAY`, `QUIT`, `RESTART` (`IDLE` deprecated) | Where the sim UI / car is. **`RACE` = on-track**, even in Practice/Quali session. |
| **Overlay / events / commentary** | `overlay_mode` | `PRACTICE`, `QUALIFYING`, `RACE`, `GENERIC` | From iRacing `SessionType` (`warmup`/`test` → `GENERIC`). |

OBS scenes in `config.example.ini`: `IDLE`, `GARAGE`, `RACE`, `REPLAY`, `QUIT` (`RESTART` optional). `LOBBY` resolves to the `IDLE` scene.

## 1. Pipeline (current)

```text
TelemetrySnapshot
  → RaceContextAnalyzer → RaceState
  → EventEngine (emitters) → CandidateEvent[]
  → EventManager(V2) arbitration (priority, cooldown, PitCycleGuard, post-race filter)
  → EventEnvelope / wire
       → OverlayBus (HUD widgets)          ← peer path
       → EventFanout → CommentaryConsumer  ← peer path (P0; was chained in OverlayRuntime)
            → anti-repeat → optional LLM polish → TTS sink
```

**Sidecars (commentary):** `InCarDetector` (`ENTER_CAR`), `SessionBriefsDetector` (intros / SoF / weather) — not classic emitters.

## 2. Feature defaults (`config.example.ini`)

### `[event_engine]` (example profile = all on)

| Key | Example | Effect |
| --- | --- | --- |
| `practice` | `true` | `PracticeEmitter`, `TargetLockedEmitter` + sector emitters |
| `quali_projection` | `true` | `QualiEmitter` + sector emitters |
| `overtake_classifier` | `true` | Replaces `PositionEmitter` with classifier |
| `pit_story` | `true` | `PitStoryEmitter` FSM (else simple `PitEmitter`) |
| `hr_pressure` | `true` | `HrPressureEmitter` |
| `v2_payload` | `true` | V4 envelope path |

**Sector coupling:** enabling **either** `practice` **or** `quali_projection` registers **both** sector emitters; they then emit in PRACTICE **and** QUALIFYING.

Missing `[event_engine]` section → code defaults (flags off).

### `[commentary]`

| Key | Example | Notes |
| --- | --- | --- |
| `enabled` | `false` | Master gate |
| `sector_speak` | `false` | Opt-in sector absolute-time TTS |
| `session_briefs` | `false` | Opt-in intro / SoF / weather |
| `llm_polish` | `false` | Optional remote polish |
| `cooldown_s` | `4.0` | Global gap between utterances |
| `use_hr_emotion` | `true` | BLE HR → emotion bands |

`ENTER_CAR` is **not** gated by `session_briefs` — only by `commentary.enabled`.

## 3. Arbitration (shared)

| Priority | Events (approx.) |
| --- | ---: |
| 100 | `finish` |
| 95 | `final_lap` |
| 90 | `incident`, `invalid_lap`, `link_drop` |
| 80 | `overtake` |
| 70 | `position_change`, `rival_threat` |
| 60 | `personal_best`, `sector_best` |
| 55 | `position_attack`, `hot_lap` |
| 50 | pit story phases |
| 45 | `gain_found`, `time_lost`, `sector_split`, `clean_streak` |
| 42 | `projected_lap`, `target_locked` |
| 40 | `lap_complete` |
| 35 | bio / HR |
| 30 | `battle_for_position`, `battle_won` |
| 20 | hunting ladder |
| 15 | system (debug) |

**PitCycleGuard:** on pit road + **5 s** post-exit grace, suppresses **`trigger`/`enter` only** for `position_change`, `overtake`, `battle`, `rival_threat` (`update`/`exit` still pass).

**Post-race:** after `session_finished`, filter keeps essentially finish / final EXIT.

**Channel caps (HUD):** battle 2; timing/position/exception/pit/bio/session 1.

“Always registered” emitters still obey connectivity, cooldowns, arbitration, pit guard, post-race filter.

## 4. Coverage matrix

Legend: **W** = widget / HUD · **C** = commentary node · **yes** / **opt-in** / **partial** / **no** / **n/a**

### 4.1 OBS scenes

| Situation | Trigger / tracks | Does | W | C |
| --- | --- | --- | --- | --- |
| CONNECTING | SDK connect handshake | Hold scene (`waiting_for_both`) | n/a | n/a |
| LOADING | Post-connect load | No switch; then 3 s LOBBY/GARAGE grace | n/a | n/a |
| LOBBY | Session lobby, not garage UI | Switch to `[scenes].IDLE` | n/a | n/a |
| GARAGE | `IsGarageVisible` (+ grace rules) | Switch to `[scenes].GARAGE` | n/a | n/a |
| RACE (on-track) | On-track + in-car | Switch to `[scenes].RACE` (any SessionType) | n/a | n/a |
| REPLAY | Replay detection | Switch to `[scenes].REPLAY` | n/a | n/a |
| QUIT | iRacing quit | Switch to `[scenes].QUIT` | n/a | n/a |
| RESTART | Optional `restart_hotkey` on quit | Hold / restart flow (`no_switch`) | n/a | n/a |

Also: manual override, autoswitch disabled, debounce, cooldown — state machine gates, not events.

### 4.2 Timing

| Situation | Session | Trigger | W | C | Flag |
| --- | --- | --- | --- | --- | --- |
| Lap complete | All | Lap↑ + valid last lap + no incident on lap | yes `lap_complete` prio 40 | yes node cd 8 / pri 40 | core |
| Personal best | All | \|last−best\| &lt; 0.005 s, lap &gt; 1 | yes `personal_best` 60 | yes cd 12 / pri 65 | core |
| Gain found | P | Minisector Δ ≤ −0.05 s | yes `gain_found` | yes cd 10 | `practice` |
| Time lost | P | Minisector Δ ≥ +0.08 s | partial → `gain_found` plate | yes `time_lost` | `practice` |
| Target locked | P | First valid best lap | yes `target` | yes cd 20 | `practice` |
| Sector split | P/Q | S1/S2/S3 crossing | partial → `gain_found` | opt `sector_split` | practice\|quali + `sector_speak` |
| Sector best | P/Q | Improves sector best | yes `pb_attack` | opt (same node) | same |
| Projected lap | Q | ≥15% progress, conf ≥ 0.35 | yes persistent | yes cd 12 | `quali_projection` |
| Hot lap | Q | ≥35% + projected &lt; best−0.05 | yes | yes cd 15 | `quali_projection` |
| Position attack | Q | projected &lt; best−0.05, conf ≥ 0.7 | yes | yes cd 12 | `quali_projection` |
| Clean streak | All | ≥3 clean laps | yes | yes cd 30 / pri 30 | core |

### 4.3 Battle

| Situation | Session | Trigger | W | C | Notes |
| --- | --- | --- | --- | --- | --- |
| Hunting | All\* | Gap ahead &lt; enter + closing, activation delay | yes persistent | yes (+ APPROACH) | No `overlay_mode` gate; abort on finish |
| Approach | All\* | Intensity ~1.5 s gap | yes | partial (shares `hunting`) | |
| Attack range | All\* | Gap ≤ ~0.8 s | yes | **no** dedicated node | Known gap |
| Side by side | All\* | Gap ≤ ~0.35 s | yes | yes | |
| Hunted | All\* | Mirror behind | yes | yes | PitCycleGuard |
| Battle for position | All\* | Hunting ∧ hunted active | yes prio 30 | partial → `side_by_side` node | |
| Battle won | All\* | Exit hunting from attack/SBS peak only | yes | yes | Not every position win |

\*Not mode-gated; practically race traffic.

### 4.4 Position

| Situation | Trigger | W | C | Flag |
| --- | --- | --- | --- | --- |
| Position gained/lost | Class/overall position stable `position_stable_seconds` | yes | yes | core / classifier |
| Overtake | Gain + confident pass (gap, not pit) | yes prio 80 | yes cd 8 / pri 85 | `overtake_classifier` |
| Rival threat | Closing behind ≥ 0.25, gap ≤ 2.5 s | yes | yes cd 20 | Modes P/Q/R |

### 4.5 Pit

| Situation | Trigger | W | C | Flag |
| --- | --- | --- | --- | --- |
| Pit entry | `on_pit_road`↑ + `should_begin_pit_cycle` (prior on-track; reject lobby spawn/tow/finished) | yes | yes | story or simple |
| Pit lane | FSM on pit, not stopped | yes | **no** | `pit_story` |
| Pit stopped | Dist eps held 1.5 s | yes | **no** | `pit_story` |
| Pit released | Moving again on pit road | yes | **no** | `pit_story` |
| Pit exit | `on_pit_road`↓ | yes | yes `back_on_track` | |
| Pit outcome | End of cycle / net delta | yes | yes (`PIT_OUTCOME`\|`PIT_EXIT`) | `pit_story` |

### 4.6 Exception / session / bio / sysinfo

| Situation | Session | Trigger | W | C |
| --- | --- | --- | --- | --- |
| Incident | All | Incidents ↑ ≥ `incident_min_delta` (default 2) | yes prio 90 | yes pri 88 |
| Invalid lap | All | Lap end with incident since lap start | yes | yes |
| Link drop | All | Stale/degraded/disconnect | yes lifecycle | **no** |
| Final lap | All\* | `is_final_lap` (no mode gate) | yes 95 | yes cd 60 |
| Finish | All\* | `session_finished` (no mode gate) | yes 100 | yes cd 120 |
| HR pressure | All | Bio `pushing`/`high` | yes | yes |
| BLE lost | All | HR provider disconnect inject | yes | **no** |
| Sysinfo bar | All | Continuous sample | persistent bar | n/a |
| CPU/GPU temp high | All | **Debug inject catalog only** (not normal emitter) | opt if `system_events_on_overlay` | **no** |

\*Race-oriented in practice; code does not filter `overlay_mode`.

### 4.7 Commentary sidecars

| Situation | Session | W | C | Gate |
| --- | --- | --- | --- | --- |
| Enter car | All | no | yes `in_car` | `commentary.enabled` |
| Session intro P/Q/R | P/Q/R | no | opt | `session_briefs` |
| SoF brief | R | no | opt | `session_briefs` |
| Weather brief | All | no | opt | `session_briefs` |

## 5. Widget catalog notes

From `event_catalog.json` fallbacks:

| Event | Maps to state |
| --- | --- |
| `TIME_LOST` | `gain_found` |
| `SECTOR_SPLIT` | `gain_found` |
| `SECTOR_BEST` | `pb_attack` |
| `NO_IMPROVEMENT` | `projected_lap` |
| `OVERTAKEN` | `position_lost` |
| `BATTLE_LOST` | `hunted` |
| `HEART_RATE` | `hr_pressure` |
| `CPU_TEMP_HIGH` / `GPU_TEMP_HIGH` | `incident` plate |

`composure_test` / `high_load`: theme manifest only — **no emitters**.

## 6. Known gaps (product)

1. `ATTACK_RANGE` — HUD yes, TTS via graph node `attack_range` (P5)  
2. `PIT_LANE` / `PIT_RELEASED` — HUD yes, TTS no; `PIT_STOPPED` optional mid-pit TTS (P5)  
3. `LINK_DROP`, `BLE_LOST`, CPU/GPU — no TTS (CPU/GPU not live emitters)  
4. `TIME_LOST` / `SECTOR_SPLIT` — plate fallback / sector speak opt-in  
5. Reserved bio plates without emitters  
6. OverlayRuntime chains commentary observe after HUD publish (see decoupling plan)

## 7. Evidence map

| Area | Paths |
| --- | --- |
| Emitters | `src/irswitch/events/*.py`, `engine.py`, `overlay/runtime.py` register hooks |
| Arbitration | `events/arbitration.py`, `manager*.py`, `session_phase.py` |
| Catalog | `src/irswitch/web/themes-v4/event_catalog.json` |
| Commentary graph | `src/irswitch/commentary/data/sequence_graph.json` |
| Director busy skip | `commentary/director.py` (`reason=busy`) |
| OBS SM | `logic/state_machine.py`, `models.py` `DrivingMode` |
| Race context | `race/context.py`, `race/opponents.py` |
| Config | `config/config.example.ini` |

## Docs impact

- New: this file  
- Related plan: [observers_decoupling_plan.md](observers_decoupling_plan.md)  
- No config/API change in this docs-only change
