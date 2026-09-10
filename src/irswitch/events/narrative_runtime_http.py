"""HTTP mount for NarrativeRuntime status + decisions projection (#284).

Exposes:
- ``GET /api/commentary/runtime`` — commentary-runtime/2 status subset
- ``GET /api/commentary/runtime/decisions`` — commentary-runtime/2 decisions ring

Providers may be attached via:

- ``APP_NARRATIVE_RUNTIME`` on the aiohttp app (tests / explicit cutover), or
- process-level ``set_narrative_runtime`` (race shadow fanout cutover).

When neither is set, handlers project a disabled library snapshot (status) or
``runtime=false`` empty decisions.

This mount does not start the NarrativeRuntime actor loop, does not replace
``GET /api/commentary/status`` or ``GET /api/commentary/decisions``, and does
not replace live CommentaryConsumer EventSubscription. Not exported from
``events/__init__.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from aiohttp import web

from irswitch.contracts.primitives import ContractViolation
from irswitch.events.narrative_decision_projection import project_runtime_decisions
from irswitch.events.narrative_ingress import project_runtime_status
from irswitch.events.narrative_runtime import NarrativeRuntime, RuntimeStatus

logger = logging.getLogger(__name__)

_process_narrative_runtime: NarrativeRuntimeStatusProvider | None = None


class NarrativeRuntimeStatusProvider(Protocol):
    def status(self) -> RuntimeStatus: ...


class NarrativeRuntimeDecisionsProvider(Protocol):
    def decisions(self, limit: int = 20) -> Sequence[Mapping[str, Any]]: ...


APP_NARRATIVE_RUNTIME: web.AppKey[NarrativeRuntimeStatusProvider] = web.AppKey("narrative_runtime")


def set_narrative_runtime(runtime: NarrativeRuntimeStatusProvider | None) -> None:
    """Attach or clear the process-level status provider (race cutover path)."""
    global _process_narrative_runtime
    _process_narrative_runtime = runtime


def get_narrative_runtime() -> NarrativeRuntimeStatusProvider | None:
    """Return the process-level status provider, if any."""
    return _process_narrative_runtime


def _resolve_provider(request: web.Request) -> NarrativeRuntimeStatusProvider | None:
    provider = request.app.get(APP_NARRATIVE_RUNTIME)
    if provider is not None:
        return provider
    return get_narrative_runtime()


def _parse_limit(request: web.Request) -> int:
    raw = request.rel_url.query.get("limit", "20")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 20


async def handle_commentary_runtime_status(request: web.Request) -> web.Response:
    """Return commentary-runtime/2 status subset for NarrativeRuntime."""
    provider = _resolve_provider(request)
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


async def handle_commentary_runtime_decisions(request: web.Request) -> web.Response:
    """Return commentary-runtime/2 decisions ring for NarrativeRuntime."""
    provider = _resolve_provider(request)
    limit = _parse_limit(request)
    try:
        if provider is None:
            payload = project_runtime_decisions([], runtime=False, limit=limit)
        else:
            decisions_fn = getattr(provider, "decisions", None)
            if decisions_fn is None:
                rows: Sequence[Mapping[str, Any]] = ()
            else:
                rows = decisions_fn(limit)
            payload = project_runtime_decisions(rows, runtime=True, limit=limit)
    except ContractViolation as exc:
        logger.warning("narrative runtime decisions projection rejected: %s", exc)
        return web.json_response({"error": str(exc)}, status=500)
    except Exception as exc:
        logger.warning("narrative runtime decisions projection failed", exc_info=True)
        return web.json_response(
            {"error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )
    return web.json_response(payload)


def register_narrative_runtime_routes(app: web.Application) -> None:
    """Mount runtime status + decisions (additive; does not run the actor)."""
    app.router.add_get("/api/commentary/runtime", handle_commentary_runtime_status)
    app.router.add_get("/api/commentary/runtime/decisions", handle_commentary_runtime_decisions)


def attach_narrative_runtime(
    app: web.Application, runtime: NarrativeRuntimeStatusProvider | None
) -> None:
    """Attach or clear the optional app-key status provider (tests / cutover)."""
    if runtime is None:
        app.pop(APP_NARRATIVE_RUNTIME, None)
        return
    app[APP_NARRATIVE_RUNTIME] = runtime


__all__ = [
    "APP_NARRATIVE_RUNTIME",
    "NarrativeRuntimeDecisionsProvider",
    "NarrativeRuntimeStatusProvider",
    "attach_narrative_runtime",
    "get_narrative_runtime",
    "handle_commentary_runtime_decisions",
    "handle_commentary_runtime_status",
    "register_narrative_runtime_routes",
    "set_narrative_runtime",
]
