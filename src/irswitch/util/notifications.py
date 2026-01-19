"""Windows toast notifications for connection alerts."""
from __future__ import annotations

import ctypes
import json
import os
import platform
import subprocess
from typing import Optional

# Windows API constants
MB_OK = 0x0
MB_ICONINFORMATION = 0x40
MB_ICONWARNING = 0x30
MB_ICONERROR = 0x10
MB_TOPMOST = 0x40000

# Global flag to enable/disable notifications
_notifications_enabled: bool = True


def set_notifications_enabled(enabled: bool) -> None:
    """Set global notifications enabled flag."""
    global _notifications_enabled
    _notifications_enabled = enabled


def show_toast(title: str, message: str, duration: int = 3) -> None:
    """
    Show Windows toast notification using PowerShell (works on Windows 10+).
    Falls back to MessageBox if PowerShell fails.
    
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
    
    # Use MessageBox as primary method (most reliable)
    # PowerShell toast is unreliable on many Windows systems
    _show_messagebox(title, message)


def _show_toast_powershell(title: str, message: str, duration: int) -> None:
    """Show toast notification using PowerShell (Windows 10+)."""
    try:
        # Escape special characters for PowerShell XML
        title_escaped = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        message_escaped = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        
        # PowerShell command to show toast notification
        ps_script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        
        $template = @"
        <toast>
            <visual>
                <binding template="ToastGeneric">
                    <text>{title_escaped}</text>
                    <text>{message_escaped}</text>
                </binding>
            </visual>
        </toast>
"@
        
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)
        
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("iRacing OBS Switcher")
        $notifier.Show($toast)
        Start-Sleep -Milliseconds 100
        Write-Host "Toast command executed"
        """
        
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            check=True,
            capture_output=True,
            timeout=3,
            text=True
        )
        # PowerShell toast might not show if Windows notifications are disabled
        # but we don't fail - just log it
        if result.stderr:
            pass  # Ignore stderr from PowerShell toast
    except subprocess.TimeoutExpired as e:
        raise
    except subprocess.CalledProcessError as e:
        raise
    except Exception as e:
        raise


def _show_messagebox(title: str, message: str) -> None:
    """Show Windows MessageBox as fallback."""
    try:
        result = ctypes.windll.user32.MessageBoxW(
            0,
            message,
            title,
            MB_OK | MB_ICONINFORMATION | MB_TOPMOST
        )
    except Exception as e:
        # Silently fail if MessageBox also fails
        pass


def notify_connection_lost(service: str, was_connected: bool = True, connection_failed: bool = False) -> None:
    """
    Notify user that connection to service was lost or failed.
    
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
    
    show_toast(
        "iRacing OBS Switcher",
        message,
        duration=5
    )


def notify_connection_restored(service: str) -> None:
    """Notify user that connection to service was restored."""
    show_toast(
        "iRacing OBS Switcher",
        f"{service} connected",
        duration=3
    )
