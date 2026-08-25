"""LibreHardwareMonitor HTTP API (0.9.5+ dropped WMI). Localhost only."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PORTS = (8085,)
_VALUE_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_HTTP_TIMEOUT_S = 0.6
_LHM_HTTP_LOGGED = False


def parse_lhm_data_json(payload: Any) -> list[dict[str, Any]]:
    """Flatten LHM /data.json tree into sensor rows for pick_cpu_package."""
    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        _walk(payload, rows, parent="")
    return rows


def fetch_lhm_http_rows(ports: tuple[int, ...] = _DEFAULT_PORTS) -> list[dict[str, Any]]:
    """GET http://127.0.0.1:<port>/data.json. Empty if the web server is off."""
    global _LHM_HTTP_LOGGED
    last_error = None
    for port in ports:
        url = f"http://127.0.0.1:{int(port)}/data.json"
        try:
            with urllib.request.urlopen(url, timeout=_HTTP_TIMEOUT_S) as resp:
                raw = resp.read()
            payload = json.loads(raw.decode("utf-8", errors="replace"))
            rows = parse_lhm_data_json(payload)
            if rows:
                return rows
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
            ValueError,
        ) as exc:
            last_error = exc
            continue
    if last_error is not None and not _LHM_HTTP_LOGGED:
        _LHM_HTTP_LOGGED = True
        logger.info(
            "LibreHardwareMonitor HTTP API not reachable on 127.0.0.1:%s "
            "(Options → Remote Web Server → Run). LHM 0.9.5+ removed WMI.",
            ",".join(str(p) for p in ports),
        )
    return []


def _walk(node: dict[str, Any], rows: list[dict[str, Any]], parent: str) -> None:
    text = str(node.get("Text") or "")
    sensor_id = str(node.get("SensorId") or node.get("HardwareId") or "")
    typ = str(node.get("Type") or "")
    value = _parse_value(
        node.get("RawValue") if node.get("RawValue") not in (None, "") else node.get("Value")
    )
    if typ and value is not None:
        rows.append(
            {
                "name": text,
                "sensor_type": typ,
                "value": value,
                "identifier": sensor_id,
                "parent": parent,
            }
        )
    next_parent = sensor_id or text or parent
    children = node.get("Children") or []
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                _walk(child, rows, next_parent)


def _parse_value(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = _VALUE_RE.search(str(raw).replace(",", "."))
    if match is None:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def iter_sensor_nodes(payload: Any) -> Iterator[dict[str, Any]]:
    """Test helper: yield sensor dicts from a tree."""
    rows = parse_lhm_data_json(payload)
    yield from rows
