# Session / stream reference (irsdk vs switcher)

## iRSDK weekend vs session

A **weekend** is one joined event (`WeekendInfo`, `SubSessionID`). Official
race, hosted, heat, … — one weekend usually has several **sessions**.

```
WeekendInfo.EventType     "Race" | "Practice" | …   product of the weekend
WeekendInfo.EventName     display name of the event
SessionInfo.Sessions[]     list of rows for this weekend
SessionNum                0-based index of the live row
Sessions[i].SessionType   "Practice" | "Lone Qualify" | "Race" | …
Sessions[i].SessionName    display ("PRACTICE", "QUALIFY", …)
SessionState              0 Invalid … 4 Racing … 5 Checkered … 6 CoolDown
SessionTime               seconds into the current session row
```

`WeekendInfo.EventType == "Race"` means “this weekend is a race weekend”,
**not** “we are in the Race session”. Live Quali on an official still has
`EventType=Race`. That fallback made overlay + commentary treat Quali as Race
(tape `overlayMode: RACE`, spoken `SESSION_INTRO_RACE`, zero `SECTOR_*`).

There is **no** live telemetry variable `SessionType` in modern irsdk.
`read_session_info()` and overlay `TELEMETRY_VARS` both must include YAML `SessionInfo`.
`extract_session_type()` is the only parser. `IRacingReader.session_sdk_payload()` is a cache of that dump, not a second extractor.

Numeric legacy map (only if a number appears): `0 Test, 1 Practice, 2 Qualify, 3 Warmup, 4 Race`.

## SessionState vs session type vs DrivingMode

| irsdk `SessionState` | Name | Switcher use |
| --- | --- | --- |
| 0 | Invalid | loading / no session |
| 1 | GetInCar | — |
| 2 | Warmup | **not** session type Warmup |
| 3 | ParadeLaps | — |
| 4 | Racing | green / running; `t_green`; also true in Practice |
| 5 | Checkered | `session_checkered` (`SessionState == 5` only); clock expired, out-lap still allowed |
| 6 | CoolDown | `player_finished` / `mute_field` fallback; `session_checkered` is **false** |

`SessionState=4` during Practice is normal. Do not infer `session_type=="Race"`.

`DrivingMode` (`extract_mode`): GARAGE (UI) > REPLAY > on-track in-car (`RACE`) > LOBBY.
Garage UI is `IsGarageVisible`, not stall physics. See rule `iracing-sdk-semantics`.

## Switcher field map

| Field | Owner | Source |
| --- | --- | --- |
| `SwitchState.session_type` | scene loop | `extract_session_type` → Practice/Qualify/Race/… |
| `SwitchState.session_name` | dashboard | row `SessionName` |
| `SwitchState.session_num` | dashboard | 0-based; display is `n+1 of total` |
| `TelemetrySnapshot.session_type` | overlay ingest | same extract |
| `RaceState.overlay_mode` | overlay/events | `overlay_mode_from_session_type` |
| `RaceState.session_checkered` | overlay | `SessionState == 5` only (not CoolDown, not client flag bit) |
| `RaceState.player_finished` | overlay | S/F or eligible pit-rise after checkered, or CoolDown. Already in pits at checkered is **not** finish |
| `RaceState.mute_field` | overlay | follows `player_finished`; post-race HUD/hunt mute |
| `RaceState.session_finished` | overlay | alias of `mute_field` |
| `build_session_key` | overlay reset | `subsession:session_num:track` |
| `StreamChapter.session_type` | VOD markers | same Title Case strings |
| `StreamMemory` | RaceObserver | survives session changes until OBS stream reset; quali bag = class position + best lap |

`RaceState` / `RaceObserver` / `RaceContextAnalyzer` are **historical names**.
They interpret telemetry for every overlay mode.

## Overlay string map

| `session_type` | `overlay_mode` | Tape | Sectors | Typical emitters |
| --- | --- | --- | --- | --- |
| Practice | PRACTICE | yes | yes | practice, target_locked, sectors |
| Qualify | QUALIFYING | yes | yes | quali, sectors |
| Race | RACE | yes | **no** | battle, overtake, hunting, … |
| Warmup | GENERIC | no | no | — |
| Test | (cleared) | no | no | — |
| None | GENERIC | no | no | — |

Config flags `[event_engine] practice` / `quali_projection` register sector
emitters together; they still **emit** only in PRACTICE and QUALIFYING.

## Stream (OBS / YouTube) — not irsdk

| Term | Meaning |
| --- | --- |
| stream | OBS output (`is_streaming`) |
| stream chapters | in-memory markers; optional YouTube VOD description after stop |
| `start_title` @ 0s | always on stream start (`session_type=None` on that marker) |
| later chapters | on `session_type` change into trigger set (default Practice, Qualify, Race) |
| YouTube OAuth | title/description of the **broadcast**, not iRacing session |
| `aiohttp.ClientSession` | HTTP client; ignore in this glossary |

RaceObserver: `reset_session()` on session_key change; `reset_stream()` on
OBS stream end / new broadcast. `StreamMemory.sessions_seen` is the
Practice→Qualify→Race list **inside one stream**.

## Weather module collision

In `iracing/weather.py`, **session** means `WeekendInfo.Track*` current-condition
fallbacks (vs live telemetry vs **forecast** `WeekendOptions`). Not session type.

## Tape clocks

| Key | Zero | Use |
| --- | --- | --- |
| `t_mono` | tape open | replay sleep |
| `t_stream` | OBS stream start | VOD sync; null if not streaming |
| `t_session` | irsdk `SessionTime` | session-row clock |
| `t_green` | first `SessionState==4` this tape | “since green” |
| `t` | — | stream else session else mono |

Tape file: `recordings/overlay-<utc>-<subsession>-<sessionNum>.jsonl`.

## Related docs / code

- `extract_session_type` / `resolve_session_identity` — `src/irswitch/iracing/extractors.py`
- Overlay map — `src/irswitch/overlay/session.py`
- DrivingMode — `src/irswitch/models.py`, `extract_mode()`
- Chapters — `src/irswitch/logic/stream_chapters.py`
- Inventory — `docs/scenario_coverage_matrix.md` §0
- Units/sentinels — skill `iracing-sdk-display-format`
