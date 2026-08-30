"""Commentary test page + speak/validate API. Localhost + CSRF for writes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import web

from irswitch.commentary.assignments import render_assignments
from irswitch.commentary.duck import ducker_from_settings
from irswitch.commentary.graph import GraphNode, load_sequence_graph
from irswitch.commentary.tts import TtsResult, detect_backend, list_voices, speak_text
from irswitch.commentary.validator import validate_utterance
from irswitch.overlay.http import _file_response, _require_csrf
from irswitch.overlay.i18n import normalize_language

logger = logging.getLogger(__name__)

SAMPLE_LINES = {
    "en": "Commentary test. He takes P5 from Rossi.",
    "cs": "Test komentáře. Bere páté místo před Rossim.",
}


def _config() -> Any:
    from irswitch.server.api import get_app_config

    return get_app_config()


def _commentary_settings() -> Any:
    cfg = _config()
    if cfg is None:
        from irswitch.overlay.settings import CommentarySettings

        return CommentarySettings()
    return cfg.overlay.commentary


def _language() -> str:
    cfg = _config()
    if cfg is None:
        return "en"
    return normalize_language(cfg.overlay.language)


async def handle_commentary_page(_request: web.Request) -> web.StreamResponse:
    return _file_response("commentary/index.html")


async def handle_commentary_status(_request: web.Request) -> web.Response:
    settings = _commentary_settings()
    graph = load_sequence_graph()
    locale = _language()
    backend = detect_backend(settings.tts_backend)
    nodes = []
    for node in sorted(graph.nodes.values(), key=lambda item: (-item.speak_priority, item.id)):
        nodes.append(
            {
                "id": node.id,
                "family": node.family,
                "eventTypes": list(node.event_types),
                "phases": list(node.phases),
                "speakPriority": node.speak_priority,
                "unfilled": not bool(node.variant_bucket(locale, "unknown")),
                "sample": _sample_for_node(node),
            }
        )
    return web.json_response(
        {
            "backend": backend,
            "configuredBackend": settings.tts_backend,
            "voices": list_voices(settings.tts_backend),
            "language": locale,
            "sample": SAMPLE_LINES.get(locale, SAMPLE_LINES["en"]),
            "settings": {
                "enabled": settings.enabled,
                "useHrEmotion": settings.use_hr_emotion,
                "cooldownS": settings.cooldown_s,
                "maxUtteranceS": settings.max_utterance_s,
                "ttsBackend": settings.tts_backend,
                "ttsVoice": settings.tts_voice,
                "ttsRate": settings.tts_rate,
                "audioDevice": settings.audio_device,
                "duckInput": settings.duck_input,
                "duckRatio": settings.duck_ratio,
                "duckFadeMs": settings.duck_fade_ms,
                "decisionLogSize": settings.decision_log_size,
            },
            "audioHint": (
                "On the stream PC, route SAPI playback to a Virtual Audio Driver "
                "(not headphones) so OBS can capture commentary separately."
            ),
            "nodes": nodes,
            "unfilledCells": len(graph.unfilled_cells()),
        }
    )


async def handle_commentary_decisions(request: web.Request) -> web.Response:
    """Recent speak/skip decisions from the live director (empty if runtime down)."""
    try:
        limit = int(request.rel_url.query.get("limit") or 20)
    except ValueError:
        limit = 20
    limit = max(1, min(limit, 100))
    from irswitch.overlay import http as overlay_http

    runtime = getattr(overlay_http, "_overlay_runtime", None)
    director = getattr(runtime, "commentary", None) if runtime is not None else None
    if director is None or not hasattr(director, "decisions"):
        return web.json_response({"decisions": [], "runtime": False})
    return web.json_response({"decisions": director.decisions(limit), "runtime": True})


async def handle_commentary_validate(request: web.Request) -> web.Response:
    denied = _require_csrf(request)
    if denied is not None:
        return denied
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    text = str(body.get("text") or "")
    node = _node_or_default(str(body.get("nodeId") or ""))
    issues = [
        {"code": item.code, "message": item.message, "severity": item.severity}
        for item in validate_utterance(text, node)
    ]
    return web.json_response({"ok": not issues, "issues": issues, "text": text, "nodeId": node.id})


async def handle_commentary_speak(request: web.Request) -> web.Response:
    denied = _require_csrf(request)
    if denied is not None:
        return denied
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    text = str(body.get("text") or "").strip()
    node = _node_or_default(str(body.get("nodeId") or ""))
    issues = validate_utterance(text, node)
    force = bool(body.get("force"))
    if issues and not force:
        return web.json_response(
            {
                "spoken": False,
                "error": "validation failed",
                "issues": [
                    {"code": item.code, "message": item.message, "severity": item.severity}
                    for item in issues
                ],
            },
            status=400,
        )
    settings = _commentary_settings()
    locale = str(body.get("locale") or _language())
    voice = str(body.get("voice") if body.get("voice") is not None else settings.tts_voice)
    try:
        rate = int(body.get("rate", settings.tts_rate))
    except (TypeError, ValueError):
        rate = settings.tts_rate
    backend = str(body.get("backend") or settings.tts_backend)
    timeout = max(settings.max_utterance_s + 10.0, 20.0)

    def _speak_job() -> TtsResult:
        with ducker_from_settings(settings):
            return speak_text(
                text,
                locale=locale,
                voice=voice,
                rate=rate,
                backend=backend,
                device=settings.audio_device,
                timeout_s=timeout,
            )

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _speak_job)
    return web.json_response(
        {
            "spoken": result.spoken,
            "backend": result.backend,
            "error": result.error,
            "text": text,
            "issues": [
                {"code": item.code, "message": item.message, "severity": item.severity}
                for item in issues
            ],
        }
    )


async def handle_commentary_assignments(_request: web.Request) -> web.Response:
    return web.Response(
        text=render_assignments(locale=_language()),
        content_type="text/markdown; charset=utf-8",
    )


def _node_or_default(node_id: str) -> GraphNode:
    graph = load_sequence_graph()
    node = graph.node(node_id) if node_id else None
    if node is not None:
        return node
    return graph.nodes["overtake"]


def _sample_for_node(node: GraphNode) -> str:
    values = {slot.name: slot.example for slot in node.slots}
    if "position" in values and "target_name" in values:
        template = "He takes P{position} from {target_name}."
    elif "position" in values:
        template = "He is P{position}."
    elif "lap" in values:
        template = "Lap {lap} is done."
    elif "gap" in values:
        template = "Gap is {gap} seconds."
    elif "bpm" in values:
        template = "Heart rate {bpm}."
    else:
        template = f"{node.id.replace('_', ' ').capitalize()} now."
    for name, example in values.items():
        template = template.replace("{" + name + "}", str(example))
    if not template.endswith((".", "!", "?")):
        template += "."
    return template


def register_commentary_routes(app: web.Application) -> None:
    app.router.add_get("/commentary", handle_commentary_page)
    app.router.add_get("/commentary/", handle_commentary_page)
    app.router.add_get("/api/commentary/status", handle_commentary_status)
    app.router.add_get("/api/commentary/decisions", handle_commentary_decisions)
    app.router.add_get("/api/commentary/assignments", handle_commentary_assignments)
    app.router.add_post("/api/commentary/validate", handle_commentary_validate)
    app.router.add_post("/api/commentary/speak", handle_commentary_speak)
