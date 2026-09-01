"""Unit tests for stream chapter tracker."""

from __future__ import annotations

import configparser

from irswitch.logic.stream_chapters import (
    STREAM_FLICKER_DEBOUNCE_S,
    StreamChaptersSettings,
    StreamChapterTracker,
    load_stream_chapters_settings,
)


def _enabled(**kwargs: object) -> StreamChaptersSettings:
    base = StreamChaptersSettings(enabled=True)
    return StreamChaptersSettings(
        enabled=True,
        start_title=str(kwargs.get("start_title", base.start_title)),
        end_title=str(kwargs.get("end_title", base.end_title)),
        trigger_session_types=tuple(
            kwargs.get("trigger_session_types", base.trigger_session_types)  # type: ignore[arg-type]
        ),
        session_titles=dict(kwargs.get("session_titles", {})),  # type: ignore[arg-type]
        youtube_vod=bool(kwargs.get("youtube_vod", base.youtube_vod)),
    )


def test_disabled_records_nothing() -> None:
    tracker = StreamChapterTracker(StreamChaptersSettings(enabled=False))
    created = tracker.update(streaming=True, duration_current_seconds=10.0, session_type="Race")
    assert created == []
    assert tracker.chapters() == []


def test_start_marker_at_offset_zero() -> None:
    mono = {"t": 100.0}
    wall = {"ms": 1_000}

    tracker = StreamChapterTracker(
        _enabled(start_title="Go live"),
        time_mono=lambda: mono["t"],
        time_wall_ms=lambda: wall["ms"],
    )
    created = tracker.update(streaming=True, duration_current_seconds=None, session_type="Practice")
    assert len(created) == 1
    assert created[0].title == "Go live"
    assert created[0].offset_seconds == 0
    assert created[0].session_type is None
    # Current Practice must not also emit a session chapter on start
    assert len(tracker.chapters()) == 1


def test_session_type_change_uses_duration_floor() -> None:
    tracker = StreamChapterTracker(
        _enabled(session_titles={"qualify": "Qualifying"}),
        time_wall_ms=lambda: 5_000,
    )
    tracker.update(streaming=True, duration_current_seconds=0.0, session_type="Practice")
    tracker.take_pending()

    created = tracker.update(streaming=True, duration_current_seconds=42.9, session_type="Qualify")
    assert len(created) == 1
    assert created[0].title == "Qualifying"
    assert created[0].offset_seconds == 42
    assert created[0].session_type == "Qualify"


def test_test_and_null_session_ignored() -> None:
    tracker = StreamChapterTracker(_enabled())
    tracker.update(streaming=True, duration_current_seconds=0.0, session_type=None)
    tracker.take_pending()
    assert tracker.update(streaming=True, duration_current_seconds=5.0, session_type="Test") == []
    assert tracker.update(streaming=True, duration_current_seconds=6.0, session_type=None) == []


def test_no_duplicate_on_same_session_type() -> None:
    tracker = StreamChapterTracker(_enabled())
    tracker.update(streaming=True, duration_current_seconds=0.0, session_type="Race")
    tracker.take_pending()
    assert tracker.update(streaming=True, duration_current_seconds=10.0, session_type="Race") == []


def test_stream_stop_keeps_chapters_and_arms_vod_flush() -> None:
    mono = {"t": 0.0}
    tracker = StreamChapterTracker(_enabled(), time_mono=lambda: mono["t"])
    tracker.update(streaming=True, duration_current_seconds=0.0, session_type="Practice")
    tracker.update(streaming=True, duration_current_seconds=42.0, session_type="Race")
    tracker.update(streaming=True, duration_current_seconds=80.0, session_type="Race")
    assert len(tracker.chapters()) == 2
    assert tracker.consume_vod_flush() is False

    mono["t"] = 1.0
    tracker.update(streaming=False, duration_current_seconds=None, session_type="Race")
    assert len(tracker.chapters()) == 2
    assert tracker.consume_vod_flush() is False

    mono["t"] = 1.0 + STREAM_FLICKER_DEBOUNCE_S
    created = tracker.update(streaming=False, duration_current_seconds=None, session_type="Race")
    titles = [c.title for c in tracker.chapters()]
    assert titles[0] == "Stream start"
    assert "Race" in titles
    assert "Stream end" in titles
    assert created[-1].title == "Stream end"
    assert created[-1].offset_seconds == 80
    assert tracker.consume_vod_flush() is True
    assert tracker.consume_vod_flush() is False


def test_prepare_vod_flush_while_obs_still_streaming() -> None:
    tracker = StreamChapterTracker(_enabled())
    tracker.update(streaming=True, duration_current_seconds=90.0, session_type="Race")
    tracker.prepare_vod_flush()
    assert tracker.chapters()[-1].title == "Stream end"
    assert tracker.consume_vod_flush() is True


def test_empty_end_title_skips_end_marker() -> None:
    tracker = StreamChapterTracker(_enabled(end_title=""))
    tracker.update(streaming=True, duration_current_seconds=30.0, session_type="Race")
    tracker.prepare_vod_flush()
    assert [c.title for c in tracker.chapters()] == ["Stream start"]
    assert tracker.consume_vod_flush() is True


def test_stream_flicker_keeps_chapters_no_new_start() -> None:
    mono = {"t": 0.0}
    tracker = StreamChapterTracker(_enabled(), time_mono=lambda: mono["t"])
    tracker.update(streaming=True, duration_current_seconds=0.0, session_type="Practice")
    tracker.update(streaming=True, duration_current_seconds=20.0, session_type="Race")
    assert len(tracker.chapters()) == 2

    mono["t"] = 10.0
    tracker.update(streaming=False, duration_current_seconds=None, session_type="Race")
    mono["t"] = 11.0  # < 2s
    created = tracker.update(streaming=True, duration_current_seconds=21.0, session_type="Race")
    assert created == []
    assert len(tracker.chapters()) == 2
    assert tracker.chapters()[0].title == "Stream start"


def test_load_stream_chapters_settings_from_ini() -> None:
    parser = configparser.ConfigParser()
    parser.read_string("""
[stream_chapters]
enabled = true
start_title = Live
trigger_session_types = Practice, Race
title_qualify = Quali block
practice = Free Practice
""")
    settings = load_stream_chapters_settings(parser)
    assert settings.enabled is True
    assert settings.start_title == "Live"
    assert settings.end_title == "Stream end"
    assert settings.trigger_session_types == ("Practice", "Race")
    assert settings.session_titles["qualify"] == "Quali block"
    assert settings.session_titles["practice"] == "Free Practice"
    assert settings.youtube_vod is False


def test_load_stream_chapters_youtube_vod() -> None:
    parser = configparser.ConfigParser()
    parser.read_string("""
[stream_chapters]
enabled = true
youtube_vod = true
""")
    settings = load_stream_chapters_settings(parser)
    assert settings.youtube_vod is True
