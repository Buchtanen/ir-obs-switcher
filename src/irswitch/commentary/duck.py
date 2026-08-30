"""Duck an OBS audio input while commentary speaks, then restore."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType

from irswitch.overlay.settings import CommentarySettings

logger = logging.getLogger(__name__)

GetMul = Callable[[str], float | None]
SetMul = Callable[[str, float], bool]
Sleep = Callable[[float], None]

_FADE_STEP_MS = 50
_MUL_FLOOR = 1e-6


def ducked_mul(original: float, ratio: float) -> float:
    """Scale a linear OBS multiplier. Ratio is 0–1 of the original level."""
    scale = max(0.0, min(1.0, float(ratio)))
    return max(0.0, float(original) * scale)


def fade_mul(start: float, end: float, t: float) -> float:
    """Lerp linear OBS multipliers in dB so the ramp sounds even."""
    t = max(0.0, min(1.0, float(t)))
    if t <= 0.0:
        return max(0.0, float(start))
    if t >= 1.0:
        return max(0.0, float(end))
    db_a = 20.0 * math.log10(max(_MUL_FLOOR, float(start)))
    db_b = 20.0 * math.log10(max(_MUL_FLOOR, float(end)))
    return 10.0 ** ((db_a + (db_b - db_a) * t) / 20.0)


@dataclass
class VolumeDucker:
    """Nested-safe duck: first enter fades down, last exit fades back."""

    input_name: str
    ratio: float
    get_mul: GetMul
    set_mul: SetMul
    fade_ms: int = 0
    sleep: Sleep = time.sleep
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _depth: int = 0
    _saved: float | None = None
    _current: float | None = None
    _fade_gen: int = 0

    def __enter__(self) -> VolumeDucker:
        self.enter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.exit()

    def enter(self) -> None:
        name = (self.input_name or "").strip()
        if not name:
            return
        start: float | None = None
        target: float | None = None
        gen = 0
        with self._lock:
            self._depth += 1
            if self._depth != 1:
                return
            original = self.get_mul(name)
            if original is None:
                self._depth -= 1
                logger.warning("commentary duck skipped: no volume for input=%s", name)
                return
            self._saved = original
            start = self._current if self._current is not None else original
            target = ducked_mul(original, self.ratio)
            self._fade_gen += 1
            gen = self._fade_gen
        if start is None or target is None:
            return
        if not self._fade(name, start, target, gen):
            with self._lock:
                if self._depth == 1 and self._fade_gen == gen:
                    self._saved = None
                    self._depth -= 1

    def exit(self) -> None:
        name = (self.input_name or "").strip()
        if not name:
            return
        start: float | None = None
        target: float | None = None
        gen = 0
        with self._lock:
            if self._depth <= 0:
                return
            self._depth -= 1
            if self._depth != 0:
                return
            target = self._saved
            self._saved = None
            start = self._current if self._current is not None else target
            self._fade_gen += 1
            gen = self._fade_gen
        if target is None:
            return
        if start is None:
            start = target
        self._fade(name, start, target, gen)
        with self._lock:
            if self._fade_gen == gen:
                self._current = None

    def _fade(self, name: str, start: float, end: float, gen: int) -> bool:
        duration_ms = max(0, int(self.fade_ms))
        if duration_ms <= 0:
            if gen != self._fade_gen:
                return True
            if not self.set_mul(name, end):
                logger.warning("commentary duck set failed input=%s", name)
                return False
            self._current = end
            return True
        steps = max(1, round(duration_ms / _FADE_STEP_MS))
        step_s = duration_ms / 1000.0 / steps
        for index in range(1, steps + 1):
            if gen != self._fade_gen:
                return True
            mul = fade_mul(start, end, index / steps)
            if not self.set_mul(name, mul):
                logger.warning("commentary duck set failed input=%s", name)
                return False
            self._current = mul
            if index < steps:
                self.sleep(step_s)
        return True


def _obs_get_mul(name: str) -> float | None:
    from irswitch.server.api import get_obs_client

    client = get_obs_client()
    if client is None:
        return None
    return client.get_input_volume_mul(name)


def _obs_set_mul(name: str, mul: float) -> bool:
    from irswitch.server.api import get_obs_client

    client = get_obs_client()
    if client is None:
        return False
    return client.set_input_volume_mul(name, mul)


_shared_lock = threading.Lock()
_shared_ducker: VolumeDucker | None = None


def reset_shared_ducker() -> None:
    """Test helper: drop the process-wide ducker."""
    global _shared_ducker
    with _shared_lock:
        _shared_ducker = None


def ducker_from_settings(settings: CommentarySettings) -> VolumeDucker:
    """One ducker for the process so overlapping lines cannot double-duck."""
    global _shared_ducker
    with _shared_lock:
        if _shared_ducker is None:
            _shared_ducker = VolumeDucker(
                input_name=settings.duck_input,
                ratio=settings.duck_ratio,
                fade_ms=settings.duck_fade_ms,
                get_mul=_obs_get_mul,
                set_mul=_obs_set_mul,
            )
            return _shared_ducker
        if _shared_ducker._depth == 0:
            _shared_ducker.input_name = settings.duck_input
            _shared_ducker.ratio = settings.duck_ratio
            _shared_ducker.fade_ms = settings.duck_fade_ms
        return _shared_ducker
