"""BLE heart-rate provider. Fail-soft, never blocks the loop."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

from irswitch.bio.history import HeartRateHistory
from irswitch.bio.parser import classify_hr_state, parse_heart_rate_measurement
from irswitch.overlay.models import BioState
from irswitch.overlay.settings import HeartRateSettings, SamplingSettings
from irswitch.sampling.scheduler import resolve_component_hz

logger = logging.getLogger(__name__)

HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"


def _hash_address(address: str) -> str:
    return hashlib.sha256(address.encode("utf-8")).hexdigest()[:8]


class BleHeartRateProvider:
    """
    Notifications-only HR reader.

    ``sample_hz() == 0`` means push (BLE notify). A positive override polls
    the last known state for the overlay bus without touching the radio.
    """

    def __init__(
        self,
        settings: HeartRateSettings,
        sampling: SamplingSettings,
        on_state: Callable[[BioState], None] | None = None,
    ) -> None:
        self._settings = settings
        self._sampling = sampling
        self._on_state = on_state
        self._history = HeartRateHistory(window_seconds=settings.baseline_window)
        self._state = BioState()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[Any] | None = None

    @property
    def name(self) -> str:
        return "bio"

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    def sample_hz(self) -> float:
        return resolve_component_hz(
            self._sampling.default_hz,
            self._sampling.bio_hz,
            push_when_unset=True,
        )

    def current(self) -> BioState:
        return self._state

    def apply_settings(self, settings: HeartRateSettings, sampling: SamplingSettings) -> None:
        self._settings = settings
        self._sampling = sampling
        self._history.window_seconds = settings.baseline_window

    def ingest_measurement(self, payload: bytes, now: float | None = None) -> BioState:
        """Parse a raw 0x2A37 payload (used by tests and mock)."""
        now = time.monotonic() if now is None else now
        bpm, rr = parse_heart_rate_measurement(payload)
        self._history.add(now, bpm)
        baseline = self._history.baseline()
        delta = (bpm - baseline) if baseline is not None else None
        hr_state = classify_hr_state(
            delta,
            calm=self._settings.calm_delta,
            focused=self._settings.focused_delta,
            pushing=self._settings.pushing_delta,
        )
        self._state = BioState(
            connected=True,
            status="connected",
            device_name=self._state.device_name,
            bpm=bpm,
            baseline_bpm=baseline,
            delta_bpm=delta,
            state=hr_state,
            rr_intervals=rr,
        )
        if self._on_state:
            self._on_state(self._state)
        return self._state

    def set_status(self, status: str, *, device_name: str | None = None) -> BioState:
        self._state = BioState(
            connected=status == "connected",
            status=status,
            device_name=device_name if device_name is not None else self._state.device_name,
            bpm=self._state.bpm if status == "connected" else None,
            baseline_bpm=self._state.baseline_bpm,
            delta_bpm=self._state.delta_bpm,
            state=self._state.state if status == "connected" else "unknown",
            rr_intervals=self._state.rr_intervals if status == "connected" else (),
        )
        if self._on_state:
            self._on_state(self._state)
        return self._state

    async def run(self) -> None:
        if not self._settings.enabled:
            self.set_status("disconnected")
            await self._stop.wait()
            return
        try:
            import bleak  # noqa: F401
        except ImportError:
            logger.warning(
                "BLE heart-rate skipped: bleak is not installed. Reinstall: pip install -e ."
            )
            self.set_status("disconnected")
            await self._stop.wait()
            return
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._connect_once()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("BLE heart-rate session failed", exc_info=True)
            if self._stop.is_set() or not self._settings.reconnect:
                break
            self.set_status("reconnecting")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
            except TimeoutError:
                pass
            backoff = min(backoff * 2, 30.0)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _connect_once(self) -> None:
        from bleak import BleakClient, BleakScanner

        self.set_status("connecting")
        device = await self._scan(BleakScanner)
        if device is None:
            raise RuntimeError("no heart-rate device")
        address = getattr(device, "address", None) or str(device)
        name = getattr(device, "name", None)
        logger.info("BLE connecting device=%s", _hash_address(str(address)))
        disconnected = asyncio.Event()

        def _on_disconnect(_client: object) -> None:
            disconnected.set()

        async with BleakClient(device, disconnected_callback=_on_disconnect) as client:
            self.set_status("connected", device_name=name)

            def _notify(_handle: int, data: bytearray) -> None:
                try:
                    self.ingest_measurement(bytes(data))
                except Exception:
                    logger.debug("HR parse failed", exc_info=True)

            await client.start_notify(HR_MEASUREMENT, _notify)
            waiters = [
                asyncio.create_task(disconnected.wait()),
                asyncio.create_task(self._stop.wait()),
            ]
            done, pending = await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            try:
                await client.stop_notify(HR_MEASUREMENT)
            except Exception:
                pass
        self.set_status("disconnected")

    async def _scan(self, scanner_cls: Any) -> Any:
        wanted = (self._settings.device or "auto").strip()
        devices = await scanner_cls.discover(timeout=8.0)
        if wanted and wanted.lower() != "auto":
            wanted_l = wanted.lower()
            for device in devices:
                name = (getattr(device, "name", None) or "").lower()
                address = (getattr(device, "address", None) or "").lower()
                if wanted_l in {name, address}:
                    return device
            return None
        for device in devices:
            uuids = {u.lower() for u in (getattr(device, "metadata", {}) or {}).get("uuids", [])}
            if HR_SERVICE in uuids:
                return device
            name = (getattr(device, "name", None) or "").lower()
            if "heart" in name or "hr" in name.split():
                return device
        return None
