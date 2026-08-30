"""LHM HTTP transport: connection-status cache/TTL, single-flight, SSRF regression.

Exclusive-file test suite for ``irswitch.system.lhm_http`` (P3 — see
docs/admin_parallel_implementation_plan.md). Does not touch
``system/provider.py`` or ``server/admin.py``.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error

from irswitch.system import lhm_http


class _FakeHttp:
    """Minimal stand-in for the context manager returned by ``opener(request, timeout=...)``."""

    def __init__(self, body: bytes | str) -> None:
        self._body = body.encode("utf-8") if isinstance(body, str) else body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeHttp:
        return self

    def __exit__(self, *args: object) -> None:
        return None


_CPU_PACKAGE_TREE = {
    "Text": "Sensor",
    "Children": [
        {
            "Text": "AMD Ryzen 9",
            "HardwareId": "/amdcpu/0",
            "Children": [
                {
                    "Text": "CPU Package",
                    "Value": "64.0 \u00b0C",
                    "SensorId": "/amdcpu/0/temperature/2",
                    "Type": "Temperature",
                    "Children": [],
                }
            ],
        }
    ],
}

_EMPTY_TREE = {"Text": "Sensor", "Children": []}


def _connected_opener(request: object, timeout: float = 0) -> _FakeHttp:  # noqa: ARG001
    return _FakeHttp(json.dumps(_CPU_PACKAGE_TREE))


def _reachable_empty_opener(request: object, timeout: float = 0) -> _FakeHttp:  # noqa: ARG001
    url = getattr(request, "full_url", "")
    if url.endswith("/data.json"):
        return _FakeHttp(json.dumps(_EMPTY_TREE))
    return _FakeHttp("")  # /metrics: no gauge lines, still a valid (empty) response


def _unreachable_opener(request: object, timeout: float = 0) -> _FakeHttp:  # noqa: ARG001
    raise urllib.error.URLError("connection refused")


def _assert_not_called_opener(request: object, timeout: float = 0) -> _FakeHttp:  # noqa: ARG001
    raise AssertionError("network should not be hit — expected a cache hit")


# --- SSRF allow-list regression (must stay unchanged; see admin_dashboard_spec.md §6) ---


def test_is_allowed_lhm_url_accepts_local_data_and_metrics_only() -> None:
    assert lhm_http.is_allowed_lhm_url("http://127.0.0.1:8085/data.json")
    assert lhm_http.is_allowed_lhm_url("http://127.0.0.1:8085/metrics")
    assert lhm_http.is_allowed_lhm_url("http://localhost:8085/")
    assert lhm_http.is_allowed_lhm_url("http://192.168.1.50:8085/data.json")
    assert lhm_http.is_allowed_lhm_url("http://[::1]:8085/data.json")


def test_is_allowed_lhm_url_rejects_non_local_and_unsafe_urls() -> None:
    # scheme
    assert not lhm_http.is_allowed_lhm_url("https://127.0.0.1:8085/data.json")
    assert not lhm_http.is_allowed_lhm_url("ftp://127.0.0.1:8085/data.json")
    # non-local host (public IP / DNS name)
    assert not lhm_http.is_allowed_lhm_url("http://example.com:8085/data.json")
    assert not lhm_http.is_allowed_lhm_url("http://8.8.8.8:8085/data.json")
    # disallowed path (SSRF via path traversal / unexpected endpoint)
    assert not lhm_http.is_allowed_lhm_url("http://127.0.0.1:8085/other")
    assert not lhm_http.is_allowed_lhm_url("http://127.0.0.1:8085/data.json/../../etc")
    # userinfo / query / fragment smuggling
    assert not lhm_http.is_allowed_lhm_url("http://user:pass@127.0.0.1:8085/data.json")
    assert not lhm_http.is_allowed_lhm_url("http://127.0.0.1:8085/data.json?x=1")
    assert not lhm_http.is_allowed_lhm_url("http://127.0.0.1:8085/data.json#frag")
    # missing/invalid port
    assert not lhm_http.is_allowed_lhm_url("http://127.0.0.1/data.json")


def test_is_local_lhm_host_regression() -> None:
    assert lhm_http.is_local_lhm_host("127.0.0.1")
    assert lhm_http.is_local_lhm_host("localhost")
    assert lhm_http.is_local_lhm_host("LOCALHOST")
    assert lhm_http.is_local_lhm_host("192.168.1.50")
    assert lhm_http.is_local_lhm_host("10.0.0.8")
    assert lhm_http.is_local_lhm_host("169.254.1.1")
    assert lhm_http.is_local_lhm_host("::1")
    assert not lhm_http.is_local_lhm_host("8.8.8.8")
    assert not lhm_http.is_local_lhm_host("example.com")
    assert not lhm_http.is_local_lhm_host("0.0.0.0")
    assert not lhm_http.is_local_lhm_host("+")
    assert not lhm_http.is_local_lhm_host("")


# --- connected / reachable_empty / unreachable distinction ---


def test_connection_status_connected_when_rows_present() -> None:
    lhm_http.reset_lhm_http_state()
    status = lhm_http.lhm_connection_status(
        opener=_connected_opener, now=100.0, config_text="", force=True
    )
    assert status["reachable"] is True
    assert status["sensor_rows"] == 1
    assert status["status"] == "connected"
    assert status["error_code"] is None
    assert status["checked_at"] == 100.0
    assert status["last_success_at"] == 100.0
    assert status["stale"] is False
    assert "sysinfo.cpu_package" in status["prerequisite_for"]


def test_connection_status_reachable_empty_when_host_answers_with_no_sensors() -> None:
    lhm_http.reset_lhm_http_state()
    status = lhm_http.lhm_connection_status(
        opener=_reachable_empty_opener, now=100.0, config_text="", force=True
    )
    assert status["reachable"] is True
    assert status["sensor_rows"] == 0
    assert status["status"] == "reachable_empty"
    assert status["error_code"] is None
    assert status["base_url"] is not None
    assert status["last_success_at"] == 100.0


def test_connection_status_unreachable_when_nothing_answers() -> None:
    lhm_http.reset_lhm_http_state()
    status = lhm_http.lhm_connection_status(
        opener=_unreachable_opener, now=100.0, config_text="", force=True
    )
    assert status["reachable"] is False
    assert status["sensor_rows"] == 0
    assert status["status"] == "unreachable"
    assert status["error_code"] == "connection_failed"
    assert status["base_url"] is None
    assert status["last_success_at"] is None


def test_connection_status_distinguishes_empty_from_unreachable() -> None:
    """The two failure modes must not collapse to the same status/reachable pair."""
    lhm_http.reset_lhm_http_state()
    unreachable = lhm_http.lhm_connection_status(
        opener=_unreachable_opener, now=100.0, config_text="", force=True
    )
    lhm_http.reset_lhm_http_state()
    empty = lhm_http.lhm_connection_status(
        opener=_reachable_empty_opener, now=100.0, config_text="", force=True
    )
    assert unreachable["status"] != empty["status"]
    assert unreachable["reachable"] is False
    assert empty["reachable"] is True


# --- status cache TTL (5-10s) decoupled from the rows TTL + force semantics ---


def test_connection_status_force_false_hits_cache_without_network() -> None:
    lhm_http.reset_lhm_http_state()
    first = lhm_http.lhm_connection_status(
        opener=_connected_opener, now=100.0, config_text="", force=True
    )
    # Well inside the 5-10s status TTL: force=False must not touch the network.
    second = lhm_http.lhm_connection_status(
        opener=_assert_not_called_opener, now=103.0, config_text="", force=False
    )
    assert second == first


def test_connection_status_cache_expires_after_ttl() -> None:
    lhm_http.reset_lhm_http_state()
    lhm_http.lhm_connection_status(opener=_connected_opener, now=100.0, config_text="", force=True)
    # Past the 10s upper bound of the documented TTL window: must reprobe.
    refreshed = lhm_http.lhm_connection_status(
        opener=_unreachable_opener, now=111.0, config_text="", force=False
    )
    assert refreshed["status"] == "unreachable"
    assert refreshed["checked_at"] == 111.0


def test_connection_status_force_true_always_reprobes() -> None:
    lhm_http.reset_lhm_http_state()
    first = lhm_http.lhm_connection_status(
        opener=_connected_opener, now=100.0, config_text="", force=True
    )
    second = lhm_http.lhm_connection_status(
        opener=_unreachable_opener, now=100.5, config_text="", force=True
    )
    assert first["status"] == "connected"
    assert second["status"] == "unreachable"
    assert second["checked_at"] == 100.5
    # last_success_at persists from the earlier successful probe (fail-soft observability).
    assert second["last_success_at"] == 100.0


def test_connection_status_returns_independent_copies() -> None:
    """Callers must not be able to mutate the shared cache via the returned dict."""
    lhm_http.reset_lhm_http_state()
    status = lhm_http.lhm_connection_status(
        opener=_connected_opener, now=100.0, config_text="", force=True
    )
    status["prerequisite_for"].append("tampered")
    again = lhm_http.lhm_connection_status(
        opener=_assert_not_called_opener, now=100.5, config_text="", force=False
    )
    assert "tampered" not in again["prerequisite_for"]


# --- single-flight: concurrent callers share one in-flight probe ---


def test_connection_status_single_flight_shares_one_probe() -> None:
    lhm_http.reset_lhm_http_state()
    call_count = {"n": 0}
    count_lock = threading.Lock()
    thread_count = 6
    barrier = threading.Barrier(thread_count)
    results: list[dict] = []
    results_lock = threading.Lock()

    def slow_opener(request: object, timeout: float = 0) -> _FakeHttp:  # noqa: ARG001
        with count_lock:
            call_count["n"] += 1
        time.sleep(0.15)
        return _FakeHttp(json.dumps(_CPU_PACKAGE_TREE))

    def worker() -> None:
        barrier.wait()
        result = lhm_http.lhm_connection_status(opener=slow_opener, config_text="", force=True)
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert call_count["n"] == 1, "single-flight must collapse concurrent probes into one"
    assert len(results) == thread_count
    for result in results:
        assert result["status"] == "connected"
        assert result["sensor_rows"] == 1


# --- fail-soft: unexpected exception during probing never crashes the caller ---


def test_connection_status_fail_soft_on_unexpected_exception(monkeypatch) -> None:
    lhm_http.reset_lhm_http_state()
    lhm_http.lhm_connection_status(opener=_connected_opener, now=100.0, config_text="", force=True)

    def _boom(**_kwargs: object) -> list[dict]:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(lhm_http, "fetch_lhm_http_rows", _boom)
    status = lhm_http.lhm_connection_status(now=200.0, config_text="", force=True)

    assert status["status"] == "error"
    assert status["reachable"] is False
    assert status["error_code"] is not None
    assert status["stale"] is True
    # Falls back to the last known-good snapshot's sensor_rows/base_url.
    assert status["sensor_rows"] == 1
    assert status["last_success_at"] == 100.0


# --- reset helper ---


def test_reset_lhm_http_state_clears_caches() -> None:
    lhm_http.reset_lhm_http_state()
    lhm_http.lhm_connection_status(opener=_connected_opener, now=100.0, config_text="", force=True)
    assert lhm_http._CACHED_STATUS is not None  # noqa: SLF001

    lhm_http.reset_lhm_http_state()
    assert lhm_http._CACHED_STATUS is None  # noqa: SLF001
    assert lhm_http._CACHED_ROWS is None  # noqa: SLF001
    assert lhm_http._CACHED_BASE is None  # noqa: SLF001
    assert lhm_http._LAST_SUCCESS_AT is None  # noqa: SLF001

    # A fresh probe after reset must not be treated as a cache hit — the
    # opener below is actually invoked (it wasn't, before the reset).
    status = lhm_http.lhm_connection_status(
        opener=_unreachable_opener, now=100.0, config_text="", force=False
    )
    assert status["status"] == "unreachable"


# --- backward-compatible dict shape consumed by server/admin.py (not touched here) ---


def test_lhm_connection_status_keeps_keys_consumed_by_admin() -> None:
    lhm_http.reset_lhm_http_state()
    status = lhm_http.lhm_connection_status(
        opener=_connected_opener, now=100.0, config_text="", force=True
    )
    for key in ("reachable", "base_url", "sensor_rows", "status", "prerequisite_for"):
        assert key in status
    for key in ("checked_at", "last_success_at", "stale", "error_code"):
        assert key in status


def test_fetch_lhm_http_rows_unaffected_by_status_cache() -> None:
    """fetch_lhm_http_rows keeps its own short TTL, independent of the status cache."""
    lhm_http.reset_lhm_http_state()
    rows = lhm_http.fetch_lhm_http_rows(
        opener=_connected_opener, now=50.0, config_text="", force=True
    )
    assert len(rows) == 1
    # Within the short rows TTL, a second call must not touch the network either.
    cached_rows = lhm_http.fetch_lhm_http_rows(
        opener=_assert_not_called_opener, now=50.5, config_text="", force=False
    )
    assert cached_rows == rows
