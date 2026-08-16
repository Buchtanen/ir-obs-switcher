"""Tests for single-instance HTTP port guard."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from irswitch.util.single_instance import (
    InstanceAlreadyRunningError,
    _can_bind_exclusively,
    _port_accepts_tcp,
    ensure_single_instance,
)


def _free_port() -> int:
    """Ask the OS for an unused ephemeral port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_ensure_single_instance_allows_free_port() -> None:
    """Free port must not raise."""
    port = _free_port()
    ensure_single_instance("127.0.0.1", port)


def test_ensure_single_instance_rejects_occupied_port() -> None:
    """Listening socket on the same host:port must raise with a clear message."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        host, port = listener.getsockname()[:2]

        with pytest.raises(InstanceAlreadyRunningError) as exc_info:
            ensure_single_instance(host, port)

        message = str(exc_info.value)
        assert str(port) in message
        assert "already in use" in message.lower()
        assert "http_port" in message or "config.ini" in message


def test_port_accepts_tcp_true_when_listening() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        _, port = listener.getsockname()
        assert _port_accepts_tcp("127.0.0.1", port) is True


def test_port_accepts_tcp_false_when_free() -> None:
    port = _free_port()
    assert _port_accepts_tcp("127.0.0.1", port) is False


def test_can_bind_exclusively_false_when_occupied() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        _, port = listener.getsockname()
        assert _can_bind_exclusively("127.0.0.1", port) is False


def test_can_bind_exclusively_true_when_free() -> None:
    port = _free_port()
    assert _can_bind_exclusively("127.0.0.1", port) is True


def test_ensure_single_instance_uses_bind_fallback_when_connect_misses() -> None:
    """If connect says free but exclusive bind fails, still treat as occupied."""
    with (
        patch("irswitch.util.single_instance._port_accepts_tcp", return_value=False),
        patch("irswitch.util.single_instance._can_bind_exclusively", return_value=False),
    ):
        with pytest.raises(InstanceAlreadyRunningError):
            ensure_single_instance("127.0.0.1", 17321)
