"""HTTP mount for NarrativeRuntime status + decisions + validate/speak (#284 / #273).

Exposes:
- ``GET /api/commentary/runtime`` — commentary-runtime/2 status subset
- ``GET /api/commentary/runtime/decisions`` — commentary-runtime/2 decisions ring
- ``POST /api/commentary/runtime/validate`` — offline validate against caller bindings
- ``POST /api/commentary/runtime/speak`` — manual speak admit via NarrativeRuntime

Providers may be attached via:

- ``APP_NARRATIVE_RUNTIME`` on the aiohttp app (tests / explicit cutover), or
- process-level ``set_narrative_runtime`` (race shadow fanout cutover).

When neither is set, handlers project a disabled library snapshot (status) or
``runtime=false`` empty decisions. Validate stays offline (no provider required).
Speak without a provider returns ``component_unavailable`` / 503.

This mount does not start the NarrativeRuntime actor loop, does not replace
``GET /api/commentary/status`` or ``GET /api/commentary/decisions``, and does
not replace live CommentaryConsumer EventSubscription. Public
``POST /api/commentary/validate`` and ``POST /api/commentary/speak`` are cut
over to these handlers (registered from ``commentary.http``); the
``/api/commentary/runtime/validate|speak`` paths remain aliases. Not exported
from ``events/__init__.py``.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from aiohttp import web

from irswitch.contracts.primitives import ContractViolation
from irswitch.events.narrative_decision_projection import project_runtime_decisions
from irswitch.events.narrative_ingress import project_runtime_status
from irswitch.events.narrative_runtime import ManualSpeakOutcome, NarrativeRuntime, RuntimeStatus
from irswitch.events.narrative_validate_projection import project_validate_response

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


def _error_response(
    code: str, status: int, message: str = "Bounded public detail."
) -> web.Response:
    return web.json_response(
        {
            "schemaVersion": "commentary-runtime/2",
            "error": {"code": code, "fields": {}, "message": message},
        },
        status=status,
    )


async def _read_json_object(request: web.Request) -> dict[str, Any] | web.Response:
    try:
        body = await request.json()
    except Exception:
        return _error_response("invalid_json", 400)
    if not isinstance(body, dict):
        return _error_response("invalid_request", 400)
    return body


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


async def handle_commentary_runtime_validate(request: web.Request) -> web.Response:
    """Offline validate EN text against supplied beat + bindings (no live state)."""

    body = await _read_json_object(request)
    if isinstance(body, web.Response):
        return body
    try:
        payload = project_validate_response(body)
    except ContractViolation as exc:
        logger.warning("narrative runtime validate rejected: %s", exc)
        return _error_response("invalid_request", 400, str(exc)[:256] or "Bounded public detail.")
    except Exception as exc:
        logger.warning("narrative runtime validate failed", exc_info=True)
        return web.json_response(
            {"error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )
    return web.json_response(payload, status=200)



_SPEAK_BODY_KEYS = frozenset({"schemaVersion", "text", "language"})


def _parse_manual_speak_body(body: dict[str, Any]) -> str | web.Response:
    """Freeze manual speak to schemaVersion/text/language only (#273).

    Unknown keys / wrong schemaVersion / non-en language → ``invalid_request``/400.
    Text must be normalized Unicode, length 1..400, without control characters
    → otherwise ``validation_failed``/422. Returns the validated text string.
    """

    if set(body) != _SPEAK_BODY_KEYS:
        return _error_response("invalid_request", 400)
    if body.get("schemaVersion") != "commentary-runtime/2":
        return _error_response("invalid_request", 400)
    if body.get("language") != "en":
        return _error_response("invalid_request", 400)
    text = body.get("text")
    if not isinstance(text, str):
        return _error_response("validation_failed", 422)
    normalized = " ".join(text.split())
    if text != normalized or not 1 <= len(text) <= 400 or any(ord(ch) < 32 for ch in text):
        return _error_response("validation_failed", 422)
    return text


async def handle_commentary_runtime_speak(request: web.Request) -> web.Response:
    """Admit manual EN speak through NarrativeRuntime (sync reduce path)."""

    body = await _read_json_object(request)
    if isinstance(body, web.Response):
        return body
    parsed = _parse_manual_speak_body(body)
    if isinstance(parsed, web.Response):
        return parsed
    text = parsed

    provider = _resolve_provider(request)
    if provider is None:
        return _error_response("component_unavailable", 503)
    speak = getattr(provider, "try_manual_speak", None)
    if speak is None:
        return _error_response("component_unavailable", 503)

    request_id = f"manual:{uuid.uuid4().hex[:4]}"
    now_ms = int(time.monotonic() * 1000)
    try:
        outcome = await speak(text, request_id=request_id, now_ms=now_ms)
    except Exception as exc:
        logger.warning("narrative runtime speak failed", exc_info=True)
        return web.json_response(
            {"error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )

    if not isinstance(outcome, ManualSpeakOutcome):
        return _error_response("component_unavailable", 503)
    if outcome.kind == "accepted":
        return web.json_response(
            {
                "schemaVersion": "commentary-runtime/2",
                "accepted": True,
                "requestId": outcome.request_id or request_id,
                "admittedState": "committed",
            },
            status=202,
        )
    if outcome.kind == "speech_busy":
        return _error_response("speech_busy", 409)
    if outcome.kind == "validation_failed":
        return _error_response("validation_failed", 422)
    if outcome.kind == "mailbox_overloaded":
        return _error_response("mailbox_overloaded", 503)
    if outcome.kind == "admission_timeout":
        return _error_response("admission_timeout", 503)
    return _error_response("component_unavailable", 503)


def register_narrative_runtime_routes(app: web.Application) -> None:
    """Mount runtime status + decisions + validate/speak (additive; no actor start)."""
    app.router.add_get("/api/commentary/runtime", handle_commentary_runtime_status)
    app.router.add_get("/api/commentary/runtime/decisions", handle_commentary_runtime_decisions)
    app.router.add_post("/api/commentary/runtime/validate", handle_commentary_runtime_validate)
    app.router.add_post("/api/commentary/runtime/speak", handle_commentary_runtime_speak)


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
    "handle_commentary_runtime_speak",
    "handle_commentary_runtime_status",
    "handle_commentary_runtime_validate",
    "register_narrative_runtime_routes",
    "set_narrative_runtime",
]
