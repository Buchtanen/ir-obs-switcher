---
name: iracing-session-glossary
description: >-
  Canonical irswitch vs iRSDK meanings of session, stream, weekend, race,
  practice, qualify, DrivingMode, overlay_mode, SessionState, SessionType,
  EventType, SubSessionID. Use when writing extractors, overlay, commentary,
  stream chapters, race observer, tape clocks, or whenever session_type,
  overlayMode, EventType, OBS stream, Practice/Quali/Race, or DrivingMode.RACE
  appear. Prevents mixing weekend product with live session and on-track with Race.
---

# iRacing session / stream glossary

Load this skill before naming fields, gating emitters, or reading `SessionType` /
`EventType` / `overlay_mode` / `DrivingMode`. Wrong name → wrong gate → Quali
runs as Race (no sectors, `SESSION_INTRO_RACE` during Qualify).

Canonical extract: `extract_session_type()` in `src/irswitch/iracing/extractors.py`.
Canonical overlay map: `overlay_mode_from_session_type()`.

Full tables: [reference.md](reference.md). Bad vs good diffs: [examples.md](examples.md).

## Layers (never collapse)

```
OBS stream (broadcast)     1× per Go Live → Stop
  └── iRacing weekend      1× SubSessionID (official/hosted instance)
        └── session row    SessionInfo.Sessions[SessionNum]
              Practice | Qualify | Race | Warmup | Test
```

| Word in chat | Means | Canonical in code |
| --- | --- | --- |
| stream | OBS is broadcasting | `streaming`, `t_stream`, `StreamChapterTracker`, `StreamMemory` |
| weekend | one iRacing event instance | `WeekendInfo`, `subsession_id` |
| session | **one row** of that weekend | `session_type`, `session_num`, `session_key` |
| pract / practice | that row is Practice | `session_type == "Practice"` → `overlay_mode == "PRACTICE"` |
| qual / quali | that row is Qualify | `session_type == "Qualify"` → `overlay_mode == "QUALIFYING"` |
| race (session) | that row is Race | `session_type == "Race"` → `overlay_mode == "RACE"` |
| race (on-track) | player in car on track | `DrivingMode.RACE` — **any** session type |
| racing (green) | session clock running | `session_state == 4` (irsdk Racing) — **any** session type |

## Canonical strings

**`session_type`** (switcher / snapshot / chapters): Title Case from YAML.

`Practice` | `Qualify` | `Race` | `Warmup` | `Test`

- `"Lone Qualify"` / `"Open Qualify"` / `"Qualifying"` → **`Qualify`**
- `Test` → switcher identity **clears to None** (`resolve_session_identity`)
- **Never** store `"QUALIFYING"` or `"PRACTICE"` in `session_type`

**`overlay_mode`** (HUD / emitters / commentary envelopes):

`PRACTICE` | `QUALIFYING` | `RACE` | `GENERIC`

Map only via `overlay_mode_from_session_type(session_type)`. Warmup/Test/unknown → `GENERIC` (no tape).

**`DrivingMode`** (`SwitchState.mode`, OBS scenes): where the sim UI/car is.

`CONNECTING` | `LOADING` | `LOBBY` | `GARAGE` | `RACE` | `REPLAY` | `QUIT` | `RESTART`

`DrivingMode.RACE` = on-track in-car. True in Practice and Qualify.

**CLI `--overlay-mode`**: `live` | `mock` | `replay`. Pipeline input. Unrelated to the two above.

## Hard don'ts

1. **Do not** use `WeekendInfo.EventType` as live session type. It is the weekend **product** (official race weekend → `"Race"` while you are still in Practice/Qualify).
2. **Do not** read a live telemetry var named `SessionType`. Modern irsdk has none. Source is YAML `SessionInfo.Sessions[SessionNum].SessionType` (fallback: that row's `SessionName`, then legacy top-level `SessionType`/`SessionName`).
3. **Do not** gate overlay/commentary on `DrivingMode.RACE`. Gate on `overlay_mode` / `session_type`.
4. **Do not** gate OBS scene switch on `session_type`. Scenes follow `DrivingMode`.
5. **Do not** call OBS stream an iRacing session. Chapters and `t_stream` are OBS-clock. `t_session` is `SessionTime`. `t_green` is first `SessionState==4` on **this tape**.
6. **Do not** treat `src/irswitch/race/` or `RaceState` as Race-session-only. They run in PRACTICE/QUALIFYING too. `SessionEmitter` has **no** `overlay_mode` gate.
7. **Do not** invent a new field named `mode`, `session`, or `race` without a prefix (`overlay_mode`, `session_type`, `driving_mode`, `streaming`).
8. **One extract path.** `SwitchState.session_type` and `TelemetrySnapshot.session_type` both call `extract_session_type()` on a dump that includes YAML `SessionInfo`. `read_session_info()` is the same parser after `SESSION_INFO_VARS`. Empty overlay cache → `read_session_info()`, not a third fallback.

## Which clock / id

| Need | Use |
| --- | --- |
| Which weekend instance | `subsession_id` (`SubSessionID`) |
| Which row inside it | `session_num` (0-based) |
| Reset overlay stores | `session_key` = `{subsession}:{session_num}:{track}` |
| Commentary brief once | `(SubSessionID, SessionNum)` |
| Memory across Practice→Race | `StreamMemory` / `reset_stream()` — OBS-stream scoped |
| VOD chapter offset | OBS stream duration (`offset_seconds`), not `SessionTime` |
| Tape replay sleep | `t_mono` |
| Tape sync to VOD | `t_stream`, else `t_session`, else `t_mono` (`t`) |

## Gate cheat sheet

| Feature | Gate |
| --- | --- |
| OBS scene | `DrivingMode` |
| Overlay tape write | `overlay_mode in {PRACTICE, QUALIFYING, RACE}` |
| Sector HUD | `overlay_mode in {PRACTICE, QUALIFYING}` |
| Practice emitters | `overlay_mode == "PRACTICE"` |
| Quali emitters | `overlay_mode == "QUALIFYING"` |
| Session intro speech | `session_type` ∈ Practice/Qualify/Race (once per session key) |
| SoF brief | Race **session** only (after intro) |
| Stream chapters | OBS `streaming` + `session_type` change ∈ triggers |
| `session_finished` / after_session | driver done: S/F after checkered, or not on a flying lap at checkered, or CoolDown — not raw `session_state==5` |
| Invalid lap | `overlay_mode in {PRACTICE, QUALIFYING}` only |

## Checklist before coding

- [ ] Name the layer: driving / session row / overlay / OBS stream / weekend
- [ ] `session_type` values are Title Case; `overlay_mode` is SCREAMING
- [ ] New extract goes through `extract_session_type`, not `EventType`
- [ ] Both switcher and overlay dumps include `SessionInfo` (one algorithm)
- [ ] Emitter gate uses `overlay_mode`, not `DrivingMode`
- [ ] Tests include a race-weekend fixture: `EventType=Race` + `SessionNum=1` → Qualify
