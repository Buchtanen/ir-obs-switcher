"""N10 watcher decision ring: bounded debug log, no public API."""

from __future__ import annotations

import logging

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import parse_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import make_envelope
from irswitch.iracing.session_flags import FLAG_BITS, decode_session_flags
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import CommentarySettings
from irswitch.race.flags import SessionFlagFsm
from irswitch.race.grid_story import IRSDK_PARADE_LAPS, IRSDK_RACING, GridStoryFsm
from irswitch.race.observer import RaceObserver
from irswitch.race.story import QualiBag
from irswitch.race.watcher_log import WATCHER_LOG_SIZE, WatcherLog


def _flag_state(
    *, names: tuple[str, ...] = (), mode: str = "RACE", **overrides: object
) -> RaceState:
    raw = 0
    for name in names:
        raw |= FLAG_BITS[name]
    decoded = decode_session_flags(raw)
    payload: dict[str, object] = {
        "connected": True,
        "overlay_mode": mode,
        "session_flags": raw,
        "session_flag_names": decoded.names,
        "flag_checkered": decoded.checkered,
        "flag_yellow": decoded.yellow,
        "flag_green": decoded.green,
        "player_finished": False,
        "session_checkered": False,
        "subsession_id": "sub",
        "session_num": 1,
    }
    payload.update(overrides)
    return RaceState(**payload)  # type: ignore[arg-type]


def _grid_state(
    *,
    mode: str = "RACE",
    session_state: int | None = IRSDK_PARADE_LAPS,
    **overrides: object,
) -> RaceState:
    payload: dict[str, object] = {
        "connected": True,
        "overlay_mode": mode,
        "session_state": session_state,
        "player_finished": False,
        "session_checkered": False,
        "mute_field": False,
        "subsession_id": "sub",
        "session_num": 2,
    }
    payload.update(overrides)
    return RaceState(**payload)  # type: ignore[arg-type]


def _bag(*, position: int = 4, best: float | None = 91.234) -> QualiBag:
    return QualiBag(class_position=position, best_lap_s=best)


def _tiny_graph(*, include_recap: bool) -> object:
    nodes: dict[str, object] = {
        "overtake": {
            "family": "position",
            "event_types": ["OVERTAKE"],
            "phases": ["RESULT"],
            "speak_priority": 85,
            "cooldown_s": 0,
            "slots": [],
            "hr_states": ["unknown"],
            "variants": {"en": {"neutral": ["He takes the place."]}},
        }
    }
    if include_recap:
        nodes["quali_recap"] = {
            "family": "session",
            "event_types": ["QUALI_RECAP"],
            "phases": ["RESULT"],
            "speak_priority": 66,
            "cooldown_s": 0,
            "slots": [],
            "hr_states": ["unknown"],
            "variants": {"en": {"neutral": ["He starts P4."]}},
        }
    return parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en", "cs"],
            "nodes": nodes,
            "edges": [],
        }
    )


def test_ring_caps_at_64() -> None:
    log = WatcherLog()
    for i in range(WATCHER_LOG_SIZE + 20):
        log.record(watch="flags", kind="SESSION_FLAG", emitted=False, reason=str(i), now=float(i))
    assert len(log) == WATCHER_LOG_SIZE
    latest = log.latest()
    assert latest[0].reason == "20"
    assert latest[-1].reason == str(WATCHER_LOG_SIZE + 19)


def test_flags_disabled_rising_logs_not_emitted() -> None:
    log = WatcherLog()
    fsm = SessionFlagFsm()
    fsm.tick(_flag_state(), 1.0, enabled=False, log=log)
    assert fsm.tick(_flag_state(names=("yellow",)), 1.2, enabled=False, log=log) == []
    entries = log.latest()
    assert len(entries) == 1
    assert entries[0].watch == "flags"
    assert entries[0].kind == "SESSION_FLAG"
    assert entries[0].emitted is False
    assert entries[0].reason == "disabled"


def test_flags_hold_does_not_flood() -> None:
    log = WatcherLog()
    fsm = SessionFlagFsm()
    fsm.tick(_flag_state(), 1.0, enabled=True, log=log)
    assert fsm.tick(_flag_state(names=("yellow",)), 1.2, enabled=True, log=log)
    for i in range(25):
        fsm.tick(_flag_state(names=("yellow",)), 1.4 + i * 0.2, enabled=True, log=log)
    assert len(log) == 1
    assert log.latest()[0].reason == "rising"
    assert log.latest()[0].emitted is True


def test_flags_cooldown_logs_once_per_rising() -> None:
    log = WatcherLog()
    fsm = SessionFlagFsm()
    fsm.tick(_flag_state(), 1.0, enabled=True, log=log)
    assert fsm.tick(_flag_state(names=("green",)), 1.2, enabled=True, log=log)
    fsm.tick(_flag_state(), 1.4, enabled=True, log=log)
    assert fsm.tick(_flag_state(names=("green",)), 5.0, enabled=True, log=log) == []
    reasons = [item.reason for item in log.latest()]
    assert reasons == ["rising", "cooldown"]


def test_flags_outside_race_is_debug_not_info(caplog) -> None:
    log = WatcherLog()
    fsm = SessionFlagFsm()
    with caplog.at_level(logging.INFO, logger="irswitch.race.flags"):
        fsm.tick(_flag_state(mode="PRACTICE"), 1.0, enabled=True, log=log)
        fsm.tick(_flag_state(names=("yellow",), mode="PRACTICE"), 1.2, enabled=True, log=log)
    assert not caplog.records
    assert log.latest()[0].reason == "not_race"
    assert log.latest()[0].emitted is False


def test_grid_story_racing_does_not_flood_ring() -> None:
    log = WatcherLog()
    fsm = GridStoryFsm()
    racing = _grid_state(session_state=IRSDK_RACING)
    for i in range(40):
        fsm.tick(
            racing,
            1.0 + i * 0.2,
            enabled=True,
            bag=_bag(),
            session_key="race",
            log=log,
        )
    assert len(log) == 1
    entry = log.latest()[0]
    assert entry.watch == "grid_story"
    assert entry.emitted is False
    assert entry.reason == "green_or_racing"


def test_grid_story_missing_bag_logs_once() -> None:
    log = WatcherLog()
    fsm = GridStoryFsm()
    fsm.tick(_grid_state(), 1.0, enabled=True, bag=None, session_key="race", log=log)
    fsm.tick(_grid_state(), 1.2, enabled=True, bag=None, session_key="race", log=log)
    recaps = [item for item in log.latest() if item.kind == "QUALI_RECAP"]
    assert len(recaps) == 1
    assert recaps[0].reason == "missing_bag"
    assert recaps[0].emitted is False


def test_director_off_track_logs_generic_suppressed() -> None:
    log = WatcherLog()
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    director.watcher_log = log
    env = make_envelope(
        event_type="INCIDENT",
        phase="RESULT",
        mode="RACE",
        priority=90,
        metrics={"value": 2, "branch": "off_track"},
    )
    spoken = director.observe([env], None, 1.0)
    assert spoken is not None
    assert spoken.node_id == "incident_off_track"
    entries = [item for item in log.latest() if item.kind == "INCIDENT"]
    assert len(entries) == 1
    assert entries[0].watch == "incidents"
    assert entries[0].emitted is True
    assert entries[0].reason == "generic_suppressed"
    assert entries[0].confidence == 1.0


def test_director_unclassified_incident_is_graph_hit() -> None:
    log = WatcherLog()
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    director.watcher_log = log
    env = make_envelope(
        event_type="INCIDENT",
        phase="RESULT",
        mode="RACE",
        priority=90,
        metrics={"value": 2},
    )
    spoken = director.observe([env], None, 1.0)
    assert spoken is not None
    assert spoken.node_id == "incident"
    assert log.latest()[-1].reason == "graph_hit"


def test_director_recap_graph_hit_vs_formatter_fallback() -> None:
    hit_log = WatcherLog()
    director = CommentaryDirector(
        graph=_tiny_graph(include_recap=True),  # type: ignore[arg-type]
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
        watcher_log=hit_log,
    )
    recap = make_envelope(
        event_type="QUALI_RECAP",
        phase="RESULT",
        mode="RACE",
        priority=66,
        metrics={"kind": "quali_recap", "position": 4},
    )
    spoken = director.observe([recap], None, 1.0)
    assert spoken is not None
    assert spoken.node_id == "quali_recap"
    assert hit_log.latest()[-1].reason == "graph_hit"
    assert hit_log.latest()[-1].confidence == 1.0

    fall_log = WatcherLog()
    fallback = CommentaryDirector(
        graph=_tiny_graph(include_recap=False),  # type: ignore[arg-type]
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
        watcher_log=fall_log,
    )
    fallback.filler_formatter = lambda _env: "He starts fourth from the quali bag."
    spoken_fmt = fallback.observe([recap], None, 1.0)
    assert spoken_fmt is not None
    assert spoken_fmt.node_id.startswith("fmt:")
    entry = fall_log.latest()[-1]
    assert entry.reason == "formatter_fallback"
    assert entry.emitted is True
    assert entry.confidence == 0.6


def test_overtake_does_not_write_watcher_ring() -> None:
    log = WatcherLog()
    director = CommentaryDirector(
        graph=_tiny_graph(include_recap=False),  # type: ignore[arg-type]
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
        watcher_log=log,
    )
    env = make_envelope(event_type="OVERTAKE", phase="RESULT", mode="RACE", priority=85)
    spoken = director.observe([env], None, 1.0)
    assert spoken is not None
    assert len(log) == 0


def test_reset_session_keeps_ring_stream_clears() -> None:
    observer = RaceObserver()
    observer.watches.record(
        watch="flags", kind="SESSION_FLAG", emitted=True, reason="rising", now=1.0
    )
    observer.reset_session()
    assert len(observer.watches) == 1
    observer.reset_stream()
    assert len(observer.watches) == 0


def test_status_snapshot_has_no_watcher_api() -> None:
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True),
        sink=NullTtsSink(),
    )
    snap = director.status_snapshot(1.0)
    assert "watches" not in snap
    assert "watcher" not in snap
