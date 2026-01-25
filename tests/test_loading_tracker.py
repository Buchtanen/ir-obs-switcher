"""Tests for loading time tracker."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from irswitch.util.loading_tracker import LoadingTimeTracker


@pytest.fixture
def temp_history_file() -> Path:
    """Create temporary history file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("[]")
        return Path(f.name)


@pytest.fixture
def tracker_with_history(temp_history_file: Path) -> LoadingTimeTracker:
    """Create tracker with existing history."""
    history_data = [10.5, 12.3, 11.8, 13.2, 10.9]
    with open(temp_history_file, "w") as f:
        json.dump(history_data, f)

    return LoadingTimeTracker(history_file=temp_history_file, default_loading_time_seconds=12.0)


def test_load_empty_history(temp_history_file: Path) -> None:
    """Test loading tracker with empty history."""
    tracker = LoadingTimeTracker(history_file=temp_history_file, default_loading_time_seconds=12.0)

    assert len(tracker.history) == 0
    assert tracker.get_average_loading_time() == 12.0


def test_load_existing_history(tracker_with_history: LoadingTimeTracker) -> None:
    """Test loading tracker with existing history."""
    assert len(tracker_with_history.history) == 5
    avg = tracker_with_history.get_average_loading_time()
    expected_avg = (10.5 + 12.3 + 11.8 + 13.2 + 10.9) / 5
    assert abs(avg - expected_avg) < 0.01


def test_start_loading(temp_history_file: Path) -> None:
    """Test starting loading tracking."""
    tracker = LoadingTimeTracker(history_file=temp_history_file, default_loading_time_seconds=12.0)

    assert not tracker.is_loading()
    tracker.start_loading()
    assert tracker.is_loading()


def test_end_loading_without_start(temp_history_file: Path) -> None:
    """Test ending loading without starting."""
    tracker = LoadingTimeTracker(history_file=temp_history_file, default_loading_time_seconds=12.0)

    result = tracker.end_loading()
    assert result is None
    assert len(tracker.history) == 0


def test_start_end_loading(temp_history_file: Path) -> None:
    """Test complete loading cycle."""
    tracker = LoadingTimeTracker(history_file=temp_history_file, default_loading_time_seconds=12.0)

    with patch("irswitch.util.loading_tracker.now_ms", side_effect=[1000, 11500]):  # 10.5 seconds
        tracker.start_loading()
        assert tracker.is_loading()

        duration = tracker.end_loading()
        assert duration == 10.5
        assert not tracker.is_loading()
        assert len(tracker.history) == 1
        assert tracker.history[0] == 10.5


def test_history_limit(temp_history_file: Path) -> None:
    """Test that history is limited to MAX_HISTORY_SIZE."""
    tracker = LoadingTimeTracker(history_file=temp_history_file, default_loading_time_seconds=12.0)

    # Add more than MAX_HISTORY_SIZE (50) entries
    for i in range(60):
        with patch(
            "irswitch.util.loading_tracker.now_ms",
            side_effect=[i * 1000, (i + 1) * 1000],
        ):
            tracker.start_loading()
            tracker.end_loading()

    # Should only keep last 50
    assert len(tracker.history) == 50


def test_get_average_with_history(tracker_with_history: LoadingTimeTracker) -> None:
    """Test getting average with existing history."""
    avg = tracker_with_history.get_average_loading_time()
    assert avg != 12.0  # Should use actual history, not default
    assert 10.0 < avg < 14.0  # Reasonable range


def test_get_average_without_history(temp_history_file: Path) -> None:
    """Test getting average without history (uses default)."""
    tracker = LoadingTimeTracker(history_file=temp_history_file, default_loading_time_seconds=15.0)

    avg = tracker.get_average_loading_time()
    assert avg == 15.0


def test_save_history(temp_history_file: Path) -> None:
    """Test that history is saved to file."""
    tracker = LoadingTimeTracker(history_file=temp_history_file, default_loading_time_seconds=12.0)

    with patch("irswitch.util.loading_tracker.now_ms", side_effect=[1000, 2000]):
        tracker.start_loading()
        tracker.end_loading()

    # Check file was saved
    assert temp_history_file.exists()
    with open(temp_history_file) as f:
        saved_data = json.load(f)
        assert len(saved_data) == 1
        assert saved_data[0] == 1.0


def test_duplicate_start_loading(temp_history_file: Path) -> None:
    """Test that duplicate start_loading calls are ignored."""
    tracker = LoadingTimeTracker(history_file=temp_history_file, default_loading_time_seconds=12.0)

    with patch("irswitch.util.loading_tracker.now_ms", side_effect=[1000, 2000]):
        tracker.start_loading()
        assert tracker.is_loading()

        # Duplicate call should be ignored
        tracker.start_loading()
        assert tracker.is_loading()

        # Should only end once (uses second timestamp from side_effect)
        duration = tracker.end_loading()
        assert duration == 1.0
        assert not tracker.is_loading()
