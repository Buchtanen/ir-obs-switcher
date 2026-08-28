"""BLE Heart Rate Measurement (0x2A37) parser."""

from __future__ import annotations


def parse_heart_rate_measurement(payload: bytes) -> tuple[int, tuple[int, ...]]:
    """
    Parse standard HRM characteristic.

    Returns (bpm, rr_intervals) where RR values are 1/1024 s units.
    """
    if not payload:
        raise ValueError("empty heart-rate payload")
    flags = payload[0]
    idx = 1
    if flags & 0x01:
        if idx + 2 > len(payload):
            raise ValueError("truncated UINT16 BPM")
        bpm = int.from_bytes(payload[idx : idx + 2], "little")
        idx += 2
    else:
        if idx >= len(payload):
            raise ValueError("truncated UINT8 BPM")
        bpm = payload[idx]
        idx += 1
    if flags & 0x08:  # energy expended
        idx += 2
    rr: list[int] = []
    if flags & 0x10:
        while idx + 1 < len(payload):
            rr.append(int.from_bytes(payload[idx : idx + 2], "little"))
            idx += 2
    return bpm, tuple(rr)


def classify_hr_state(
    delta: float | None,
    *,
    calm: float,
    focused: float,
    pushing: float,
) -> str:
    if delta is None:
        return "unknown"
    if delta < calm:
        return "calm"
    if delta < focused:
        return "focused"
    if delta < pushing:
        return "pushing"
    return "high"
