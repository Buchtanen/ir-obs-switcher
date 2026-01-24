"""Tests for metrics collection."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from irswitch.server.metrics import MetricsCollector, get_metrics, reset_metrics


@pytest.fixture
def metrics() -> MetricsCollector:
    """Create a fresh metrics collector for testing."""
    reset_metrics()
    return get_metrics()


def test_record_scene_switch(metrics: MetricsCollector) -> None:
    """Test recording scene switches."""
    assert metrics.scene_switches_total == 0

    metrics.record_scene_switch(50.0)
    assert metrics.scene_switches_total == 1
    assert len(metrics.scene_switch_latencies_ms) == 1
    assert metrics.scene_switch_latencies_ms[0] == 50.0

    metrics.record_scene_switch(75.0)
    assert metrics.scene_switches_total == 2
    assert len(metrics.scene_switch_latencies_ms) == 2


def test_scene_switch_latency_limit(metrics: MetricsCollector) -> None:
    """Test that scene switch latencies are limited to max samples."""
    # Record more than max samples
    for i in range(metrics._max_latency_samples + 10):
        metrics.record_scene_switch(float(i))

    assert len(metrics.scene_switch_latencies_ms) == metrics._max_latency_samples
    # Oldest samples should be removed (FIFO)
    assert metrics.scene_switch_latencies_ms[0] == 10.0  # First 10 were removed


def test_get_scene_switch_latency_avg_ms(metrics: MetricsCollector) -> None:
    """Test getting average scene switch latency."""
    # No data
    assert metrics.get_scene_switch_latency_avg_ms() is None

    # With data
    metrics.record_scene_switch(50.0)
    metrics.record_scene_switch(75.0)
    metrics.record_scene_switch(100.0)

    avg = metrics.get_scene_switch_latency_avg_ms()
    assert avg == 75.0  # (50 + 75 + 100) / 3


def test_record_error(metrics: MetricsCollector) -> None:
    """Test recording errors."""
    assert len(metrics.errors_total) == 0

    metrics.record_error("connection_error")
    assert metrics.errors_total["connection_error"] == 1

    metrics.record_error("connection_error")
    assert metrics.errors_total["connection_error"] == 2

    metrics.record_error("timeout_error")
    assert metrics.errors_total["timeout_error"] == 1
    assert metrics.errors_total["connection_error"] == 2


def test_get_uptime_seconds(metrics: MetricsCollector) -> None:
    """Test getting uptime."""
    uptime1 = metrics.get_uptime_seconds()
    assert uptime1 >= 0

    time.sleep(0.1)
    uptime2 = metrics.get_uptime_seconds()
    assert uptime2 > uptime1


def test_iracing_connection_duration(metrics: MetricsCollector) -> None:
    """Test iRacing connection duration tracking (cumulative + current session)."""
    # Never connected
    cumulative, current = metrics.get_iracing_connected_duration_seconds()
    assert cumulative is None
    assert current is None

    # Connect
    with patch("time.monotonic", return_value=100.0):
        metrics.set_iracing_connected(True)

    # Check during connection
    with patch("time.monotonic", return_value=150.0):
        cumulative, current = metrics.get_iracing_connected_duration_seconds()
        assert cumulative == 50.0  # 150 - 100
        assert current == 50.0

    # Disconnect
    with patch("time.monotonic", return_value=200.0):
        metrics.set_iracing_connected(False)

    # Check after disconnect
    with patch("time.monotonic", return_value=250.0):
        cumulative, current = metrics.get_iracing_connected_duration_seconds()
        assert cumulative == 100.0  # 200 - 100 (total from first session)
        assert current is None  # Not connected anymore

    # Reconnect
    with patch("time.monotonic", return_value=300.0):
        metrics.set_iracing_connected(True)

    # Check during second connection
    with patch("time.monotonic", return_value=350.0):
        cumulative, current = metrics.get_iracing_connected_duration_seconds()
        assert cumulative == 150.0  # 100 (first session) + 50 (current session)
        assert current == 50.0  # 350 - 300


def test_obs_connection_duration(metrics: MetricsCollector) -> None:
    """Test OBS connection duration tracking (cumulative + current session)."""
    # Same logic as iRacing
    with patch("time.monotonic", return_value=100.0):
        metrics.set_obs_connected(True)

    with patch("time.monotonic", return_value=150.0):
        cumulative, current = metrics.get_obs_connected_duration_seconds()
        assert cumulative == 50.0
        assert current == 50.0

    with patch("time.monotonic", return_value=200.0):
        metrics.set_obs_connected(False)

    with patch("time.monotonic", return_value=250.0):
        cumulative, current = metrics.get_obs_connected_duration_seconds()
        assert cumulative == 100.0
        assert current is None


def test_stream_duration(metrics: MetricsCollector) -> None:
    """Test stream duration tracking (cumulative + current session)."""
    # Never streamed
    cumulative, current = metrics.get_stream_duration_seconds()
    assert cumulative is None
    assert current is None

    # Start streaming
    with patch("time.monotonic", return_value=100.0):
        metrics.set_streaming(True)

    # Check during streaming
    with patch("time.monotonic", return_value=150.0):
        cumulative, current = metrics.get_stream_duration_seconds()
        assert cumulative == 50.0  # 150 - 100
        assert current == 50.0

    # Stop streaming
    with patch("time.monotonic", return_value=200.0):
        metrics.set_streaming(False)

    # Check after stop
    with patch("time.monotonic", return_value=250.0):
        cumulative, current = metrics.get_stream_duration_seconds()
        assert cumulative == 100.0  # 200 - 100 (total from first session)
        assert current is None  # Not streaming anymore

    # Start streaming again
    with patch("time.monotonic", return_value=300.0):
        metrics.set_streaming(True)

    # Check during second stream
    with patch("time.monotonic", return_value=350.0):
        cumulative, current = metrics.get_stream_duration_seconds()
        assert cumulative == 150.0  # 100 (first session) + 50 (current session)
        assert current == 50.0  # 350 - 300


def test_to_dict_basic(metrics: MetricsCollector) -> None:
    """Test to_dict() method with basic metrics."""
    metrics.record_scene_switch(50.0)
    metrics.record_error("test_error")

    result = metrics.to_dict()

    assert result["scene_switches_total"] == 1
    assert result["uptime_seconds"] >= 0  # Can be 0 if test runs very fast
    assert result["errors_total"]["test_error"] == 1
    assert result["scene_switch_latency_avg_ms"] == 50.0


def test_to_dict_with_current_state(metrics: MetricsCollector) -> None:
    """Test to_dict() method with current state."""
    from irswitch.models import DrivingMode, SwitchState

    state = SwitchState(
        connected_iracing=True,
        connected_obs=True,
        autoswitch=True,
        override_scene=None,
        override_until=None,
        mode=DrivingMode.IDLE,
        target_scene="Idle",
        current_scene="Idle",
        last_switch_ts=None,
        reason="test",
    )

    result = metrics.to_dict(state)

    assert "current_state" in result
    assert result["current_state"]["mode"] == "IDLE"
    assert result["current_state"]["scene"] == "Idle"
    assert result["current_state"]["autoswitch"] is True


def test_to_dict_connection_durations(metrics: MetricsCollector) -> None:
    """Test to_dict() includes connection durations."""
    with patch("time.monotonic", return_value=100.0):
        metrics.set_iracing_connected(True)
        metrics.set_obs_connected(True)
        metrics.set_streaming(True)

    with patch("time.monotonic", return_value=150.0):
        result = metrics.to_dict()

        assert "iracing_connected_duration_seconds" in result
        assert "iracing_connected_duration_current_session_seconds" in result
        assert "obs_connected_duration_seconds" in result
        assert "obs_connected_duration_current_session_seconds" in result
        assert "stream_duration_seconds" in result
        assert "stream_duration_current_session_seconds" in result

        assert result["iracing_connected_duration_seconds"] == 50.0
        assert result["iracing_connected_duration_current_session_seconds"] == 50.0


def test_to_dict_no_durations_when_disconnected(metrics: MetricsCollector) -> None:
    """Test to_dict() doesn't include durations when never connected."""
    result = metrics.to_dict()

    # Should not include duration fields if never connected
    assert "iracing_connected_duration_seconds" not in result
    assert "obs_connected_duration_seconds" not in result
    assert "stream_duration_seconds" not in result
