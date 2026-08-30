"""Server-side admin health aggregation."""

from __future__ import annotations

from irswitch.server.admin_health import evaluate_health


def test_health_ready_when_core_connected_and_no_warnings() -> None:
    payload = {
        "switcher": {"connected_iracing": True, "connected_obs": True},
        "extensions": {
            "ble": {"enabled": False, "status": "disabled"},
            "lhm": {"required": False, "status": "not_required", "detail": {}},
            "sysinfo": {"enabled": False, "status": "disabled"},
        },
        "features": {
            "overlay": {"enabled": True, "active": True, "status": "running"},
            "commentary": {"enabled": False, "status": "disabled"},
        },
    }
    health = evaluate_health(payload)
    assert health["ready"] is True
    assert health["blocking"] == []
    assert health["warnings"] == []


def test_health_blocking_for_disconnected_core() -> None:
    payload = {
        "switcher": {"connected_iracing": False, "connected_obs": False},
        "extensions": {},
        "features": {},
    }
    health = evaluate_health(payload)
    assert health["ready"] is False
    ids = {row["id"] for row in health["blocking"]}
    assert ids == {"iracing", "obs"}


def test_health_lhm_required_unhealthy_is_warning_not_blocking() -> None:
    payload = {
        "switcher": {"connected_iracing": True, "connected_obs": True},
        "extensions": {
            "lhm": {
                "required": True,
                "status": "unreachable",
                "detail": {"tip": "Start LibreHardwareMonitor"},
            },
            "sysinfo": {"enabled": True, "status": "degraded"},
        },
        "features": {"overlay": {"enabled": True, "active": True, "status": "running"}},
    }
    health = evaluate_health(payload)
    assert health["ready"] is True
    warn_ids = {row["id"] for row in health["warnings"]}
    assert "lhm" in warn_ids
    assert "sysinfo" in warn_ids
    assert health["blocking"] == []
