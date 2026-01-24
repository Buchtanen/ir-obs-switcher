"""Console alert system with toast-style highlighting."""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Enable ANSI escape codes in Windows console once at module load
_ansi_enabled = False
if sys.platform == 'win32':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # Get handle to stderr
        handle = kernel32.GetStdHandle(-12)  # STD_ERROR_HANDLE
        # Get current mode
        current_mode = ctypes.wintypes.DWORD()
        if kernel32.GetConsoleMode(handle, ctypes.byref(current_mode)):
            # Enable virtual terminal processing
            new_mode = current_mode.value | 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            if kernel32.SetConsoleMode(handle, new_mode):
                _ansi_enabled = True
                logger.debug("ANSI escape codes enabled for Windows console")
    except Exception as e:
        logger.debug(f"Failed to enable ANSI escape codes: {e}")

# ANSI escape codes for colors and formatting
RESET = "\033[0m"
BOLD = "\033[1m"
BRIGHT_BG_GREEN = "\033[102m"  # Bright green background
BRIGHT_BG_YELLOW = "\033[103m"  # Bright yellow background
BRIGHT_BG_RED = "\033[101m"  # Bright red background
BRIGHT_BG_BLUE = "\033[104m"  # Bright blue background
BRIGHT_BG_CYAN = "\033[106m"  # Bright cyan background
BRIGHT_BG_MAGENTA = "\033[105m"  # Bright magenta background
FG_BLACK = "\033[30m"  # Black foreground (for readability on bright backgrounds)


def format_event_alert(
    event_type: str,
    message: str,
    data: Optional[dict] = None,
) -> str:
    """
    Format event as alert: "XXX Detected | Action AAAA Activated | Scene SSSS"
    
    Args:
        event_type: Type of event (e.g., "connection_lost", "scene_switch")
        message: Human-readable message
        data: Optional additional data
        
    Returns:
        Formatted alert string
    """
    data = data or {}
    
    # Extract components from event type and data
    detected = _format_detected(event_type, data, message)
    action = _format_action(event_type, message, data)
    scene = _format_scene(event_type, data)
    
    # Build alert string
    parts = []
    if detected:
        parts.append(detected)
    if action:
        parts.append(action)
    if scene:
        parts.append(scene)
    
    if not parts:
        # Fallback to original message if we can't format it
        return message
    
    return " | ".join(parts)


def _format_detected(event_type: str, data: dict, message: str = "") -> str:
    """Format the "XXX Detected" part."""
    detected_map = {
        "connection_lost": lambda d, m: f"{_extract_component_from_message(m, '')} Disconnected",
        "connection_restored": lambda d, m: f"{_extract_component_from_message(m, '')} Connected",
        "loading_started": "Loading Detected",
        "loading_ended": "Loading Completed",
        "game_started": lambda d, m: f"{d.get('mode', 'Game').upper()} Detected",
        "scene_switch": "Scene Change Detected",
        "stream_started": "Stream Started",
        "stream_stopped": "Stream Stopped",
        "stream_start_failed": "Stream Start Failed",
        "stream_stop_failed": "Stream Stop Failed",
        "stream_start_skipped": "Stream Start Skipped",
        "stream_stop_skipped": "Stream Stop Skipped",
        "override_applied": "Override Detected",
        "autoswitch_toggled": "Autoswitch Toggled",
        "stream_title_detected": lambda d, m: f"Stream Title Detected",
    }
    
    formatter = detected_map.get(event_type)
    if formatter:
        if callable(formatter):
            return formatter(data, message)
        return formatter
    return f"{event_type.replace('_', ' ').title()} Detected"


def _extract_component_from_message(message: str, suffix: str) -> str:
    """Extract component name from message like 'iRacing connection restored'."""
    # Try to extract component (e.g., "iRacing", "OBS") from message
    message_lower = message.lower()
    if "iracing" in message_lower:
        component = "iRacing"
    elif "obs" in message_lower:
        component = "OBS"
    else:
        component = "Connection"
    
    if suffix:
        return f"{component} {suffix}"
    return component


def _format_action(event_type: str, message: str, data: dict) -> str:
    """Format the "Action AAAA Activated" part."""
    action_map = {
        "connection_lost": lambda d, m: f"{_extract_component_from_message(m, '')} Connection Lost",
        "connection_restored": lambda d, m: f"{_extract_component_from_message(m, '')} Connection Restored",
        "loading_started": "Loading Started",
        "loading_ended": "Loading Completed",
        "game_started": lambda d, m: f"Game Mode {d.get('mode', 'Unknown')} Activated",
        "scene_switch": "Scene Switch Activated",
        "stream_started": "Stream Start Activated",
        "stream_stopped": "Stream Stop Activated",
        "stream_start_failed": "Stream Start Failed",
        "stream_stop_failed": "Stream Stop Failed",
        "stream_start_skipped": "Stream Start Skipped",
        "stream_stop_skipped": "Stream Stop Skipped",
        "override_applied": lambda d, m: f"Override Activated ({d.get('seconds', '?')}s)",
        "autoswitch_toggled": lambda d, m: f"Autoswitch {'Enabled' if d.get('autoswitch', False) else 'Disabled'}",
        "stream_title_detected": lambda d, m: f"Stream Title: {d.get('stream_title', 'Unknown')}",
    }
    
    formatter = action_map.get(event_type)
    if formatter:
        if callable(formatter):
            return formatter(data, message)
        return formatter
    return f"{event_type.replace('_', ' ').title()} Activated"


def _format_scene(event_type: str, data: dict) -> str:
    """Format the "Scene SSSS" part."""
    scene = data.get("scene")
    if scene:
        return f"Scene {scene}"
    
    # Try to extract scene from message if not in data
    if "scene" in data:
        scene_val = data["scene"]
        if isinstance(scene_val, str):
            return f"Scene {scene_val}"
    
    # For scene_switch events, scene should always be present
    if event_type == "scene_switch" and not scene:
        return "Scene Unknown"
    
    return None


def get_alert_color(event_type: str) -> tuple[str, str]:
    """
    Get ANSI color codes for alert highlighting.
    
    Returns:
        Tuple of (background_code, foreground_code)
    """
    color_map = {
        "connection_lost": (BRIGHT_BG_RED, FG_BLACK),
        "connection_restored": (BRIGHT_BG_GREEN, FG_BLACK),
        "loading_started": (BRIGHT_BG_CYAN, FG_BLACK),
        "loading_ended": (BRIGHT_BG_CYAN, FG_BLACK),
        "game_started": (BRIGHT_BG_GREEN, FG_BLACK),
        "scene_switch": (BRIGHT_BG_BLUE, FG_BLACK),
        "stream_started": (BRIGHT_BG_GREEN, FG_BLACK),
        "stream_stopped": (BRIGHT_BG_YELLOW, FG_BLACK),
        "stream_start_failed": (BRIGHT_BG_RED, FG_BLACK),
        "stream_stop_failed": (BRIGHT_BG_RED, FG_BLACK),
        "stream_start_skipped": (BRIGHT_BG_YELLOW, FG_BLACK),
        "stream_stop_skipped": (BRIGHT_BG_YELLOW, FG_BLACK),
        "override_applied": (BRIGHT_BG_MAGENTA, FG_BLACK),
        "autoswitch_toggled": (BRIGHT_BG_MAGENTA, FG_BLACK),
        "stream_title_detected": (BRIGHT_BG_CYAN, FG_BLACK),
    }
    
    return color_map.get(event_type, (BRIGHT_BG_CYAN, FG_BLACK))


def show_console_alert(
    event_type: str,
    message: str,
    data: Optional[dict] = None,
    highlight_duration: float = 3.0,
) -> None:
    """
    Show formatted console alert with toast-style highlighting.
    
    Args:
        event_type: Type of event
        message: Human-readable message
        data: Optional additional data
        highlight_duration: Duration in seconds for toast highlighting (default: 3.0)
    """
    # Format the alert
    alert_text = format_event_alert(event_type, message, data)
    
    # Get timestamp
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Get color codes
    bg_color, fg_color = get_alert_color(event_type)
    
    # Format with toast highlighting (bright background)
    highlighted = f"{bg_color}{fg_color}{BOLD} {alert_text} {RESET}"
    
    # Print highlighted version
    print(f"{timestamp} {highlighted}", file=sys.stderr, flush=True)


async def show_console_alert_async(
    event_type: str,
    message: str,
    data: Optional[dict] = None,
    highlight_duration: float = 3.0,
) -> None:
    """
    Async version of show_console_alert with toast-style fade effect.
    
    Shows highlighted version immediately, then fades to normal after highlight_duration.
    
    Args:
        event_type: Type of event
        message: Human-readable message
        data: Optional additional data
        highlight_duration: Duration in seconds for toast highlighting (default: 3.0)
    """
    # Format the alert
    alert_text = format_event_alert(event_type, message, data)
    
    # Get timestamp
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Get color codes
    bg_color, fg_color = get_alert_color(event_type)
    
    # Format with toast highlighting (bright background)
    highlighted = f"{bg_color}{fg_color}{BOLD} {alert_text} {RESET}"
    normal = f"{alert_text}"
    
    # Print highlighted version immediately
    print(f"{timestamp} {highlighted}", file=sys.stderr, flush=True)
    
    # Schedule fade to normal version after highlight_duration
    # Use asyncio.create_task to schedule fade (fire and forget)
    try:
        loop = asyncio.get_running_loop()
        # Event loop is running, create task for fade effect
        async def fade_to_normal():
            await asyncio.sleep(highlight_duration)
            # Use ANSI escape codes to move cursor up one line and overwrite
            # \033[A = move cursor up, \033[K = clear to end of line
            # \r = carriage return to start of line
            if _ansi_enabled:
                print(f"\033[A\r\033[K{timestamp} {normal}", file=sys.stderr, flush=True)
            else:
                # Fallback: just print normal version on new line
                print(f"{timestamp} {normal}", file=sys.stderr, flush=True)
        
        # Create task (fire and forget)
        loop.create_task(fade_to_normal())
    except RuntimeError:
        # No event loop available, just show highlighted version
        pass
