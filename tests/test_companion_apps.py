from types import SimpleNamespace
from unittest.mock import patch

import psutil
import pytest

from irswitch.system.companion_apps import detect_companion_apps


def test_known_apps_use_exact_process_names_in_one_scan():
    names = [
        "dre.EXE",
        "MarvinsAIRARefactored.exe",
        "SimHubWPF.exe",
        "CAMMUS.exe",
        "Trading Paints.exe",
        "VirtualDesktop.Streamer.exe",
        "iRacingUI.exe",
    ]
    with patch.object(
        psutil,
        "process_iter",
        return_value=iter(SimpleNamespace(info={"name": name}) for name in names),
    ) as scan:
        result = detect_companion_apps()
    assert all(
        result[key] is True
        for key in (
            "dre",
            "maira",
            "simhub",
            "cammus",
            "trading_paints",
            "virtual_desktop",
            "iracing_ui",
        )
    )
    scan.assert_called_once_with(["name"], ad_value=None)


def test_helpers_and_simulator_are_not_application_presence():
    names = [
        "DRECrashHandler.exe",
        "CammusProtectProcess.exe",
        "VirtualDesktop.Service.exe",
        "not-SimHubWPF.exe",
        "iRacingSim64DX11.exe",
    ]
    with patch.object(
        psutil,
        "process_iter",
        return_value=iter(SimpleNamespace(info={"name": name}) for name in names),
    ):
        result = detect_companion_apps()
    assert all(
        result[key] is False
        for key in (
            "dre",
            "maira",
            "simhub",
            "cammus",
            "trading_paints",
            "virtual_desktop",
            "iracing_ui",
        )
    )


def test_incomplete_scan_keeps_detected_apps_and_unknown_absence():
    with patch.object(
        psutil,
        "process_iter",
        return_value=iter(
            [SimpleNamespace(info={"name": "DRE.exe"}), SimpleNamespace(info={"name": None})]
        ),
    ):
        result = detect_companion_apps()
    assert result["dre"] is True
    assert result["simhub"] is None


def test_failed_scan_cannot_report_absence():
    with patch.object(psutil, "process_iter", side_effect=psutil.AccessDenied()):
        assert all(value is None for value in detect_companion_apps().values())


def test_requirement_config_is_persisted_live_and_only_affects_advisory(tmp_path, monkeypatch):
    from test_overlay_config import _minimal_ini

    from irswitch.config import AppConfig
    from irswitch.config_reload import classify_reload_diff
    from irswitch.overlay.config_io import apply_overlay_values
    from irswitch.server import admin

    path = _minimal_ini(tmp_path)
    before = AppConfig.from_file(path)
    assert all(before.companion_required.values())
    apply_overlay_values(
        path, {"companion_apps.dre": False, "companion_apps.virtual_desktop": False}
    )
    after = AppConfig.from_file(path)
    assert after.companion_required["dre"] is False
    assert after.companion_required["maira"] is True
    live, restart = classify_reload_diff(before, after)
    assert set(live) == {"companion_apps.dre", "companion_apps.virtual_desktop"}
    assert restart == []
    monkeypatch.setattr(admin, "_app_config", lambda: before)
    old = admin.build_admin_status(companion_apps={"dre": False})
    monkeypatch.setattr(admin, "_app_config", lambda: after)
    new = admin.build_admin_status(companion_apps={"dre": False})
    assert new["companionApps"][0] == {
        "id": "dre",
        "label": "DRE",
        "running": False,
        "required": False,
    }
    assert old["health"] == new["health"]
    assert old["switcher"] == new["switcher"]
    assert old["features"] == new["features"]


@pytest.mark.asyncio
async def test_requirement_http_roundtrip(tmp_path, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    from test_overlay_config import _minimal_ini

    from irswitch.config import AppConfig
    from irswitch.server import api
    from irswitch.server.app_keys import APP_CONFIG_PATH

    path = _minimal_ini(tmp_path)
    monkeypatch.setattr(api, "_config_container", [AppConfig.from_file(path)])
    app = api.create_app()
    app[APP_CONFIG_PATH] = path
    async with TestClient(TestServer(app)) as client:
        initial = await (await client.get("/api/config")).json()
        fields = [row for row in initial["schema"] if row["section"] == "companion_apps"]
        assert len(fields) == 6 and all(row["live"] for row in fields)
        response = await client.put(
            "/api/config",
            json={"values": {"companion_apps.dre": False}},
            headers={"X-Requested-With": "irswitch"},
        )
        assert response.status == 200
        assert (await response.json())["applied_live"] == ["companion_apps.dre"]
        saved = await (await client.get("/api/config")).json()
        assert saved["overlay"]["companion_apps.dre"] is False
        status = await (await client.get("/api/admin/status")).json()
        assert status["companionApps"][0]["required"] is False
    assert AppConfig.from_file(path).companion_required["dre"] is False
