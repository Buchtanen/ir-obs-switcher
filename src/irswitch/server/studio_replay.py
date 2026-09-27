"""Bounded fixtures through isolated existing replay harnesses; no live sinks."""

import asyncio
import hashlib
import json
from functools import lru_cache
from uuid import uuid4

from aiohttp import web

from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.contracts.studio_definitions import (
    DefinitionError,
    compile_document,
    default_document,
)
from irswitch.events.episode_registry import EpisodeRegistry
from irswitch.events.narrative_reducer_replay import capture_reducer_trace, command_from_dict
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.overlay.replay_input import ReplayInputRunner
from irswitch.server.studio_authoring import write_body

APP_REPLAY_LOCK: web.AppKey[asyncio.Lock] = web.AppKey("studio_replay_lock")


@lru_cache(maxsize=1)
def fixtures():
    return json.loads(packaged_schema_bytes("studio-replay-scenarios.json"))


def run_fixture(identifier: str, document=None) -> dict:
    # Each call owns fresh runtime, registry, clock input, manager and emitter state.
    run_id = str(uuid4())
    if identifier == "narrative_world":
        document = default_document() if document is None else document
        catalog = compile_document(document)
        registry = EpisodeRegistry(definition_catalog=catalog, definition_revision="replay")
        commands = tuple(
            command_from_dict(row)
            for row in json.loads(packaged_schema_bytes("studio-narrative-replay.json"))
        )
        trace = capture_reducer_trace(
            commands,
            runtime_factory=lambda: NarrativeRuntime(
                episode_registry=registry, definition_catalog=catalog
            ),
        )
        # Only synchronous reduce/drain: effect names are output evidence, never dispatched.
        outputs = [
            {"atMs": int(command.enqueued_mono_ms), **row}
            for command, row in zip(commands, trace.to_tape_rows(), strict=True)
        ]
        episodes = registry.studio_snapshot()
        deterministic = {
            "outputs": outputs,
            "episodes": episodes["items"],
            "history": episodes["history"],
        }
        duration = max((int(c.enqueued_mono_ms) for c in commands), default=0)
    else:
        if document is not None:
            raise DefinitionError("Narrative definitions apply only to narrative replay")
        fixture = fixtures().get(identifier)
        if fixture is None:
            raise DefinitionError("Unknown packaged fixture")
        result = ReplayInputRunner().run_fixture(fixture)
        outputs = [
            {"atMs": round(t * 1000), "eventType": kind, "phase": phase}
            for t, kind, phase in result.events
        ]
        deterministic = {"outputs": outputs}
        duration = round(max((tick["t"] for tick in fixture["ticks"]), default=0) * 1000)
    digest = hashlib.sha256(
        json.dumps(deterministic, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schemaVersion": "studio-replay/1",
        "runId": run_id,
        "fixture": identifier,
        "virtualDurationMs": duration,
        "outputHash": digest,
        **deterministic,
        "isolated": True,
        "effectsExecuted": False,
    }


async def replay(request: web.Request) -> web.Response:
    if request.method == "GET":
        available = await asyncio.to_thread(fixtures)
        return web.json_response(
            {
                "schemaVersion": "studio-replay/1",
                "fixtures": [
                    {"id": key, "name": row["name"], "domain": "overlay"}
                    for key, row in available.items()
                ]
                + [
                    {
                        "id": "narrative_world",
                        "name": "Narrative world / accepted context / shutdown",
                        "domain": "narrative",
                    }
                ],
            }
        )
    try:
        body = await write_body(request)
        if set(body) not in ({"fixture"}, {"fixture", "document"}) or not isinstance(
            body["fixture"], str
        ):
            raise DefinitionError("Expected fixture and optional narrative document")
        lock = request.app[APP_REPLAY_LOCK]
        if lock.locked():
            return web.json_response({"error": "replay_busy"}, status=409)
        async with lock:
            task = asyncio.create_task(
                asyncio.to_thread(run_fixture, body["fixture"], body.get("document"))
            )
            try:
                value = await asyncio.shield(task)
            except asyncio.CancelledError:
                await task  # keep capacity owned until the bounded fixture has stopped
                raise
        return web.json_response(value)
    except (DefinitionError, ValueError, KeyError, TypeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)


def register_studio_replay_routes(app: web.Application) -> None:
    app[APP_REPLAY_LOCK] = asyncio.Lock()
    app.router.add_get("/api/studio/replay", replay)
    app.router.add_post("/api/studio/replay", replay)
