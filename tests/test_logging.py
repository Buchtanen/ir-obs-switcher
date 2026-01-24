"""Tests for logging setup with file rotation."""

from __future__ import annotations

import logging
import logging.handlers
import tempfile
from pathlib import Path

import pytest

from irswitch.util.logging import setup_logging


def test_setup_logging_console_only() -> None:
    """Test that logging works to console (stderr) when log_file is None."""
    import sys

    # Clear existing handlers
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers.clear()

    try:
        setup_logging(level="INFO", log_file=None)

        # Should have stderr handler
        handlers = root_logger.handlers
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.StreamHandler)
        assert handlers[0].stream == sys.stderr

        # Test that it logs
        logger = logging.getLogger("test")
        logger.info("Test message")
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)


def test_setup_logging_with_file(tmp_path: Path) -> None:
    """Test that logging works to both console and file."""
    import sys

    log_file = tmp_path / "test.log"

    # Clear existing handlers
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers.clear()

    try:
        setup_logging(level="INFO", log_file=str(log_file))

        # Should have both stderr and file handlers
        handlers = root_logger.handlers
        assert len(handlers) == 2

        # Check handlers
        handler_types = [type(h).__name__ for h in handlers]
        assert "StreamHandler" in handler_types
        assert "RotatingFileHandler" in handler_types

        # Test that it logs to file
        logger = logging.getLogger("test")
        logger.info("Test message to file")

        # Force flush
        for handler in handlers:
            handler.flush()

        # Check file was created and contains message
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "Test message to file" in content
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)


def test_setup_logging_creates_directory(tmp_path: Path) -> None:
    """Test that logging creates log directory if it doesn't exist."""
    import sys

    log_dir = tmp_path / "logs"
    log_file = log_dir / "test.log"

    # Directory should not exist
    assert not log_dir.exists()

    # Clear existing handlers
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers.clear()

    try:
        setup_logging(level="INFO", log_file=str(log_file))

        # Directory should be created
        assert log_dir.exists()
        assert log_dir.is_dir()

        # File should be created after logging
        logger = logging.getLogger("test")
        logger.info("Test message")

        # Force flush
        for handler in root_logger.handlers:
            handler.flush()

        assert log_file.exists()
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)


def test_setup_logging_rotation(tmp_path: Path) -> None:
    """Test that log rotation works when max_bytes is reached."""
    import sys

    log_file = tmp_path / "test.log"
    max_bytes = 1024  # 1 KB
    backup_count = 3

    # Clear existing handlers
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers.clear()

    try:
        setup_logging(
            level="INFO",
            log_file=str(log_file),
            max_bytes=max_bytes,
            backup_count=backup_count,
        )

        logger = logging.getLogger("test")

        # Write enough data to trigger rotation
        large_message = "X" * 200  # 200 bytes per message
        for i in range(10):  # 10 messages = ~2KB, should trigger rotation
            logger.info(f"{large_message} {i}")
            # Force flush after each message
            for handler in root_logger.handlers:
                handler.flush()

        # Check that rotation occurred
        # Should have main log file and backup files
        log_files = list(tmp_path.glob("test.log*"))
        assert len(log_files) > 1  # At least main file + one backup

        # Check backup files
        backup_files = [f for f in log_files if f.name != "test.log"]
        assert len(backup_files) <= backup_count  # Should not exceed backup_count
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)


def test_setup_logging_utf8_encoding(tmp_path: Path) -> None:
    """Test that log file uses UTF-8 encoding."""
    import sys

    log_file = tmp_path / "test.log"

    # Clear existing handlers
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers.clear()

    try:
        setup_logging(level="INFO", log_file=str(log_file))

        logger = logging.getLogger("test")

        # Write UTF-8 characters
        logger.info("Test with UTF-8: ěščřžýáíé")

        # Force flush
        for handler in root_logger.handlers:
            handler.flush()

        # Read file and check encoding
        content = log_file.read_text(encoding="utf-8")
        assert "ěščřžýáíé" in content
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)


def test_setup_logging_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that logging works with relative paths."""
    import sys
    import os

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    log_file = Path("relative_test.log")

    # Clear existing handlers
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers.clear()

    try:
        setup_logging(level="INFO", log_file=str(log_file))

        logger = logging.getLogger("test")
        logger.info("Test message")

        # Force flush
        for handler in root_logger.handlers:
            handler.flush()

        # File should be created in current directory
        assert log_file.exists()
        assert log_file.is_absolute() or (tmp_path / log_file).exists()
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)


def test_setup_logging_absolute_path(tmp_path: Path) -> None:
    """Test that logging works with absolute paths."""
    import sys

    log_file = tmp_path / "absolute_test.log"
    absolute_path = log_file.resolve()

    # Clear existing handlers
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers.clear()

    try:
        setup_logging(level="INFO", log_file=str(absolute_path))

        logger = logging.getLogger("test")
        logger.info("Test message")

        # Force flush
        for handler in root_logger.handlers:
            handler.flush()

        # File should be created at absolute path
        assert absolute_path.exists()
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)


def test_setup_logging_formatter(tmp_path: Path) -> None:
    """Test that log formatter is correct."""
    import sys

    log_file = tmp_path / "test.log"

    # Clear existing handlers
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers.clear()

    try:
        setup_logging(level="INFO", log_file=str(log_file))

        logger = logging.getLogger("test.module")
        logger.info("Test message")

        # Force flush
        for handler in root_logger.handlers:
            handler.flush()

        # Check format
        content = log_file.read_text(encoding="utf-8")
        # Should contain timestamp, level, name, message
        assert "INFO" in content
        assert "test.module" in content
        assert "Test message" in content
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)
