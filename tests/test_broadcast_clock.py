"""One broadcast timeline for metrics and chapter consumers."""

from unittest.mock import patch

import pytest

from irswitch.logic.stream_chapters import StreamChaptersSettings, StreamChapterTracker
from irswitch.server.metrics import MetricsCollector


def test_obs_clock_survives_short_output_restart() -> None:
    metrics = MetricsCollector()
    tracker = StreamChapterTracker(StreamChaptersSettings(enabled=True))

    def sample(now: float, streaming: bool, duration: float | None, session: str):
        with patch("time.monotonic", return_value=now):
            metrics.set_streaming(streaming, output_duration_seconds=duration)
            snapshot = metrics.get_broadcast_clock()
            tracker.update(
                streaming=streaming,
                duration_current_seconds=snapshot.offset_seconds,
                session_type=session,
                clock_snapshot=snapshot,
            )
            return metrics.get_stream_duration_seconds()

    assert sample(100, True, 600, "Practice") == (600, 600)
    assert sample(110, True, 610, "Qualify") == (610, 610)
    sample(111, False, None, "Qualify")
    assert sample(112, True, 0.5, "Race") == (610.5, 610.5)
    assert sample(122, True, 10.5, "Race") == (620.5, 620.5)
    assert [c.offset_seconds for c in tracker.chapters()] == [0, 610, 620]


def test_confirmed_new_broadcast_resets_clock_and_history_together() -> None:
    metrics = MetricsCollector()
    tracker = StreamChapterTracker(StreamChaptersSettings(enabled=True))
    for now, streaming, duration, broadcast_id, session in [
        (100, True, 600, "first", "Practice"),
        (110, True, 610, "first", "Qualify"),
        (111, False, None, "first", "Qualify"),
        (113, False, None, "first", "Qualify"),
        (120, True, 2, "second", "Race"),
    ]:
        with patch("time.monotonic", return_value=now):
            metrics.set_streaming(
                streaming, output_duration_seconds=duration, broadcast_id=broadcast_id
            )
            snapshot = metrics.get_broadcast_clock()
            tracker.update(
                streaming=streaming,
                duration_current_seconds=snapshot.offset_seconds,
                session_type=session,
                clock_snapshot=snapshot,
            )
    assert snapshot.epoch == 2
    assert snapshot.offset_seconds == 2
    assert [(c.title, c.offset_seconds) for c in tracker.chapters()] == [("Stream start", 0)]


def test_same_broadcast_id_keeps_timeline_after_long_interruption() -> None:
    metrics = MetricsCollector()
    with patch("time.monotonic", return_value=100):
        metrics.set_streaming(True, output_duration_seconds=500, broadcast_id="same")
    with patch("time.monotonic", return_value=101):
        metrics.set_streaming(False, broadcast_id="same")
    with patch("time.monotonic", return_value=110):
        metrics.set_streaming(False, broadcast_id="same")
    with patch("time.monotonic", return_value=120):
        metrics.set_streaming(True, output_duration_seconds=1, broadcast_id="same")
        assert metrics.get_broadcast_clock().epoch == 1
        assert metrics.get_stream_duration_seconds() == (501, 501)


@pytest.mark.parametrize("duration", [None, -1, float("nan"), float("inf")])
def test_unusable_obs_duration_falls_back_to_monotonic_time(duration) -> None:
    metrics = MetricsCollector()
    with patch("time.monotonic", return_value=100):
        metrics.set_streaming(True, output_duration_seconds=duration)
    with patch("time.monotonic", return_value=112):
        metrics.set_streaming(True, output_duration_seconds=duration)
        assert metrics.get_stream_duration_seconds() == (12, 12)


def test_unknown_connection_state_is_not_a_confirmed_stop() -> None:
    metrics = MetricsCollector()
    with patch("time.monotonic", return_value=100):
        metrics.set_streaming(True, output_duration_seconds=500)
    with patch("time.monotonic", return_value=101):
        metrics.set_streaming(None)
    with patch("time.monotonic", return_value=120):
        metrics.set_streaming(True, output_duration_seconds=520)
        assert metrics.get_broadcast_clock().epoch == 1
        assert metrics.get_stream_duration_seconds() == (520, 520)


def test_obs_duration_regression_does_not_rewind_clock() -> None:
    metrics = MetricsCollector()
    with patch("time.monotonic", return_value=100):
        metrics.set_streaming(True, output_duration_seconds=500)
    with patch("time.monotonic", return_value=101):
        metrics.set_streaming(True, output_duration_seconds=499)
        assert metrics.get_stream_duration_seconds() == (500, 500)
    with patch("time.monotonic", return_value=102):
        metrics.set_streaming(True, output_duration_seconds=502)
        assert metrics.get_stream_duration_seconds() == (502, 502)


def test_missing_counter_continues_from_last_authoritative_sample() -> None:
    metrics = MetricsCollector()
    with patch("time.monotonic", return_value=0):
        metrics.set_streaming(True, output_duration_seconds=500)
    with patch("time.monotonic", return_value=12):
        metrics.set_streaming(True, output_duration_seconds=None)
        assert metrics.get_stream_duration_seconds() == (512, 512)


def test_small_counter_regression_after_flicker_is_not_an_output_reset() -> None:
    metrics = MetricsCollector()
    with patch("time.monotonic", return_value=100):
        metrics.set_streaming(True, output_duration_seconds=500)
    with patch("time.monotonic", return_value=101):
        metrics.set_streaming(False)
    with patch("time.monotonic", return_value=102):
        metrics.set_streaming(True, output_duration_seconds=499)
        assert metrics.get_stream_duration_seconds() == (500, 500)
