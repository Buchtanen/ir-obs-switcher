"""Logging helpers for structured logging."""
from __future__ import annotations

import logging
import sys
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def setup_logging(level: str | LogLevel = "INFO") -> None:
    """
    Configure Python logging with structured format.

    Format: timestamp | level | component | message
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)

    # Prevent duplicate logs
    root_logger.propagate = False


def log_state_changed(logger: logging.Logger, old_state: str, new_state: str) -> None:
    """Log state change event."""
    logger.info(f"state_changed: {old_state} -> {new_state}")


def log_scene_switch(
    logger: logging.Logger, scene: str, reason: str, latency_ms: int | None = None
) -> None:
    """Log scene switch event."""
    msg = f"scene_switch: {scene} (reason: {reason})"
    if latency_ms is not None:
        msg += f" latency: {latency_ms}ms"
    logger.info(msg)


def log_override_applied(
    logger: logging.Logger, scene: str, until_ms: int
) -> None:
    """Log override application."""
    logger.info(f"override_applied: {scene} until {until_ms}")


def log_connection_lost(logger: logging.Logger, component: str) -> None:
    """Log connection loss."""
    logger.warning(f"connection_lost: {component}")


def log_connection_restored(logger: logging.Logger, component: str) -> None:
    """Log connection restoration."""
    logger.info(f"connection_restored: {component}")
