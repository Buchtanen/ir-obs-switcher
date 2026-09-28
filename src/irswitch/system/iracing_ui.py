"""Read-only launcher presence compatibility helper."""

from irswitch.system.companion_apps import detect_companion_apps


def detect_iracing_ui() -> bool | None:
    """Return exact launcher presence; call off the event loop."""
    return detect_companion_apps()["iracing_ui"]
