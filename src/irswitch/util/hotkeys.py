"""Global hotkey listener for RESTART mode detection."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Set

logger = logging.getLogger(__name__)

# Track currently pressed keys
_pressed_keys: Set[str] = set()
_lock = threading.Lock()
_listener: Optional[object] = None
_target_keys: Set[str] = set()
_hotkey_active = False
_last_hotkey_activation_ts: float = 0  # Timestamp of last hotkey activation
_HOTKEY_WINDOW_SECONDS = 10.0  # Window to detect hotkey before QUIT


def _normalize_key(key: str) -> str:
    """Normalize key name to lowercase."""
    return key.lower().replace("_l", "").replace("_r", "")


def _parse_hotkey(hotkey_str: str) -> Set[str]:
    """
    Parse hotkey string like "ctrl+shift+r" into set of key names.

    Supports: ctrl, shift, alt, and any letter/number key.
    """
    parts = hotkey_str.lower().split("+")
    keys = set()
    for part in parts:
        part = part.strip()
        if part in ("ctrl", "control"):
            keys.add("ctrl")
        elif part in ("shift",):
            keys.add("shift")
        elif part in ("alt",):
            keys.add("alt")
        elif part in ("cmd", "command", "win", "super"):
            keys.add("cmd")
        else:
            # Regular key (letter, number, etc.)
            keys.add(part)
    logger.info(f"Parsed hotkey '{hotkey_str}' -> {keys}")
    return keys


def _on_press(key) -> None:
    """Handle key press event."""
    global _hotkey_active, _last_hotkey_activation_ts
    try:
        # Get key name
        if hasattr(key, "char") and key.char:
            key_name = key.char.lower()
        elif hasattr(key, "name"):
            key_name = _normalize_key(key.name)
        else:
            return

        with _lock:
            _pressed_keys.add(key_name)
            # Check if all target keys are pressed
            if _target_keys and _target_keys.issubset(_pressed_keys):
                _last_hotkey_activation_ts = time.time()
                if not _hotkey_active:
                    _hotkey_active = True
                    logger.debug(f"Hotkey activated: {_target_keys}")
    except Exception as e:
        logger.debug(f"Error in hotkey press handler: {e}")


def _on_release(key) -> None:
    """Handle key release event."""
    global _hotkey_active
    try:
        # Get key name
        if hasattr(key, "char") and key.char:
            key_name = key.char.lower()
        elif hasattr(key, "name"):
            key_name = _normalize_key(key.name)
        else:
            return

        with _lock:
            _pressed_keys.discard(key_name)
            # Check if hotkey is no longer fully pressed
            if _hotkey_active and not _target_keys.issubset(_pressed_keys):
                _hotkey_active = False
                logger.debug(f"Hotkey deactivated: {_target_keys}")
    except Exception as e:
        logger.debug(f"Error in hotkey release handler: {e}")


def start_listener(hotkey_str: str) -> bool:
    """
    Start the global hotkey listener.

    Args:
        hotkey_str: Hotkey combination like "ctrl+shift+r"

    Returns:
        True if listener started successfully, False otherwise
    """
    global _listener, _target_keys

    if not hotkey_str:
        logger.debug("No hotkey configured, listener not started")
        return False

    try:
        from pynput import keyboard
    except ImportError:
        logger.warning("pynput not installed, hotkey listener disabled")
        return False

    _target_keys = _parse_hotkey(hotkey_str)
    if not _target_keys:
        logger.warning(f"Invalid hotkey string: {hotkey_str}")
        return False

    logger.info(f"Starting hotkey listener for: {hotkey_str} (keys: {_target_keys})")

    try:
        _listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
        _listener.start()
        return True
    except Exception as e:
        logger.error(f"Failed to start hotkey listener: {e}")
        return False


def stop_listener() -> None:
    """Stop the global hotkey listener."""
    global _listener, _hotkey_active

    if _listener is not None:
        try:
            _listener.stop()
            logger.info("Hotkey listener stopped")
        except Exception as e:
            logger.debug(f"Error stopping hotkey listener: {e}")
        finally:
            _listener = None
            _hotkey_active = False
            with _lock:
                _pressed_keys.clear()


def is_hotkey_pressed() -> bool:
    """
    Check if the configured hotkey is currently pressed.

    Returns:
        True if all keys in the hotkey combination are currently pressed
    """
    return _hotkey_active


def was_hotkey_pressed_recently() -> bool:
    """
    Check if the hotkey was pressed within the last HOTKEY_WINDOW_SECONDS.

    This is useful for detecting hotkey presses that happened shortly before
    an event (like QUIT detection), even if the keys were released.

    Returns:
        True if hotkey was pressed within the time window
    """
    if _last_hotkey_activation_ts == 0:
        # Never activated - log once per call for debugging
        return False
    elapsed = time.time() - _last_hotkey_activation_ts
    result = elapsed <= _HOTKEY_WINDOW_SECONDS
    return result
