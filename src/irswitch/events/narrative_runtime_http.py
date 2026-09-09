"""HTTP mount for NarrativeRuntime status projection (#284).

Exposes ``GET /api/commentary/runtime`` as the ``commentary-runtime/2`` subset
produced by ``project_runtime_status``. Optional ``APP_NARRATIVE_RUNTIME`` may
point at a library ``NarrativeRuntime`` (or duck with ``status()`` returning
``RuntimeStatus``). When absent, the handler projects a disabled library
snapshot.

This mount does not start the NarrativeRuntime actor loop, does not replace
``GET /api/commentary/status``, and does not activate live EventSubscription
cutover. Not exported from ``events/__init__.py``.
"""

from __future__ import annotations

import logging
from typing import Protocol

from aiohttp import web

from irswitch.contracts.primitives import ContractViolation
from irswitch.events.narrative_ingress import project_runtime_status
from irswitch.events.narrative_runtime import NarrativeRuntime, RuntimeStatus

logger = logging.getLogger(__name__)


class NarrativeRuntimeStatusProvider(Protocol):
    def status(self) -> RuntimeStatus: ...


APP_NARRATIVE_RUNTIME: web.AppKey[NarrativeRuntimeStatusProvider] = web.AppKey("narrative_runtime")


async def handle_commentary_runtime_status(request: web.Request) -> web.Response:
    """Return commentary-runtime/2 status subset for NarrativeRuntime."""
    provider = request.app.get(APP_NARRATIVE_RUNTIME)
    try:
        if provider is None:
            status = NarrativeRuntime().status()
        else:
            status = provider.status()
        payload = project_runtime_status(status)
    except ContractViolation as exc:
        logger.warning("narrative runtime status projection rejected: %s", exc)
        return web.json_response({"error": str(exc)}, status=500)
    except Exception as exc:
        logger.warning("narrative runtime status projection failed", exc_info=True)
        return web.json_response(
            {"error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )
    return web.json_response(payload)


def register_narrative_runtime_routes(app: web.Application) -> None:
    """Mount GET /api/commentary/runtime (additive; does not run the actor)."""
    app.router.add_get("/api/commentary/runtime", handle_commentary_runtime_status)


def attach_narrative_runtime(
    app: web.Application, runtime: NarrativeRuntimeStatusProvider | None
) -> None:
    """Attach or clear the optional status provider (tests / explicit cutover)."""
    if runtime is None:
        app.pop(APP_NARRATIVE_RUNTIME, None)
        return
    app[APP_NARRATIVE_RUNTIME] = runtime


__all__ = [
    "APP_NARRATIVE_RUNTIME",
    "NarrativeRuntimeStatusProvider",
    "attach_narrative_runtime",
    "handle_commentary_runtime_status",
    "register_narrative_runtime_routes",
]
