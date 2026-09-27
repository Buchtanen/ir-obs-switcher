"""Versioned Studio read projections; providers own their state and history."""

import asyncio
import json
from dataclasses import asdict

from aiohttp import web

from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.contracts.runtime_catalog import load_runtime_catalog as load_narrative_catalog
from irswitch.contracts.runtime_catalog import runtime_definition_status
from irswitch.events.event_catalog import load_event_catalog
from irswitch.events.narrative_runtime_http import APP_NARRATIVE_RUNTIME, get_narrative_runtime


def _catalog_response() -> web.Response:
    loaded = load_narrative_catalog()
    if loaded.catalog is None:
        return web.json_response({"error": "catalog_unavailable"}, status=503)
    registry = json.loads(packaged_schema_bytes("freeze-registry.json"))
    graph = json.loads(packaged_schema_bytes("successor-graph.json"))
    return web.json_response(
        {
            "schemaVersion": "studio-catalog/1",
            "narrative": asdict(loaded.catalog),
            "definitions": runtime_definition_status(),
            "events": registry["eventIdentifiers"],
            "guards": graph["guardProfiles"],
            "overlay": load_event_catalog(),
            "capabilities": {
                "liveNodeActivity": False,
                "configWriter": "/api/config",
                "definitionActivation": "next_startup",
                "layout": "browser_only",
            },
        }
    )


async def catalog(_request: web.Request) -> web.Response:
    try:
        return await asyncio.to_thread(_catalog_response)
    except (ValueError, OSError, RuntimeError):
        return web.json_response({"error": "catalog_unavailable"}, status=503)


async def episodes(request: web.Request) -> web.Response:
    try:
        limit = int(request.query.get("limit", "50"))
        offset = int(request.query.get("offset", "0"))
        if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
            raise ValueError
    except ValueError:
        return web.json_response({"error": "invalid_pagination"}, status=400)
    provider = request.app.get(APP_NARRATIVE_RUNTIME) or get_narrative_runtime()
    snapshot = getattr(provider, "studio_episodes", None)
    if snapshot is None:
        return web.json_response(
            {
                "schemaVersion": "studio-episodes/1",
                "available": False,
                "runId": None,
                "items": [],
                "history": [],
                "total": None,
            }
        )
    try:
        data = snapshot(limit=limit, offset=offset)
    except Exception:
        return web.json_response({"error": "episode_provider_unavailable"}, status=503)
    requested_run = request.query.get("runId")
    if requested_run and requested_run != data.get("runId"):
        return web.json_response({"error": "run_changed", "runId": data.get("runId")}, status=409)
    return web.json_response(data)


def register_studio_data_routes(app: web.Application) -> None:
    app.router.add_get("/api/studio/catalog", catalog)
    app.router.add_get("/api/studio/episodes", episodes)
