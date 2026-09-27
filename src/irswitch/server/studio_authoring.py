"""Local Studio revision transport. All disk/validation work runs off the loop."""

import asyncio
import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web

from irswitch.contracts.runtime_catalog import runtime_definition_status
from irswitch.contracts.studio_definitions import (
    MAX_DOCUMENT_BYTES,
    DefinitionError,
    DefinitionStore,
    RevisionConflict,
    compile_document,
    default_document,
)
from irswitch.server.app_keys import APP_CONFIG_PATH

APP_STUDIO_STORE: web.AppKey[DefinitionStore] = web.AppKey("studio_definition_store")


def store_for(request: web.Request) -> DefinitionStore | None:
    explicit = request.app.get(APP_STUDIO_STORE)
    path = request.app.get(APP_CONFIG_PATH)
    return (
        explicit
        if explicit is not None
        else (
            DefinitionStore(Path(path).resolve().with_name("studio-definitions.json"))
            if path
            else None
        )
    )


async def write_body(request: web.Request) -> dict:
    try:
        host = urlsplit(f"http://{request.host}").hostname
        local_host = host == "localhost" or bool(host and ipaddress.ip_address(host).is_loopback)
        if not local_host or not ipaddress.ip_address(request.remote or "").is_loopback:
            raise ValueError
    except ValueError:
        raise web.HTTPForbidden(reason="Loopback required") from None
    if request.headers.get("X-Requested-With") != "irswitch":
        raise web.HTTPForbidden(reason="CSRF header required")
    if request.headers.get("Origin") not in (None, f"{request.scheme}://{request.host}"):
        raise web.HTTPForbidden(reason="Same origin required")
    if request.content_type != "application/json":
        raise DefinitionError("JSON required")
    if request.content_length is not None and request.content_length > MAX_DOCUMENT_BYTES:
        raise DefinitionError("Request too large")

    async def bounded_read():
        raw = bytearray()
        async for chunk in request.content.iter_chunked(8192):
            raw.extend(chunk)
            if len(raw) > MAX_DOCUMENT_BYTES:
                raise DefinitionError("Request too large")
        return raw

    try:
        raw = await asyncio.wait_for(bounded_read(), timeout=5)
    except TimeoutError as exc:
        raise DefinitionError("Request body timeout") from exc
    try:
        value = json.loads(raw)
    except RecursionError as exc:
        raise DefinitionError("JSON nesting too deep") from exc
    if not isinstance(value, dict):
        raise DefinitionError("Expected object")
    return value


async def definitions(request: web.Request) -> web.Response:
    store = store_for(request)
    try:
        if request.method == "GET":
            if store is None:
                data = {
                    "baseRevision": 0,
                    "effectiveRevision": "builtin",
                    "pendingRevision": "builtin",
                    "revisions": [],
                    "builtin": await asyncio.to_thread(default_document),
                }
            else:
                data = await asyncio.to_thread(store.snapshot)
            return web.json_response(
                {**data, "available": store is not None, "runtime": runtime_definition_status()}
            )
        body = await write_body(request)
        action = request.match_info["action"]
        if action == "validate":
            if set(body) != {"document"}:
                raise DefinitionError("Expected document")
            catalog = await asyncio.to_thread(compile_document, body["document"])
            return web.json_response(
                {"valid": True, "stories": len(catalog.stories), "edges": len(catalog.edges)}
            )
        if store is None:
            return web.json_response({"error": "definition_store_unavailable"}, status=503)
        if action == "save" and set(body) == {"document", "baseRevision"}:
            data = await asyncio.to_thread(
                store.save, body["document"], base_revision=body["baseRevision"]
            )
        elif (
            action == "activate"
            and set(body) == {"revision", "baseRevision"}
            and isinstance(body["revision"], str)
        ):
            data = await asyncio.to_thread(
                store.select, body["revision"], base_revision=body["baseRevision"]
            )
        else:
            raise DefinitionError("Unknown action or fields")
        return web.json_response(
            {**data, "available": True, "runtime": runtime_definition_status()}
        )
    except RevisionConflict as exc:
        return web.json_response({"error": str(exc)}, status=409)
    except (DefinitionError, ValueError, KeyError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except OSError:
        return web.json_response(
            {"error": "Definition storage unavailable; last persisted state retained"}, status=503
        )


def register_studio_authoring_routes(app: web.Application) -> None:
    app.router.add_get("/api/studio/definitions", definitions)
    app.router.add_post("/api/studio/definitions/{action}", definitions)
