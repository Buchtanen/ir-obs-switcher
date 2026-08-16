"""Single-instance guard based on HTTP listen address."""

from __future__ import annotations

import logging
import os
import socket
import time

logger = logging.getLogger(__name__)

# When respawning via POST /restart, parent may still hold the port briefly.
_RESTART_ENV_FLAG = "IRSWITCH_RESTARTING"
_RESTART_RETRY_SECONDS = 15.0
_RESTART_RETRY_INTERVAL = 0.2


class InstanceAlreadyRunningError(RuntimeError):
    """Raised when another process already holds http_host:http_port."""


def _probe_host(host: str) -> str:
    """Map wildcard bind addresses to a loopback probe target."""
    # Compare against INADDR_ANY / IPv6 any — not opening a public listener here.
    if host in ("0.0.0.0", "", "::", "[::]"):  # nosec B104
        return "127.0.0.1"
    return host


def _port_accepts_tcp(host: str, port: int, *, timeout: float = 0.5) -> bool:
    """Return True if something already accepts TCP on host:port."""
    probe = _probe_host(host)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((probe, port))
        except OSError:
            return False
    return True


def _can_bind_exclusively(host: str, port: int) -> bool:
    """
    Try an exclusive bind on host:port.

    Returns True if the address is free (bind succeeded), False if occupied.
    """
    # Empty host → same as INADDR_ANY for the temporary exclusivity probe only.
    bind_host = host if host else "0.0.0.0"  # nosec B104
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # Prefer exclusive ownership where supported (Windows).
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            sock.bind((bind_host, port))
        except OSError:
            return False
    return True


def _address_occupied(host: str, port: int) -> bool:
    occupied = _port_accepts_tcp(host, port)
    if not occupied:
        occupied = not _can_bind_exclusively(host, port)
    return occupied


def ensure_single_instance(host: str, port: int) -> None:
    """
    Ensure no other irswitch (or conflicting listener) holds http_host:http_port.

    Checks whether the address already accepts TCP; if not conclusive, attempts
    an exclusive bind. Raises InstanceAlreadyRunningError with a clear message.

    When ``IRSWITCH_RESTARTING=1`` (set by POST /restart spawn), only probes for
    an active listener (not exclusive bind). After the parent closes its socket,
    Windows ``TIME_WAIT`` + ``SO_EXCLUSIVEADDRUSE`` would otherwise look occupied
    and abort the handoff.
    """
    restarting = os.environ.get(_RESTART_ENV_FLAG) == "1"
    deadline = time.monotonic()
    if restarting:
        deadline += _RESTART_RETRY_SECONDS
        logger.info(
            "Restart handoff: waiting up to %.1fs for %s:%s listener to go away",
            _RESTART_RETRY_SECONDS,
            host,
            port,
        )

    while True:
        if restarting:
            occupied = _port_accepts_tcp(host, port)
        else:
            occupied = _address_occupied(host, port)

        if not occupied:
            # Drop handoff flag so later logic does not keep retrying forever.
            os.environ.pop(_RESTART_ENV_FLAG, None)
            return
        if time.monotonic() >= deadline:
            break
        time.sleep(_RESTART_RETRY_INTERVAL)

    raise InstanceAlreadyRunningError(
        f"Another irswitch instance appears to be running "
        f"(address {host}:{port} is already in use). "
        f"Stop the existing process or change app.http_port in config.ini. "
        f"Exit code 2."
    )
