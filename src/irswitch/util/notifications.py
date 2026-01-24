"""Windows toast notifications for connection alerts."""

from __future__ import annotations

import logging
import platform

logger = logging.getLogger(__name__)

# Global flag to enable/disable notifications
_notifications_enabled: bool = True


def set_notifications_enabled(enabled: bool) -> None:
    """Set global notifications enabled flag."""
    global _notifications_enabled
    _notifications_enabled = enabled


def show_toast(title: str, message: str, duration: int = 3) -> None:
    """
    Show Windows toast notification using PowerShell (works on Windows 10+).
    Does nothing on non-Windows systems or if notifications are disabled.

    Note: This function is deprecated. Dashboard notifications should be used instead.
    Kept for backward compatibility only.

    Args:
        title: Notification title
        message: Notification message
        duration: Duration in seconds
    """
    # Check global notifications flag first
    if not _notifications_enabled:
        return

    if platform.system() != "Windows":
        return  # Only works on Windows

    # Deprecated - no longer show system toasts
    # Dashboard notifications should be used instead
    logger.debug(f"Toast notification suppressed (deprecated): {title}: {message}")


def notify_connection_lost(
    service: str, was_connected: bool = True, connection_failed: bool = False
) -> None:
    """
    Log connection loss. Dashboard handles user notifications.

    Args:
        service: Service name (e.g., "OBS", "iRacing")
        was_connected: True if service was connected and then disconnected,
                      False if service never connected
        connection_failed: True if service is running but connection failed
                         (e.g., wrong password, authentication error)
    """
    if was_connected:
        message = f"{service} disconnected"
    elif connection_failed:
        message = f"{service} connection failed (check password/settings)"
    else:
        message = f"{service} is not running"

    logger.info(message)


def notify_connection_restored(service: str) -> None:
    """Log connection restoration. Dashboard handles user notifications."""
    logger.info(f"{service} connected")
