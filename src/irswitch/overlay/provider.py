"""Fail-soft provider protocol. Implementations must never crash the host loop."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class OverlayProvider(Protocol):
    """Minimal contract every overlay data source implements."""

    @property
    def name(self) -> str: ...

    @property
    def enabled(self) -> bool: ...

    def sample_hz(self) -> float:
        """Poll rate in Hz. ``0`` means the provider is push/event-driven."""
        ...
