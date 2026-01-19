"""Logging helpers for structured logging."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Literal, Optional

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def setup_logging(
    level: str | LogLevel = "INFO",
    log_file: Optional[str | Path] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5
) -> None:
    """
    Configure Python logging with structured format.
    
    Always logs to stderr (console). Optionally logs to file with rotation.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file (if None, logs only to stderr)
        max_bytes: Maximum log file size before rotation (default: 10 MB)
        backup_count: Number of backup log files to keep (default: 5)
    
    Format: timestamp | level | component | message
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()  # Remove existing handlers
    
    # Always log to stderr (console)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    root_logger.addHandler(stderr_handler)
    
    # Optionally log to file with rotation
    if log_file:
        log_path = Path(log_file)
        # Create log directory if it doesn't exist
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
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
