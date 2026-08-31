# Naming examples (copy the good column)

## Extract live session type

Bad — weekend product, Quali becomes Race:

```python
event = data["WeekendInfo"]["EventType"]  # "Race" all weekend
overlay_mode = "RACE" if event == "Race" else "PRACTICE"
```

Good:

```python
from irswitch.iracing.extractors import extract_session_type
from irswitch.overlay.session import overlay_mode_from_session_type

session_type = extract_session_type(data)  # "Qualify" when SessionNum=1
overlay_mode = overlay_mode_from_session_type(session_type)  # QUALIFYING
```

Fixture that must stay green:

```python
data = {
    "SessionNum": 1,
    "WeekendInfo": {"EventType": "Race"},
    "SessionInfo": {
        "Sessions": [
            {"SessionType": "Practice"},
            {"SessionType": "Lone Qualify"},
            {"SessionType": "Race"},
        ]
    },
}
assert extract_session_type(data) == "Qualify"
```

## Gate an emitter

Bad — fires in Practice because on-track:

```python
if state.mode == DrivingMode.RACE:
    emit_overtake()
```

Good:

```python
if state.overlay_mode == "RACE" and not state.session_finished:
    emit_overtake()
```

Sectors:

```python
if state.overlay_mode not in {"PRACTICE", "QUALIFYING"}:
    return []
```

## OBS scene vs session row

Bad:

```python
if session_type == "Race":
    switch_to(scenes[DrivingMode.RACE])
```

Good: scenes follow `DrivingMode` (on-track / garage / lobby). Session row
only feeds dashboard, chapters, overlay_mode.

## Stream chapter vs session clock

Bad — chapter at SessionTime (wrong on VOD):

```python
offset = int(snapshot.session_time)
```

Good: OBS stream duration (`duration_current_seconds` into `StreamChapterTracker.update`).

## New identifier

| Bad | Good |
| --- | --- |
| `mode` | `overlay_mode` or `driving_mode` |
| `is_race` | `overlay_mode == "RACE"` or `driving_mode == DrivingMode.RACE` (say which) |
| `session_id` | `session_key` or `subsession_id` (say which) |
| `qualifying` in snapshot | `session_type == "Qualify"` |
| `EventType` fallback | omit |

## Two readers, one parser

Bad — switcher path without YAML, overlay path with YAML:

```python
session_type = data.get("WeekendInfo", {}).get("EventType")
```

Good — both:

```python
extract_session_type(data)  # data must contain SessionInfo.Sessions
```

`read_session_info()` uses `SESSION_INFO_VARS`. Overlay `read_telemetry()` uses `TELEMETRY_VARS`. Both tuples include `SessionInfo`.

## Speech event names

Keep existing: `SESSION_INTRO_PRACTICE` / `SESSION_INTRO_QUALIFY` / `SESSION_INTRO_RACE`.
Those follow **session row**, not DrivingMode. If `overlay_mode` is wrong, intros lie.
