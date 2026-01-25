"""Loading screen time tracker."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from irswitch.util.clock import now_ms

logger = logging.getLogger(__name__)

# Default history file location (in data/ directory)
DEFAULT_HISTORY_FILE = Path("data/loading_history.json")
MAX_HISTORY_SIZE = 50


class LoadingTimeTracker:
    """Tracks loading screen durations and calculates averages."""

    def __init__(
        self,
        history_file: Path | str = DEFAULT_HISTORY_FILE,
        default_loading_time_seconds: float = 12.0,
    ) -> None:
        """
        Initialize loading time tracker.

        Args:
            history_file: Path to JSON file for storing loading history
            default_loading_time_seconds: Default loading time to use when no history exists
        """
        # Resolve to absolute path and log it
        self.history_file = Path(history_file).resolve()  # Resolve to absolute path
        logger.info(f"LoadingTimeTracker initialized, history file: {self.history_file}")
        self.default_loading_time_seconds = default_loading_time_seconds
        self.history: list[float] = []
        self._loading_start_ts: int | None = None  # Changed to int to match now_ms() return type
        self._load_history()

    def _load_history(self) -> None:
        """Load loading history from JSON file."""
        if not self.history_file.exists():
            logger.info(
                f"Loading history file not found: {self.history_file}, starting with empty history"
            )
            return

        try:
            with open(self.history_file, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    # Ensure all values are floats and limit to MAX_HISTORY_SIZE
                    self.history = [float(x) for x in data[-MAX_HISTORY_SIZE:]]
                    logger.info(
                        f"Loaded {len(self.history)} loading time records from {self.history_file}"
                    )
                else:
                    logger.warning(
                        f"Invalid history file format: {self.history_file}, starting with empty history"
                    )
                    self.history = []
        except Exception as e:
            logger.error(
                f"Failed to load loading history from {self.history_file}: {e}, starting with empty history",
                exc_info=True,
            )
            self.history = []

    def _save_history(self) -> None:
        """Save loading history to JSON file."""
        try:
            # Ensure directory exists
            self.history_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)
            logger.info(f"Saved {len(self.history)} loading time records to {self.history_file}")
        except Exception as e:
            logger.error(
                f"Failed to save loading history to {self.history_file}: {e}",
                exc_info=True,
            )

    def start_loading(self) -> None:
        """Mark the start of a loading screen."""
        if self._loading_start_ts is not None:
            # Already tracking a loading, ignore duplicate start
            logger.debug("Loading already started, ignoring duplicate start_loading() call")
            return

        self._loading_start_ts = now_ms()
        logger.debug("Loading screen started")

    def end_loading(self) -> float | None:
        """
        Mark the end of a loading screen and save the duration.

        Returns:
            Duration in seconds, or None if no loading was started
        """
        if self._loading_start_ts is None:
            logger.debug("end_loading() called but no loading was started")
            return None

        duration_ms = now_ms() - self._loading_start_ts
        duration_seconds = duration_ms / 1000.0
        self._loading_start_ts = None

        # Add to history (FIFO - keep only last MAX_HISTORY_SIZE)
        self.history.append(duration_seconds)
        if len(self.history) > MAX_HISTORY_SIZE:
            self.history = self.history[-MAX_HISTORY_SIZE:]

        # Save history
        logger.debug(
            f"About to save history: {len(self.history)} records, file: {self.history_file}"
        )
        self._save_history()
        logger.debug(f"History save completed, file exists: {self.history_file.exists()}")

        logger.info(f"Loading screen ended, duration: {duration_seconds:.2f}s")
        return duration_seconds

    def get_average_loading_time(self) -> float:
        """
        Get average loading time from history.

        Returns:
            Average loading time in seconds, or default_loading_time_seconds if no history
        """
        if not self.history:
            logger.debug(
                f"No loading history available, using default: {self.default_loading_time_seconds}s"
            )
            return self.default_loading_time_seconds

        average = sum(self.history) / len(self.history)
        logger.debug(f"Average loading time: {average:.2f}s (from {len(self.history)} records)")
        return average

    def is_loading(self) -> bool:
        """Check if currently tracking a loading screen."""
        return self._loading_start_ts is not None
