"""BLE heart-rate provider. Fail-soft, never blocks the loop."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sys
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


def _scan_rows(raw: Any) -> list[tuple[Any, Any | None]]:
    """Normalize BleakScanner.discover() list or return_adv dict into (device, adv)."""
    if isinstance(raw, dict):
        rows: list[tuple[Any, Any | None]] = []
        for key, val in raw.items():
            if isinstance(val, tuple) and len(val) == 2:
                rows.append((val[0], val[1]))
            else:
                rows.append((key, val))
        return rows
    return [(device, None) for device in (raw or ())]


def _device_name(device: Any, adv: Any | None) -> str:
    name = getattr(device, "name", None) or ""
    if name:
        return str(name).strip()
    if adv is not None:
        return str(getattr(adv, "local_name", None) or "").strip()
    return ""


def _device_address(device: Any) -> str:
    return str(getattr(device, "address", None) or "").strip()


def _advertised_service_uuids(device: Any, adv: Any | None) -> set[str]:
    uuids: set[str] = set()
    if adv is not None:
        for uid in getattr(adv, "service_uuids", None) or ():
            uuids.add(str(uid).lower())
    meta = getattr(device, "metadata", None) or {}
    for uid in meta.get("uuids", []) or []:
        uuids.add(str(uid).lower())
    return uuids


def _name_looks_like_hr(name: str) -> bool:
    lowered = name.lower()
    if "heart" in lowered:
        return True
    tokens = lowered.replace("-", " ").replace("_", " ").split()
    return "hr" in tokens or "hrm" in tokens


def pick_heart_rate_device(rows: list[tuple[Any, Any | None]], wanted: str) -> Any | None:
    """Pick a scanned BLE device. ``wanted`` is ``auto`` or a name/address substring."""
    wanted_l = (wanted or "auto").strip().lower()
    if wanted_l and wanted_l != "auto":
        for device, adv in rows:
            name = _device_name(device, adv).lower()
            address = _device_address(device).lower()
            if wanted_l in {name, address} or wanted_l in name or wanted_l in address:
                return device
        return None
    for device, adv in rows:
        if HR_SERVICE in _advertised_service_uuids(device, adv):
            return device
    for device, adv in rows:
        if _name_looks_like_hr(_device_name(device, adv)):
            return device
    return None


async def pair_if_supported(client: Any) -> None:
    """Windows HR notify often needs a bond. Fail-soft if already paired or unsupported."""
    pair = getattr(client, "pair", None)
    if not callable(pair):
        return
    try:
        await pair()
    except Exception:
        logger.debug("BLE pair skipped", exc_info=True)


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
                "BLE heart-rate skipped: bleak is not installed for %s. "
                'Install with that interpreter: "%s" -m pip install -e .',
                sys.executable,
                sys.executable,
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
        address = _device_address(device) or str(device)
        name = _device_name(device, None) or None
        logger.info("BLE connecting device=%s", _hash_address(str(address)))
        disconnected = asyncio.Event()

        def _on_disconnect(_client: object) -> None:
            disconnected.set()

        async with BleakClient(device, disconnected_callback=_on_disconnect) as client:
            await pair_if_supported(client)
            self.set_status("connected", device_name=name)

            def _notify(_char: object, data: bytearray) -> None:
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
        try:
            raw = await scanner_cls.discover(timeout=8.0, return_adv=True)
        except TypeError:
            raw = await scanner_cls.discover(timeout=8.0)
        rows = _scan_rows(raw)
        picked = pick_heart_rate_device(rows, wanted)
        if picked is None:
            logger.warning("BLE HR scan matched nothing (devices=%s wanted=%s)", len(rows), wanted)
        return picked
