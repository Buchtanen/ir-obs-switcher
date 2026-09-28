from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import psutil
import pytest

from irswitch.system.iracing_ui import detect_iracing_ui


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["iRacingUI.exe"], True),
        (["IRACINGUI.EXE"], True),
        (["iRacingService64.exe", "iRacingSim64DX11.exe"], False),
        (["not-iRacingUI.exe", "iracing-ini-guard-cli.exe"], False),
        ([], False),
        ([None], None),
        ([None, "iRacingUI.exe"], True),
    ],
)
def test_exact_launcher_presence(names, expected):
    processes = [SimpleNamespace(info={"name": name}) for name in names]
    with patch.object(psutil, "process_iter", return_value=iter(processes)):
        assert detect_iracing_ui() is expected


def test_process_enumeration_failure_is_unknown():
    with patch.object(psutil, "process_iter", side_effect=psutil.AccessDenied()):
        assert detect_iracing_ui() is None


def test_missing_optional_dependency_is_unknown():
    with patch.dict("sys.modules", {"psutil": None}):
        assert detect_iracing_ui() is None


def test_scan_budget_expiry_is_unknown():
    processes = [SimpleNamespace(info={"name": "unrelated.exe"})]
    with (
        patch.object(psutil, "process_iter", return_value=iter(processes)),
        patch("irswitch.system.companion_apps.time.monotonic", side_effect=[0.0, 1.1]),
    ):
        assert detect_iracing_ui() is None


def test_ui_hint_does_not_change_session_or_health(monkeypatch):
    from irswitch.server import admin

    monkeypatch.setattr(admin, "_switcher_state", lambda: SimpleNamespace(connected_iracing=False))
    absent = admin.build_admin_status(iracing_ui=False)
    present = admin.build_admin_status(iracing_ui=True)
    assert present["iracingUi"] == {"running": True}
    assert absent["iracingUi"] == {"running": False}
    assert present["switcher"]["connected_iracing"] is False
    assert present["health"] == absent["health"]
    assert present["switcher"] == absent["switcher"]
    assert present["features"] == absent["features"]


@pytest.mark.asyncio
async def test_http_projection_uses_worker_thread():
    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.server.api import create_app

    with (
        patch("irswitch.server.admin._probe_lhm", new=AsyncMock(return_value={})),
        patch(
            "irswitch.server.admin.asyncio.to_thread",
            new=AsyncMock(return_value={"iracing_ui": True}),
        ) as worker,
    ):
        async with TestClient(TestServer(create_app())) as client:
            response = await client.get("/api/admin/status")
            assert response.status == 200
            assert (await response.json())["iracingUi"] == {"running": True}
        from irswitch.system.companion_apps import detect_companion_apps

        worker.assert_awaited_once_with(detect_companion_apps)
