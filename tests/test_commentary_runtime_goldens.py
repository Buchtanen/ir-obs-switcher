"""#273: freeze commentary-runtime/2 request/response/error goldens before handler edits."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from irswitch.events.narrative_runtime import ManualSpeakOutcome
from irswitch.events.narrative_runtime_http import (
    APP_NARRATIVE_RUNTIME,
    register_narrative_runtime_routes,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "commentary_runtime"
MACHINE_GOLDENS = ROOT / "docs" / "v2.0.0" / "machine" / "api-goldens.json"

# Required frozen surface for status / decisions / validate / speak (+ speak errors).
REQUIRED_FIXTURES = (
    "status_ready_library.json",
    "status_speech_idle.json",
    "status_identity_disabled.json",
    "status_identity_after_context.json",
    "status_timeline_session_null.json",
    "status_components_llm_tts.json",
    "decisions_selected.json",
    "decisions_story_successor.json",
    "decisions_expired_ttl.json",
    "status_opportunities_queue.json",
    "validate_request.json",
    "validate_supported.json",
    "validate_rejected.json",
    "speak_request.json",
    "speak_accepted.json",
    "error_invalid_json.json",
    "error_invalid_request.json",
    "error_forbidden.json",
    "error_not_found.json",
    "error_speech_busy.json",
    "error_validation_failed.json",
    "error_component_unavailable.json",
    "error_mailbox_overloaded.json",
    "error_admission_timeout.json",
    "health_commentary_disabled.json",
    "health_commentary_ready.json",
    "health_commentary_ready_history_incomplete.json",
    "health_commentary_degraded.json",
    "status_component_tape_capture_unavailable.json",
    "status_component_tape_counters.json",
    "status_by_tape_channel.json",
    "status_component_detectors_disabled.json",
    "status_health_projections_library.json",
)


def test_required_commentary_runtime_goldens_exist() -> None:
    missing = [name for name in REQUIRED_FIXTURES if not (FIXTURES / name).is_file()]
    assert missing == [], f"missing frozen goldens: {missing}"


def test_error_goldens_match_machine_api_goldens() -> None:
    machine = json.loads(MACHINE_GOLDENS.read_text(encoding="utf-8"))
    by_id = {
        row["id"]: row for row in machine["valid"] if str(row.get("id", "")).startswith("error_")
    }
    assert by_id, "machine api-goldens.json must list error_* rows"
    for error_id, row in sorted(by_id.items()):
        path = FIXTURES / f"{error_id}.json"
        assert path.is_file(), f"missing fixture for {error_id}"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        assert fixture == row["value"], f"{error_id} fixture drifted from machine golden"


def _app_with_provider(provider: object | None) -> web.Application:
    app = web.Application()
    register_narrative_runtime_routes(app)
    if provider is not None:
        app[APP_NARRATIVE_RUNTIME] = provider
    return app


@pytest.mark.asyncio
async def test_runtime_speak_mailbox_overloaded_matches_error_golden() -> None:
    """#273: mailbox_overloaded/503 body is frozen against error_mailbox_overloaded.json."""

    class _Overloaded:
        async def try_manual_speak(self, text: str, **kwargs: object) -> ManualSpeakOutcome:
            return ManualSpeakOutcome(kind="mailbox_overloaded")

    expected = json.loads((FIXTURES / "error_mailbox_overloaded.json").read_text(encoding="utf-8"))
    request = json.loads((FIXTURES / "speak_request.json").read_text(encoding="utf-8"))
    app = _app_with_provider(_Overloaded())
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/api/commentary/runtime/speak", json=request)
            assert resp.status == 503
            assert await resp.json() == expected


@pytest.mark.asyncio
async def test_runtime_speak_admission_timeout_matches_error_golden() -> None:
    class _Timeout:
        async def try_manual_speak(self, text: str, **kwargs: object) -> ManualSpeakOutcome:
            return ManualSpeakOutcome(kind="admission_timeout")

    expected = json.loads((FIXTURES / "error_admission_timeout.json").read_text(encoding="utf-8"))
    request = json.loads((FIXTURES / "speak_request.json").read_text(encoding="utf-8"))
    app = _app_with_provider(_Timeout())
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/api/commentary/runtime/speak", json=request)
            assert resp.status == 503
            assert await resp.json() == expected


@pytest.mark.asyncio
async def test_runtime_speak_busy_matches_error_golden() -> None:
    class _Busy:
        async def try_manual_speak(self, text: str, **kwargs: object) -> ManualSpeakOutcome:
            return ManualSpeakOutcome(kind="speech_busy")

    expected = json.loads((FIXTURES / "error_speech_busy.json").read_text(encoding="utf-8"))
    request = json.loads((FIXTURES / "speak_request.json").read_text(encoding="utf-8"))
    app = _app_with_provider(_Busy())
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/api/commentary/runtime/speak", json=request)
            assert resp.status == 409
            assert await resp.json() == expected


@pytest.mark.asyncio
async def test_runtime_speak_component_unavailable_matches_error_golden() -> None:
    expected = json.loads(
        (FIXTURES / "error_component_unavailable.json").read_text(encoding="utf-8")
    )
    request = json.loads((FIXTURES / "speak_request.json").read_text(encoding="utf-8"))
    app = _app_with_provider(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/api/commentary/runtime/speak", json=request)
            assert resp.status == 503
            assert await resp.json() == expected


def test_health_commentary_ready_matches_machine_golden() -> None:
    """#273: /health commentary ready shape is frozen to machine health_ready."""
    machine = json.loads(MACHINE_GOLDENS.read_text(encoding="utf-8"))
    row = next(item for item in machine["valid"] if item["id"] == "health_ready")
    fixture = json.loads((FIXTURES / "health_commentary_ready.json").read_text(encoding="utf-8"))
    assert fixture == row["value"]
    assert set(fixture) == {"status", "reason"}


def test_health_commentary_projector_matches_disabled_and_ready_goldens() -> None:
    from irswitch.events.narrative_ingress import project_commentary_health_component
    from irswitch.events.narrative_runtime import NarrativeRuntime

    disabled = json.loads(
        (FIXTURES / "health_commentary_disabled.json").read_text(encoding="utf-8")
    )
    ready = json.loads((FIXTURES / "health_commentary_ready.json").read_text(encoding="utf-8"))
    assert project_commentary_health_component() == disabled
    runtime = NarrativeRuntime()
    runtime.enable()
    assert project_commentary_health_component(runtime.status()) == ready


def test_health_commentary_projector_matches_degraded_golden() -> None:
    from dataclasses import replace

    from irswitch.events.narrative_ingress import project_commentary_health_component
    from irswitch.events.narrative_runtime import NarrativeRuntime

    expected = json.loads(
        (FIXTURES / "health_commentary_degraded.json").read_text(encoding="utf-8")
    )
    runtime = NarrativeRuntime()
    runtime.enable()
    degraded = replace(
        runtime.status(),
        runtime_state="degraded",
        reason_codes=("component_unavailable",),
    )
    assert project_commentary_health_component(degraded) == expected
