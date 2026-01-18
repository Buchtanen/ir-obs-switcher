"""Wrapper around pyirsdk shared memory reader."""
from __future__ import annotations

from typing import Iterable

import irsdk


class IRacingReader:
    def __init__(self, poll_hz: int) -> None:
        self.poll_hz = poll_hz
        self._sdk = irsdk.IRSDK()

    def startup(self) -> None:
        self._sdk.startup()

    def is_connected(self) -> bool:
        return bool(self._sdk.is_initialized)

    def read_vars(self, names: Iterable[str]) -> dict[str, object]:
        return {name: self._sdk[name] for name in names}
