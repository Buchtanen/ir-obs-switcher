"""Windows PDH thermal-zone counters. No extra process; fail-soft."""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import POINTER, byref, c_double, c_void_p, c_wchar, wintypes
from typing import Any

logger = logging.getLogger(__name__)

PDH_FMT_DOUBLE = 0x00000200
PDH_MORE_DATA = 0x800007D2
ERROR_SUCCESS = 0

_WILDCARDS = (
    r"\Thermal Zone Information(*)\High Precision Temperature",
    r"\Thermal Zone Information(*)\Temperature",
)


class _PDH_FMT_COUNTERVALUE(ctypes.Structure):
    class _Value(ctypes.Union):
        _fields_ = [
            ("longValue", ctypes.c_long),
            ("doubleValue", c_double),
            ("largeValue", ctypes.c_longlong),
        ]

    _anonymous_ = ("value",)
    _fields_ = [("CStatus", wintypes.DWORD), ("value", _Value)]


def read_pdh_thermal_rows() -> list[dict[str, Any]]:
    """Return PDH thermal-zone samples as {name, value} rows. Empty off Windows."""
    if sys.platform != "win32":
        return []
    try:
        return _expand_and_read()
    except Exception:
        logger.debug("PDH thermal zone read failed", exc_info=True)
        return []


def _expand_and_read() -> list[dict[str, Any]]:
    pdh = ctypes.windll.pdh  # type: ignore[attr-defined]
    _bind_pdh(pdh)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for wildcard in _WILDCARDS:
        for path in _expand_paths(pdh, wildcard):
            if path in seen:
                continue
            seen.add(path)
            value = _read_counter(pdh, path)
            if value is None:
                continue
            rows.append({"name": path, "value": value})
    return rows


def _bind_pdh(pdh: Any) -> None:
    pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, c_void_p, POINTER(c_void_p)]
    pdh.PdhOpenQueryW.restype = wintypes.DWORD
    pdh.PdhAddEnglishCounterW.argtypes = [
        c_void_p,
        wintypes.LPCWSTR,
        c_void_p,
        POINTER(c_void_p),
    ]
    pdh.PdhAddEnglishCounterW.restype = wintypes.DWORD
    pdh.PdhCollectQueryData.argtypes = [c_void_p]
    pdh.PdhCollectQueryData.restype = wintypes.DWORD
    pdh.PdhGetFormattedCounterValue.argtypes = [
        c_void_p,
        wintypes.DWORD,
        POINTER(wintypes.DWORD),
        POINTER(_PDH_FMT_COUNTERVALUE),
    ]
    pdh.PdhGetFormattedCounterValue.restype = wintypes.DWORD
    pdh.PdhCloseQuery.argtypes = [c_void_p]
    pdh.PdhCloseQuery.restype = wintypes.DWORD
    pdh.PdhExpandWildCardPathW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        POINTER(wintypes.DWORD),
        wintypes.DWORD,
    ]
    pdh.PdhExpandWildCardPathW.restype = wintypes.DWORD


def _expand_paths(pdh: Any, wildcard: str) -> list[str]:
    size = wintypes.DWORD(0)
    status = pdh.PdhExpandWildCardPathW(None, wildcard, None, byref(size), 0)
    if status not in (ERROR_SUCCESS, PDH_MORE_DATA) or size.value <= 1:
        return [wildcard]
    buf = (c_wchar * size.value)()
    status = pdh.PdhExpandWildCardPathW(None, wildcard, buf, byref(size), 0)
    if status != ERROR_SUCCESS:
        return [wildcard]
    raw = ctypes.wstring_at(ctypes.addressof(buf), size.value)
    return [part for part in raw.split("\x00") if part]


def _read_counter(pdh: Any, path: str) -> float | None:
    query = c_void_p()
    counter = c_void_p()
    if pdh.PdhOpenQueryW(None, None, byref(query)) != ERROR_SUCCESS:
        return None
    try:
        if pdh.PdhAddEnglishCounterW(query, path, None, byref(counter)) != ERROR_SUCCESS:
            return None
        if pdh.PdhCollectQueryData(query) != ERROR_SUCCESS:
            return None
        fmt = _PDH_FMT_COUNTERVALUE()
        if pdh.PdhGetFormattedCounterValue(counter, PDH_FMT_DOUBLE, None, byref(fmt)) != 0:
            return None
        return float(fmt.doubleValue)
    finally:
        pdh.PdhCloseQuery(query)
