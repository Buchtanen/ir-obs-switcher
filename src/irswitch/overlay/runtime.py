"""Compatibility import for the pre-N12 runtime location.

New composition code imports :class:`irswitch.race.runtime.RaceRuntime`.
"""

from irswitch.race.runtime import OverlayMode, RaceRuntime

OverlayRuntime = RaceRuntime

__all__ = ["OverlayMode", "OverlayRuntime"]
