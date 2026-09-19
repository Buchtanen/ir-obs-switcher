---
name: overlay-tape-triage
description: >-
  Diagnose overlay, commentary, and session bugs from overlay JSONL tapes and
  filtered logs. Use when the user mentions VOD, recordings/overlay-*.jsonl,
  session tape, commentary rejected, overlayMode, chapters, BLE/OBS log spam,
  or “look at last session / stream”.
---

# Overlay tape triage

Start at the tape. `logs/irswitch.log` is BLE/OBS-noisy; do not grep it first.

## 1. Pick the file

`recordings/overlay-<utc>-<subsession>-<sessionNum>.jsonl`

Newest matching the stream wall-clock. Header is line 1 (`type: header`).

## 2. Header (must read)

| Field | Meaning |
| --- | --- |
| `overlayMode` | PRACTICE / QUALIFYING / RACE / GENERIC — session **row**, not DrivingMode |
| `sessionId` | `subsession:session_num:track` |
| `drivingMode` | OBS scene side (RACE = on-track) |
| `obsScene` | scene name at tape open |
| `origins.stream` / `sessionTime` | do not mix with `t_session` |

If header `overlayMode` is `RACE` during Quali → skill `iracing-session-glossary` (EventType bug), not a widget bug.

## 3. Tape row types

| `type` | Use |
| --- | --- |
| `header` | identity |
| `green` | first `SessionState==4` |
| `scene` | OBS scene / drivingMode change |
| `decision` | event engine emit/suppress/preempt |
| `stories` | active V4 stories |
| `commentary` | director speak/reject — **only at runtime DEBUG** |
| `llm_polish` | optional polish — **only at runtime DEBUG** |
| `stream_origin` | OBS stream clock attached |

Clocks on each row: `t_stream` (VOD), `t_session` (`SessionTime`), `t_green`, `t_mono` (replay sleep), `t` (best). Align VOD to `t_stream`, not `t_session`.

## 4. Then the log (filtered)

```text
Session info updated
stream_chapter
commentary
overlayMode
Session info during loading
```

Skip BLE reconnect, OBS poll, SSL. If commentary rows are missing on tape, runtime log level was not DEBUG — that is expected, not “commentary is dead”.

## 5. Report shape

- tape file + `overlayMode` + `sessionId`
- what the HUD decided (`decision` / stories)
- what was spoken or rejected (if DEBUG tape)
- likely layer: extract / overlay copy / commentary graph / OBS cache

Do not “fix display-v4” because VOD showed a raw token until i18n + CEF are checked (skill `overlay-hud-copy`).
---
