"""Logging helpers for structured logging."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Literal, Optional

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Try to use colorama for Windows color support, fallback to ANSI codes
_ansi_enabled = False
try:
    import colorama

    colorama.init(strip=False)  # Initialize colorama (enables ANSI on Windows)
    _ansi_enabled = True
    # Use colorama's color constants
    from colorama import Fore, Style

    _RESET = Style.RESET_ALL
    _BOLD = Style.BRIGHT
    _GRAY = Fore.LIGHTBLACK_EX
    _BLUE = Fore.LIGHTBLUE_EX
    _GREEN = Fore.LIGHTGREEN_EX
    _YELLOW = Fore.LIGHTYELLOW_EX
    _RED = Fore.LIGHTRED_EX
    _MAGENTA = Fore.LIGHTMAGENTA_EX
    _CYAN = Fore.LIGHTCYAN_EX
except ImportError:
    # Fallback to ANSI escape codes if colorama not available
    _RESET = "\033[0m"
    _BOLD = "\033[1m"
    _GRAY = "\033[90m"
    _BLUE = "\033[94m"
    _GREEN = "\033[92m"
    _YELLOW = "\033[93m"
    _RED = "\033[91m"
    _MAGENTA = "\033[95m"
    _CYAN = "\033[96m"

    # Try to enable ANSI escape codes in Windows console manually
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32

            # Enable for both stdout and stderr
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            STD_OUTPUT_HANDLE = -11
            STD_ERROR_HANDLE = -12

            for handle_id in [STD_OUTPUT_HANDLE, STD_ERROR_HANDLE]:
                handle = kernel32.GetStdHandle(handle_id)
                if handle and handle != -1:  # Valid handle
                    current_mode = wintypes.DWORD()
                    if kernel32.GetConsoleMode(handle, ctypes.byref(current_mode)):
                        new_mode = (
                            current_mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
                        )
                        if kernel32.SetConsoleMode(handle, new_mode):
                            _ansi_enabled = True
                            break  # If at least one works, enable colors
        except Exception:
            pass  # ANSI codes may not work, fallback to plain text


class ColoredFormatter(logging.Formatter):
    """Formatter that adds colors to log levels."""

    def format(self, record: logging.LogRecord) -> str:
        if not _ansi_enabled:
            return super().format(record)

        # Color mapping for log levels
        level_colors = {
            "DEBUG": _GRAY,
            "INFO": _GREEN,
            "WARNING": _YELLOW,
            "ERROR": _RED,
            "CRITICAL": _RED + _BOLD,
        }

        # Get color for this level
        level_color = level_colors.get(record.levelname, "")

        # Format timestamp
        timestamp = self.formatTime(record, self.datefmt)

        # Format message
        message = record.getMessage()

        # Build colored output manually to avoid formatting issues
        colored_timestamp = f"{_GRAY}{timestamp}{_RESET}"
        colored_levelname = f"{level_color}{record.levelname}{_RESET}"
        colored_name = f"{_CYAN}{record.name}{_RESET}"

        # Format: timestamp | level | component | message
        # Use fixed width for levelname (8 chars) without counting ANSI codes
        levelname_padded = f"{record.levelname:<8}"
        result = f"{colored_timestamp} | {level_color}{levelname_padded}{_RESET} | {colored_name} | {message}"

        return result


def setup_logging(
    level: str | LogLevel = "INFO",
    log_file: Optional[str | Path] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    use_colors: bool = True,
) -> None:
    """
    Configure Python logging with structured format.

    Always logs to stderr (console). Optionally logs to file with rotation.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file (if None, logs only to stderr)
        max_bytes: Maximum log file size before rotation (default: 10 MB)
        backup_count: Number of backup log files to keep (default: 5)
        use_colors: Enable colored output for console (default: True)

    Format: timestamp | level | component | message
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Use colored formatter for console, plain for file
    if use_colors and _ansi_enabled:
        console_formatter = ColoredFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        console_formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    file_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()  # Remove existing handlers

    # Always log to stderr (console) with colors
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(console_formatter)
    root_logger.addHandler(stderr_handler)

    # Debug: log if colors are enabled
    if use_colors:
        colors_status = "enabled" if _ansi_enabled else "disabled (ANSI not supported)"
        root_logger.debug(f"Console colors: {colors_status}")

    # Optionally log to file with rotation
    if log_file:
        log_path = Path(log_file)
        # Create log directory if it doesn't exist
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Prevent duplicate logs
    root_logger.propagate = False

    # Suppress noisy logs from obsws_python library
    # Set obsws_python loggers to CRITICAL level to suppress expected vendor request errors
    # Code 600 "No vendor was found" errors are expected when trying different vendor names
    # These errors are handled gracefully in the code and don't need to be logged

    # Custom filter to suppress vendor request errors (code 600)
    class VendorRequestFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            # Suppress messages containing vendor request errors
            msg = record.getMessage()
            if "CallVendorRequest" in msg and (
                "code 600" in msg or "No vendor was found" in msg
            ):
                return False
            if "OBSSDKRequestError" in msg and "code 600" in msg:
                return False
            return True

    vendor_filter = VendorRequestFilter()

    obsws_loggers = [
        logging.getLogger("obsws_python"),
        logging.getLogger("obsws_python.baseclient"),
        logging.getLogger("obsws_python.reqs"),
        logging.getLogger("obsws_python.baseclient.ObsClient"),  # More specific logger
        logging.getLogger("obsws_python.error"),  # Error logger
    ]
    for obsws_logger in obsws_loggers:
        obsws_logger.setLevel(logging.CRITICAL)  # Suppress all except CRITICAL errors
        obsws_logger.addFilter(
            vendor_filter
        )  # Add filter to suppress vendor request errors
        # Also disable propagation to prevent parent logger from showing these
        obsws_logger.propagate = False

    # Also add filter to root logger to catch any vendor request errors that slip through
    root_logger.addFilter(vendor_filter)

    # Suppress warnings from obsws_python vendor requests
    import warnings

    warnings.filterwarnings("ignore", category=UserWarning, module="obsws_python")


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


def log_override_applied(logger: logging.Logger, scene: str, until_ms: int) -> None:
    """Log override application."""
    logger.info(f"override_applied: {scene} until {until_ms}")


def log_connection_lost(logger: logging.Logger, component: str) -> None:
    """Log connection loss."""
    logger.warning(f"connection_lost: {component}")


def log_connection_restored(logger: logging.Logger, component: str) -> None:
    """Log connection restoration."""
    logger.info(f"connection_restored: {component}")
