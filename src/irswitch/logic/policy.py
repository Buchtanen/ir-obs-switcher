"""Scene mapping policy."""
from __future__ import annotations

from collections.abc import Mapping

from irswitch.models import DrivingMode


class Policy:
    def __init__(self, scenes: Mapping[DrivingMode, str], safe_scene: str) -> None:
        self._scenes = dict(scenes)
        self._safe_scene = safe_scene

    def target_for_mode(self, mode: DrivingMode) -> str:
        return self._scenes.get(mode, self._safe_scene)
