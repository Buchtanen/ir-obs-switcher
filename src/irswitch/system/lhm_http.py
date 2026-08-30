"""LibreHardwareMonitor HTTP API (0.9.5+ dropped WMI). Localhost / bound NIC only.

Two independent caches/TTLs live here (see admin_dashboard_spec.md §5 "Live
transport" + sysinfo_lhm_upgrade_spec.md §6 "Admin / observability"):

- ``_ROWS_TTL_S`` (~1.5s): ``fetch_lhm_http_rows`` — short-lived cache for the
  sampling hot path (sysinfo/cpu_sensors want fresh-ish sensor values often).
- ``_STATUS_TTL_S`` (5-10s): ``lhm_connection_status`` — a slower, decoupled
  cache for the admin/diagnostics connection-status path so a ~2s admin poll
  loop does not force a network round trip on every request. Concurrent
  callers of ``lhm_connection_status`` share a single in-flight probe
  (single-flight via ``_STATUS_LOCK``); nobody fires a redundant HTTP request
  while one is already outstanding.
"""

from __future__ import annotations

import gzip
import http.client
import ipaddress
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 8085
_VALUE_RE = re.compile(r"[-+]?\d+(?:\.\d+(?:[eE][-+]?\d+)?)?")
_PORT_RE = re.compile(r'key="listenerPort"\s+value="(\d+)"', re.I)
_IP_RE = re.compile(r'key="listenerIp"\s+value="([^"]*)"', re.I)
_PROM_LABEL_RE = re.compile(r'"?(\w+)"?\s*=\s*"([^"]*)"')
# Rejected LHM bind wildcards; never used as a listen address.
_WILDCARD_IPS = {"", "+", "*", "?", "0.0.0.0", "::"}  # nosec B104
_ALLOWED_PATHS = {"", "/", "/data.json", "/metrics"}
_HTTP_TIMEOUT_S = 2.5
_ROWS_TTL_S = 1.5
_CONFIG_TTL_S = 30.0
# Connection-status cache TTL, decoupled from _ROWS_TTL_S — see module docstring.
_STATUS_TTL_S = 7.0
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "identity",
    "User-Agent": "irswitch-lhm",
}

# Data lock: guards all module-level cache reads/writes below. Held only for
# bookkeeping, never across a network call.
_LOCK = threading.Lock()
# Probe lock: single-flight gate for lhm_connection_status. A caller holds
# this only while an actual HTTP probe is in flight, so waiters can reuse
# the freshly-written cache instead of issuing their own redundant request.
_STATUS_LOCK = threading.Lock()

_LHM_HTTP_LOGGED = False
_LHM_HTTP_OK_LOGGED = False
_LHM_HTTP_EMPTY_LOGGED = False
_CACHED_ROWS: tuple[float, list[dict[str, Any]]] | None = None
_CACHED_BASE: str | None = None
_CACHED_CONFIG: tuple[float, int, str | None] | None = None

# Populated by fetch_lhm_http_rows on every *real* probe (not on a cache hit):
# whether the LHM listener answered at all, regardless of row count. This is
# what lets lhm_connection_status tell "unreachable" apart from
# "reachable_empty" even when fetch_lhm_http_rows() alone can only return an
# empty list for both cases.
_LAST_PROBE_REACHED = False
_LAST_PROBE_BASE: str | None = None
_LAST_PROBE_ERROR: Exception | None = None
_LAST_SUCCESS_AT: float | None = None

# lhm_connection_status result cache (5-10s TTL) + single-flight epoch.
_CACHED_STATUS: dict[str, Any] | None = None
_STATUS_EPOCH = 0

Opener = Callable[..., Any]


def parse_lhm_config(text: str) -> dict[str, Any]:
    """Read listenerPort / listenerIp from LibreHardwareMonitor.config XML."""
    port = _DEFAULT_PORT
    ip: str | None = None
    match = _PORT_RE.search(text)
    if match:
        port = int(match.group(1))
    match = _IP_RE.search(text)
    if match:
        raw = match.group(1).strip()
        if raw and raw not in _WILDCARD_IPS and is_local_lhm_host(raw):
            ip = raw
    return {"port": port, "ip": ip}


def is_local_lhm_host(host: str) -> bool:
    """Loopback / RFC1918 / link-local only. No DNS — host must be localhost or a literal IP."""
    cleaned = host.strip().strip("[]")
    if not cleaned or cleaned in _WILDCARD_IPS:
        return False
    if cleaned.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(cleaned)
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private or ip.is_link_local)


def is_allowed_lhm_url(url: str) -> bool:
    """SSRF gate: http to a local LHM listener, only /data.json or /metrics."""
    parsed = urlparse(url)
    if parsed.scheme != "http":
        return False
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    if parsed.path not in _ALLOWED_PATHS:
        return False
    host = parsed.hostname
    port = parsed.port
    if not host or port is None or not (1 <= int(port) <= 65535):
        return False
    return is_local_lhm_host(host)


def iter_http_bases(
    port: int = _DEFAULT_PORT,
    bind_ip: str | None = None,
    extra_hosts: tuple[str, ...] = (),
) -> list[str]:
    """HTTP origins to try. Bound NIC first: HttpListener on a LAN IP ignores 127.0.0.1."""
    hosts: list[str] = []

    def add(host: str | None) -> None:
        if not host:
            return
        host = host.strip()
        if not is_local_lhm_host(host):
            return
        if host not in hosts:
            hosts.append(host)

    add(bind_ip)
    for host in extra_hosts:
        add(host)
    add("127.0.0.1")
    add("localhost")
    bases: list[str] = []
    for host in hosts:
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        bases.append(f"http://{host}:{int(port)}")
    return bases


def parse_lhm_data_json(payload: Any) -> list[dict[str, Any]]:
    """Flatten LHM /data.json tree into sensor rows for pick_cpu_package."""
    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        _walk(payload, rows, parent="", hardware="")
    return rows


def parse_lhm_prometheus(text: str) -> list[dict[str, Any]]:
    """Flatten LHM /metrics CPU (and motherboard CPU-named) gauges."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lowered = stripped.lower()
        if "lhm_cpu_temperature" in lowered:
            stype = "Temperature"
        elif "lhm_cpu_power" in lowered:
            stype = "Power"
        elif "lhm_motherboard_temperature" in lowered:
            stype = "Temperature"
        elif "lhm_motherboard_power" in lowered:
            stype = "Power"
        else:
            continue
        brace = stripped.find("{")
        end = stripped.rfind("}")
        if brace < 0 or end < 0 or end < brace:
            continue
        labels = dict(_PROM_LABEL_RE.findall(stripped[brace + 1 : end]))
        rest = stripped[end + 1 :].strip().split()
        if not rest:
            continue
        value = _parse_value(rest[0])
        if value is None:
            continue
        name = labels.get("sensorName") or ""
        hardware_id = labels.get("hardwareId") or ""
        sensor_id = labels.get("sensorId") or ""
        key = (stype, hardware_id, sensor_id or name)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "name": name,
                "sensor_type": stype,
                "value": value,
                "identifier": f"{hardware_id}{sensor_id}",
                "parent": labels.get("hardwareName") or hardware_id,
            }
        )
    return rows


def fetch_lhm_http_rows(
    *,
    opener: Opener | None = None,
    now: float | None = None,
    config_text: str | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    """GET /data.json (then /metrics) from the LHM web server. Empty if it is off.

    Rows cache TTL is ``_ROWS_TTL_S`` (short — this is the sampling hot
    path). This is intentionally decoupled from the longer
    ``lhm_connection_status`` cache (``_STATUS_TTL_S``); see module
    docstring.

    As a side effect on every *real* probe (cache miss / ``force=True``),
    updates module-level ``_LAST_PROBE_REACHED`` / ``_LAST_PROBE_BASE`` /
    ``_LAST_PROBE_ERROR`` so ``lhm_connection_status`` can tell "the
    listener answered but had zero usable sensor rows" apart from
    "nothing answered at all" — both of which otherwise look identical
    from this function's ``[]`` return value alone.
    """
    global _CACHED_ROWS, _CACHED_BASE, _LHM_HTTP_LOGGED, _LHM_HTTP_OK_LOGGED, _LHM_HTTP_EMPTY_LOGGED
    global _LAST_PROBE_REACHED, _LAST_PROBE_BASE, _LAST_PROBE_ERROR
    monotonic = time.monotonic() if now is None else now
    with _LOCK:
        cached = _CACHED_ROWS
        if not force and cached is not None and monotonic - cached[0] < _ROWS_TTL_S:
            return list(cached[1])
        sticky_base = _CACHED_BASE
    port, bind_ip = _listener_from_config(config_text=config_text, now=monotonic)
    bases = iter_http_bases(port, bind_ip)
    if sticky_base:
        bases = [sticky_base] + [base for base in bases if base != sticky_base]
    rows, reached_base, reached, last_error = _probe_bases(opener, bases)
    with _LOCK:
        _CACHED_ROWS = (monotonic, list(rows))
        _LAST_PROBE_REACHED = reached
        _LAST_PROBE_BASE = reached_base
        _LAST_PROBE_ERROR = last_error
        if rows:
            _CACHED_BASE = reached_base
            if not _LHM_HTTP_OK_LOGGED:
                _LHM_HTTP_OK_LOGGED = True
                logger.info("LibreHardwareMonitor HTTP API connected at %s", reached_base)
        elif reached:
            if not _LHM_HTTP_EMPTY_LOGGED:
                _LHM_HTTP_EMPTY_LOGGED = True
                logger.info(
                    "LibreHardwareMonitor HTTP API reachable at %s but returned no "
                    "usable sensor rows (File \u2192 Hardware must include CPU).",
                    reached_base,
                )
        elif last_error is not None and not _LHM_HTTP_LOGGED:
            _LHM_HTTP_LOGGED = True
            logger.info(
                "LibreHardwareMonitor HTTP API not reachable at %s "
                "(keep Options → Remote Web Server → Run; "
                "File → Hardware must include CPU). Last error: %s",
                ", ".join(bases),
                last_error,
            )
    return list(rows)


def lhm_connection_status(
    *,
    opener: Opener | None = None,
    now: float | None = None,
    config_text: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Admin/diagnostics snapshot: is LHM HTTP reachable, where, and how fresh.

    Cache TTL is ``_STATUS_TTL_S`` (5-10s) — independent from the much
    shorter ``_ROWS_TTL_S`` used by ``fetch_lhm_http_rows``. Callers on the
    admin/request path (poll ~every 2s per admin_dashboard_spec.md §5)
    should call this with ``force=False``; that hits the cache without
    forcing a network round trip on every request.

    Single-flight: when the cache is stale, concurrent callers share one
    in-flight probe. Whoever gets there first does the real HTTP call;
    everyone else waiting on the lock reuses that result instead of firing
    a redundant request of their own — this holds regardless of each
    caller's own ``force`` flag.

    ``checked_at`` / ``last_success_at`` live in the same clock domain as
    the ``now`` parameter (``time.monotonic()`` unless a caller injects a
    deterministic value for tests). Callers that need wall-clock epoch
    seconds convert at the API layer, matching the
    ``occurredAt = time.time() - (time.monotonic() - mono)`` pattern used
    elsewhere for admin payload clocks (see admin_dashboard_spec.md §5).

    Returns a dict with (snake_case, matching the rest of this module):
    ``reachable`` (bool), ``base_url`` (str | None), ``sensor_rows`` (int),
    ``status`` (``unreachable`` | ``reachable_empty`` | ``connected`` |
    ``error``), ``prerequisite_for`` (list[str]), ``checked_at`` (float),
    ``last_success_at`` (float | None), ``stale`` (bool),
    ``error_code`` (str | None).
    """
    monotonic = time.monotonic() if now is None else now
    with _LOCK:
        cached = _CACHED_STATUS
        epoch = _STATUS_EPOCH
    if not force:
        fresh = _status_if_fresh(cached, monotonic)
        if fresh is not None:
            return fresh
    with _STATUS_LOCK:
        with _LOCK:
            latest = _CACHED_STATUS
            latest_epoch = _STATUS_EPOCH
        refreshed_elsewhere = latest_epoch != epoch
        if refreshed_elsewhere:
            fresh = _status_if_fresh(latest, monotonic)
            if fresh is not None:
                return fresh
        if not force:
            fresh = _status_if_fresh(latest, monotonic)
            if fresh is not None:
                return fresh
        computed = _probe_connection_status(
            opener=opener, monotonic=monotonic, config_text=config_text, force=force
        )
        return _copy_status(computed)


def reset_lhm_http_state() -> None:
    """Test helper: clear every module-level cache/dedupe flag (rows, status, config)."""
    global _CACHED_ROWS, _CACHED_BASE, _CACHED_CONFIG
    global _LHM_HTTP_LOGGED, _LHM_HTTP_OK_LOGGED, _LHM_HTTP_EMPTY_LOGGED
    global _LAST_PROBE_REACHED, _LAST_PROBE_BASE, _LAST_PROBE_ERROR, _LAST_SUCCESS_AT
    global _CACHED_STATUS, _STATUS_EPOCH
    with _LOCK:
        _CACHED_ROWS = None
        _CACHED_BASE = None
        _CACHED_CONFIG = None
        _LHM_HTTP_LOGGED = False
        _LHM_HTTP_OK_LOGGED = False
        _LHM_HTTP_EMPTY_LOGGED = False
        _LAST_PROBE_REACHED = False
        _LAST_PROBE_BASE = None
        _LAST_PROBE_ERROR = None
        _LAST_SUCCESS_AT = None
        _CACHED_STATUS = None
        _STATUS_EPOCH = 0


def _status_if_fresh(status: dict[str, Any] | None, monotonic: float) -> dict[str, Any] | None:
    """Return a safe copy of ``status`` if within TTL, else ``None``."""
    if status is None:
        return None
    checked_at = float(status["checked_at"])
    if monotonic - checked_at >= _STATUS_TTL_S:
        return None
    return _copy_status(status)


def _copy_status(status: dict[str, Any]) -> dict[str, Any]:
    payload = dict(status)
    payload["prerequisite_for"] = list(status["prerequisite_for"])
    return payload


def _probe_connection_status(
    *,
    opener: Opener | None,
    monotonic: float,
    config_text: str | None,
    force: bool,
) -> dict[str, Any]:
    global _CACHED_STATUS, _STATUS_EPOCH
    try:
        rows = fetch_lhm_http_rows(
            opener=opener, now=monotonic, config_text=config_text, force=force
        )
    except Exception as exc:
        # fetch_lhm_http_rows is already fail-soft (catches its own network
        # errors); this is belt-and-suspenders so a status probe can never
        # crash the admin/request path. Fall back to the last known-good
        # snapshot (if any) marked stale rather than losing state entirely.
        logger.debug("LHM connection status probe raised unexpectedly", exc_info=True)
        with _LOCK:
            previous = _CACHED_STATUS
        payload = _build_status(
            reachable=False,
            base=previous.get("base_url") if previous else None,
            sensor_rows=int(previous.get("sensor_rows") or 0) if previous else 0,
            error=exc,
            monotonic=monotonic,
            stale=previous is not None,
            status_override="error",
        )
        with _LOCK:
            _CACHED_STATUS = payload
            _STATUS_EPOCH += 1
        return payload

    with _LOCK:
        reached = _LAST_PROBE_REACHED
        base = _LAST_PROBE_BASE or _CACHED_BASE
        error = _LAST_PROBE_ERROR
    reachable = bool(rows) or reached
    payload = _build_status(
        reachable=reachable,
        base=base,
        sensor_rows=len(rows),
        error=(None if reachable else error),
        monotonic=monotonic,
        stale=False,
    )
    with _LOCK:
        _CACHED_STATUS = payload
        _STATUS_EPOCH += 1
    return payload


def _build_status(
    *,
    reachable: bool,
    base: str | None,
    sensor_rows: int,
    error: Exception | None,
    monotonic: float,
    stale: bool,
    status_override: str | None = None,
) -> dict[str, Any]:
    global _LAST_SUCCESS_AT
    if status_override is not None:
        status = status_override
    elif reachable:
        status = "connected" if sensor_rows > 0 else "reachable_empty"
    else:
        status = "unreachable"
    if reachable:
        with _LOCK:
            _LAST_SUCCESS_AT = monotonic
    with _LOCK:
        last_success_at = _LAST_SUCCESS_AT
    return {
        "reachable": reachable,
        "base_url": base,
        "sensor_rows": sensor_rows,
        "status": status,
        "prerequisite_for": ["sysinfo.cpu_package"],
        "checked_at": monotonic,
        "last_success_at": last_success_at,
        "stale": stale,
        "error_code": None if reachable else _error_code_for(error),
    }


def _error_code_for(error: Exception | None) -> str | None:
    if error is None:
        return None
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, urllib.error.HTTPError):
        return "http_error"
    if isinstance(error, urllib.error.URLError):
        return "connection_failed"
    if isinstance(error, http.client.HTTPException):
        return "http_error"
    if isinstance(error, (json.JSONDecodeError, ValueError)):
        return "invalid_response"
    if isinstance(error, OSError):
        return "connection_failed"
    return "unknown_error"


def _probe_bases(
    open_fn: Opener | None, bases: list[str]
) -> tuple[list[dict[str, Any]], str | None, bool, Exception | None]:
    """Try each candidate base URL in order. Returns (rows, base_used, reached, last_error).

    ``reached`` is True as soon as *any* base returns a parseable HTTP
    response, even one with zero usable sensor rows — this is what lets
    ``lhm_connection_status`` distinguish "reachable_empty" from a listener
    that never answered.
    """
    last_error: Exception | None = None
    reached_base: str | None = None
    for base in bases:
        rows, reached, error = _probe_one_base(open_fn, base)
        if error is not None:
            last_error = error
        if reached and reached_base is None:
            reached_base = base
        if rows:
            return rows, base, True, None
    return [], reached_base, reached_base is not None, last_error


def _probe_one_base(
    open_fn: Opener | None, base: str
) -> tuple[list[dict[str, Any]], bool, Exception | None]:
    """GET /data.json then /metrics for one origin. Never raises."""
    reached = False
    last_error: Exception | None = None
    attempts: tuple[tuple[str, Callable[[Any], list[dict[str, Any]]]], ...] = (
        (f"{base}/data.json", parse_lhm_data_json),
        (f"{base}/metrics", parse_lhm_prometheus),
    )
    for url, parser in attempts:
        try:
            rows = _read_endpoint(open_fn, url, parser)
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
            ValueError,
            http.client.HTTPException,
        ) as exc:
            last_error = exc
            continue
        reached = True
        if rows:
            return rows, True, None
    return [], reached, (None if reached else last_error)


def _listener_from_config(*, config_text: str | None, now: float) -> tuple[int, str | None]:
    global _CACHED_CONFIG
    if config_text is not None:
        parsed = parse_lhm_config(config_text)
        return int(parsed["port"]), parsed.get("ip")
    with _LOCK:
        cached = _CACHED_CONFIG
        if cached is not None and now - cached[0] < _CONFIG_TTL_S:
            return cached[1], cached[2]
    port, bind_ip = _DEFAULT_PORT, None
    for path in _lhm_config_paths():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parsed = parse_lhm_config(text)
        port = int(parsed["port"])
        bind_ip = parsed.get("ip")
        break
    with _LOCK:
        _CACHED_CONFIG = (now, port, bind_ip)
    return port, bind_ip


def _lhm_config_paths() -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path
        if resolved in seen:
            return
        seen.add(resolved)
        paths.append(resolved)

    if sys.platform == "win32":
        try:
            import psutil
        except ImportError:
            pass
        else:
            try:
                for proc in psutil.process_iter(["name", "exe"]):
                    name = str(proc.info.get("name") or "").lower()
                    if name != "librehardwaremonitor.exe":
                        continue
                    exe = proc.info.get("exe")
                    if not exe:
                        continue
                    exe_path = Path(str(exe))
                    add(exe_path.with_suffix(".config"))
                    add(exe_path.parent / "LibreHardwareMonitor.config")
            except Exception:
                logger.debug("LHM process scan failed", exc_info=True)
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app = os.environ.get("LOCALAPPDATA", "")
        roots = [
            Path(program_files) / "LibreHardwareMonitor",
            Path(program_files_x86) / "LibreHardwareMonitor",
            Path(program_files) / "Libre Hardware Monitor",
            Path(program_files_x86) / "Libre Hardware Monitor",
        ]
        if local_app:
            roots.append(Path(local_app) / "LibreHardwareMonitor")
        for root in roots:
            add(root / "LibreHardwareMonitor.config")
            add(root / "LibreHardwareMonitor.exe.config")
    return paths


def _read_endpoint(
    open_fn: Opener | None, url: str, parser: Callable[[Any], list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    if not is_allowed_lhm_url(url):
        raise ValueError(f"refusing non-local LHM URL {url}")
    if open_fn is not None:
        request = urllib.request.Request(url, headers=_HEADERS, method="GET")
        with open_fn(request, timeout=_HTTP_TIMEOUT_S) as resp:
            raw = resp.read()
    else:
        raw = _http_get(url)
    if isinstance(raw, str):
        body = raw
    else:
        body = _decode_body(raw)
    if url.endswith("metrics"):
        payload: Any = body
    else:
        payload = json.loads(body)
    return parser(payload)


def _http_get(url: str) -> bytes:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = int(parsed.port or _DEFAULT_PORT)
    path = parsed.path or "/"
    conn = http.client.HTTPConnection(host, port, timeout=_HTTP_TIMEOUT_S)
    try:
        conn.request("GET", path, headers=_HEADERS)
        resp = conn.getresponse()
        data = resp.read()
        if resp.status >= 400:
            raise urllib.error.URLError(f"HTTP {resp.status} {resp.reason} for {url}")
        return data
    finally:
        conn.close()


def _decode_body(raw: bytes) -> str:
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def _walk(node: dict[str, Any], rows: list[dict[str, Any]], parent: str, hardware: str) -> None:
    text = str(node.get("Text") or "")
    hardware_id = str(node.get("HardwareId") or "")
    sensor_id = str(node.get("SensorId") or "")
    typ = str(node.get("Type") or "")
    value = _parse_value(
        node.get("RawValue") if node.get("RawValue") not in (None, "") else node.get("Value")
    )
    next_hardware = hardware
    if hardware_id:
        next_hardware = f"{hardware_id} {text}".strip()
    elif not typ and text and node.get("Children"):
        next_hardware = f"{hardware} {text}".strip()
    next_parent = hardware_id or parent or next_hardware
    if typ and value is not None:
        rows.append(
            {
                "name": text,
                "sensor_type": typ,
                "value": value,
                "identifier": sensor_id or hardware_id,
                "parent": next_parent,
            }
        )
    children = node.get("Children") or []
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                _walk(child, rows, next_parent, next_hardware)


def _parse_value(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        number = float(raw)
        if number != number:  # NaN
            return None
        return number
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
