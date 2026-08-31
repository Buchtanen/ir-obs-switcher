"""Decode iRacing ``SessionFlags`` bits. Extraction only — no speak policy.

Bit values match ``irsdk_Flags`` in irsdk.h. Unknown leftover bits are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass

# Official irsdk_Flags (irsdk.h). Names are SDK identifiers without the prefix.
FLAG_BITS: dict[str, int] = {
    "checkered": 0x00000001,
    "white": 0x00000002,
    "green": 0x00000004,
    "yellow": 0x00000008,
    "red": 0x00000010,
    "blue": 0x00000020,
    "debris": 0x00000040,
    "crossed": 0x00000080,
    "yellowWaving": 0x00000100,
    "oneLapToGreen": 0x00000200,
    "greenHeld": 0x00000400,
    "tenToGo": 0x00000800,
    "fiveToGo": 0x00001000,
    "randomWaving": 0x00002000,
    "caution": 0x00004000,
    "cautionWaving": 0x00008000,
    "black": 0x00010000,
    "disqualify": 0x00020000,
    "servicible": 0x00040000,
    "furled": 0x00080000,
    "repair": 0x00100000,
    "startHidden": 0x10000000,
    "startReady": 0x20000000,
    "startSet": 0x40000000,
    "startGo": 0x80000000,
}

KNOWN_MASK = 0
for _bit in FLAG_BITS.values():
    KNOWN_MASK |= _bit


@dataclass(frozen=True)
class DecodedSessionFlags:
    """Named bits present in a SessionFlags int. Leftover is unsigned remainder."""

    names: tuple[str, ...]
    leftover: int
    checkered: bool
    yellow: bool
    green: bool


_EMPTY = DecodedSessionFlags(
    names=(),
    leftover=0,
    checkered=False,
    yellow=False,
    green=False,
)


def decode_session_flags(value: int | None) -> DecodedSessionFlags:
    """Map known bits to names. ``None`` / non-int → empty. Unknown bits dropped."""
    if value is None or isinstance(value, bool):
        return _EMPTY
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return _EMPTY
    # SessionFlags is unsigned 32-bit in the SDK.
    raw &= 0xFFFFFFFF
    names = tuple(name for name, bit in FLAG_BITS.items() if raw & bit)
    leftover = raw & ~KNOWN_MASK
    present = set(names)
    return DecodedSessionFlags(
        names=names,
        leftover=leftover,
        checkered="checkered" in present,
        yellow="yellow" in present,
        green="green" in present,
    )
