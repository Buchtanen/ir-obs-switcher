import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from irswitch.contracts.studio_definitions import DefinitionStore, default_document
from irswitch.server.studio_authoring import APP_STUDIO_STORE, register_studio_authoring_routes


@pytest.mark.asyncio
async def test_store_transport_conflicts_and_same_origin(tmp_path):
    app = web.Application()
    app[APP_STUDIO_STORE] = DefinitionStore(tmp_path / "defs.json")
    register_studio_authoring_routes(app)
    async with TestClient(TestServer(app)) as client:
        body = {"document": default_document(), "baseRevision": 0}
        assert (await client.post("/api/studio/definitions/save", json=body)).status == 403
        headers = {"X-Requested-With": "irswitch", "Origin": "https://evil.invalid"}
        assert (
            await client.post("/api/studio/definitions/save", json=body, headers=headers)
        ).status == 403
        headers.pop("Origin")
        deep = "[" * 2000 + "0" + "]" * 2000
        response = await client.post(
            "/api/studio/definitions/save",
            data=deep,
            headers={**headers, "Content-Type": "application/json"},
        )
        assert response.status == 400
        assert not app[APP_STUDIO_STORE].path.exists()
        assert (
            await client.post("/api/studio/definitions/save", json=body, headers=headers)
        ).status == 200
        assert (
            await client.post("/api/studio/definitions/save", json=body, headers=headers)
        ).status == 409
        state = await (await client.get("/api/studio/definitions")).json()
        assert state["effectiveRevision"] == "builtin"
        revision = state["revisions"][0]["id"]
        response = await client.post(
            "/api/studio/definitions/activate",
            json={"revision": revision, "baseRevision": 1},
            headers=headers,
        )
        assert response.status == 200
        assert (await response.json())["pendingRevision"] == revision
        assert (
            await client.post(
                "/api/studio/definitions/validate", json={"document": {}}, headers=headers
            )
        ).status == 400


@pytest.mark.asyncio
async def test_replay_is_deterministic_and_does_not_attach_live_provider():
    from irswitch.events.narrative_runtime_http import get_narrative_runtime
    from irswitch.server.studio_replay import register_studio_replay_routes

    app = web.Application()
    register_studio_replay_routes(app)
    previous = get_narrative_runtime()
    async with TestClient(TestServer(app)) as client:
        fixtures = await (await client.get("/api/studio/replay")).json()
        assert len(fixtures["fixtures"]) == 17
        for fixture in fixtures["fixtures"]:
            body = {"fixture": fixture["id"]}
            if fixture["id"] == "narrative_world":
                body["document"] = default_document()
            a = await (
                await client.post(
                    "/api/studio/replay", json=body, headers={"X-Requested-With": "irswitch"}
                )
            ).json()
            b = await (
                await client.post(
                    "/api/studio/replay", json=body, headers={"X-Requested-With": "irswitch"}
                )
            ).json()
            assert a["runId"] != b["runId"]
            assert a["outputHash"] == b["outputHash"]
            assert a["outputs"] == b["outputs"]
        assert get_narrative_runtime() is previous


def test_replay_has_no_network_or_effect_dispatch(monkeypatch):
    import socket

    from irswitch.events.narrative_runtime import NarrativeRuntime
    from irswitch.server.studio_replay import fixtures, run_fixture

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Replay attempted an external effect")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(NarrativeRuntime, "apply_effects", forbidden)
    for identifier in (*fixtures(), "narrative_world"):
        result = run_fixture(identifier)
        assert result["effectsExecuted"] is False
