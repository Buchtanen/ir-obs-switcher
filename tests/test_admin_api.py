"""Admin dashboard API + pages."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from irswitch.commentary.director import CommentaryDirector, SpeakDecision
from irswitch.overlay.http import get_overlay_bus, reset_overlay_server
from irswitch.overlay.models import BioState, CPUState, SystemState
from irswitch.server.api import create_app, reset_state
from irswitch.server.event_log import EventLog, set_event_log


@pytest.fixture
def app() -> web.Application:
    reset_state()
    reset_overlay_server()
    set_event_log(EventLog(max_size=20))
    return create_app()


@pytest.mark.asyncio
async def test_admin_pages_and_static(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            for path in ("/admin", "/admin/extensions", "/admin/features", "/admin/activity"):
                page = await client.get(path)
                assert page.status == 200, path
                body = await page.text()
                assert "irswitch" in body.lower()
            css = await client.get("/admin/web/css/admin.css")
            assert css.status == 200
            js = await client.get("/admin/web/js/admin.js")
            assert js.status == 200
            assert "renderHealth" in await js.text()


@pytest.mark.asyncio
async def test_admin_status_extensions_and_features(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    bus = get_overlay_bus()
    bus.set_bio(
        BioState(
            connected=True,
            status="connected",
            device_name="HRM-Test",
            bpm=142,
            state="pushing",
        )
    )
    bus.set_system(SystemState(cpu=CPUState(load=40.0, temperature=71.0, power=88.0)))

    fake_lhm = {
        "reachable": True,
        "base_url": "http://127.0.0.1:8085",
        "sensor_rows": 12,
        "status": "connected",
        "prerequisite_for": ["sysinfo.cpu_package"],
        "checked_at": 100.0,
        "last_success_at": 99.0,
        "stale": False,
        "error_code": None,
    }

    with patch("irswitch.server.admin._probe_lhm", new=AsyncMock(return_value=fake_lhm)):
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                resp = await client.get("/api/admin/status")
                assert resp.status == 200
                body = await resp.json()
                assert body["schemaVersion"] == 1
                assert "version" in body
                assert "health" in body
                assert "ready" in body["health"]
                assert isinstance(body["health"]["blocking"], list)
                assert isinstance(body["health"]["warnings"], list)
                assert body["extensions"]["ble"]["active"] is True
                assert body["extensions"]["ble"]["severity"] == "ok"
                assert body["extensions"]["ble"]["detail"]["bpm"] == 142
                assert body["extensions"]["lhm"]["required"] is True
                assert body["extensions"]["lhm"]["requirementMode"] == "recommended"
                assert body["extensions"]["lhm"]["active"] is True
                assert body["extensions"]["lhm"]["detail"]["lastBaseUrl"] == "http://127.0.0.1:8085"
                assert body["extensions"]["lhm"]["detail"]["checkedAt"] is not None
                assert body["extensions"]["lhm"]["detail"]["lastSuccessAt"] is not None
                assert body["extensions"]["lhm"]["detail"]["stale"] is False
                assert body["extensions"]["lhm"]["detail"]["errorCode"] is None
                assert body["extensions"]["sysinfo"]["detail"]["lhmRequired"] is True
                assert "overlay" in body["features"]
                assert "commentary" in body["features"]
                assert "enabled" in body["features"]["commentary"]
                assert "available" in body["features"]["commentary"]
                assert "active" in body["features"]["commentary"]
                assert "eventEngine" in body["features"]


@pytest.mark.asyncio
async def test_commentary_ready_is_active_not_warn(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.overlay.settings import CommentarySettings, OverlaySettings
    from irswitch.server.api import set_app_config

    cfg = MagicMock()
    cfg.overlay = OverlaySettings(commentary=CommentarySettings(enabled=True))
    set_app_config(cfg)

    director = CommentaryDirector.from_defaults(settings=CommentarySettings(enabled=True))
    runtime = MagicMock()
    runtime.status_snapshot.return_value = {
        "enabled": True,
        "available": True,
        "running": True,
        "status": "running",
        "mode": None,
        "commentary": director.status_snapshot(0.0, enabled=True),
        "tape": {"enabled": True, "available": False, "pathOpen": False, "status": "idle"},
        "bio": {"enabled": True, "available": False, "status": "disconnected"},
        "system": {"enabled": True, "available": True, "status": "sampling"},
    }
    runtime.commentary = director

    with (
        patch("irswitch.server.admin.get_overlay_runtime", return_value=runtime),
        patch(
            "irswitch.server.admin._probe_lhm",
            new=AsyncMock(
                return_value={
                    "reachable": False,
                    "base_url": None,
                    "sensor_rows": 0,
                    "status": "unreachable",
                    "prerequisite_for": ["sysinfo.cpu_package"],
                    "checked_at": 1.0,
                    "last_success_at": None,
                    "stale": False,
                    "error_code": None,
                }
            ),
        ),
    ):
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                body = await (await client.get("/api/admin/status")).json()
                card = body["features"]["commentary"]
                assert card["enabled"] is True
                assert card["available"] is True
                assert card["active"] is True
                assert card["busy"] is False
                assert card["status"] == "ready"
                assert card["severity"] == "ok"
                warn_ids = {w["id"] for w in body["health"]["warnings"]}
                assert "lhm" in warn_ids


@pytest.mark.asyncio
async def test_admin_activity_uses_lifecycle_ring(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    log = EventLog(max_size=20)
    set_event_log(log)
    await log.add_event("scene_switch", "Scene switched to Race", {"scene": "Race"})

    bus = get_overlay_bus()
    assert bus.activity_log.add(
        {
            "type": "event",
            "eventType": "hunting",
            "phase": "ENTER",
            "monotonicMs": 100_000,
            "message": "Widget hunting (ENTER)",
        }
    )

    director = CommentaryDirector.from_defaults()
    director._decisions.append(
        SpeakDecision(
            action="spoken",
            reason="ok",
            event_type="OVERTAKE",
            node_id="overtake",
            text="He takes P5 from Rossi.",
            at=200.0,
        )
    )
    runtime = MagicMock()
    runtime.commentary = director
    runtime.status_snapshot.return_value = {}

    with patch("irswitch.server.admin.get_overlay_runtime", return_value=runtime):
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                resp = await client.get("/api/admin/activity?limit=20")
                assert resp.status == 200
                body = await resp.json()
                assert body["schemaVersion"] == 1
                sources = {item["source"] for item in body["items"]}
                assert "switcher" in sources
                assert "commentary" in sources
                assert "overlay" in sources
                for item in body["items"]:
                    assert item["occurredAt"] > 1_600_000_000
                    assert "dedupeKey" in item
                spoken = [i for i in body["items"] if i["kind"] == "spoken"]
                assert spoken and "Rossi" in spoken[0]["message"]
                overlay = [i for i in body["items"] if i["source"] == "overlay"]
                assert overlay and overlay[0]["kind"] == "hunting"
                assert overlay[0]["ephemeral"] is False
                assert overlay[0]["dedupeKey"].startswith("overlay:")


@pytest.mark.asyncio
async def test_admin_status_lhm_probe_is_cache_path(app: web.Application) -> None:
    """GET /api/admin/status must call lhm_connection_status with force=False."""
    from aiohttp.test_utils import TestClient, TestServer

    captured: dict[str, object] = {}

    def fake_status(*, force: bool = False, **_kwargs: object) -> dict:
        captured["force"] = force
        return {
            "reachable": False,
            "base_url": None,
            "sensor_rows": 0,
            "status": "unreachable",
            "prerequisite_for": ["sysinfo.cpu_package"],
            "checked_at": 1.0,
            "last_success_at": None,
            "stale": False,
            "error_code": None,
        }

    with patch("irswitch.system.lhm_http.lhm_connection_status", side_effect=fake_status):
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                resp = await client.get("/api/admin/status")
                assert resp.status == 200
                assert captured.get("force") is False


def test_lhm_connection_status_helper() -> None:
    from irswitch.system import lhm_http

    rows = [
        {
            "name": "CPU Package",
            "sensor_type": "Temperature",
            "value": 70.0,
            "identifier": "/amdcpu/0/temperature/2",
            "parent": "CPU",
        }
    ]

    def opener(req: object, timeout: float = 0) -> object:  # noqa: ARG001
        raise AssertionError("should use cache")

    with patch.object(lhm_http, "fetch_lhm_http_rows", return_value=rows) as mocked:
        status = lhm_http.lhm_connection_status(opener=opener, force=True)
        mocked.assert_called_once()
    assert status["reachable"] is True
    assert status["sensor_rows"] == 1
    assert status["status"] == "connected"
    assert "sysinfo.cpu_package" in status["prerequisite_for"]


def test_admin_module_avoids_foreign_private_attrs() -> None:
    """Slice 1.2: admin.py must not reach into foreign _-prefixed attrs."""
    import re
    from pathlib import Path

    text = Path("src/irswitch/server/admin.py").read_text(encoding="utf-8")
    # Match attribute access / bare names — not substrings of public getters.
    forbidden = (
        r"\b_busy_until\b",
        r"\b_tape\b",
        r"\b_decisions\b",
        r"(?<!get)\b_overlay_runtime\b",
        r"\b_current_state\b",
    )
    for pattern in forbidden:
        assert re.search(pattern, text) is None, f"forbidden pattern still in admin.py: {pattern}"
