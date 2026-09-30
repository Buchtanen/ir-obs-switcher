"""Provider compatibility, authentication and failure isolation gates."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_remote_commentary_microplan import plan
from test_remote_commentary_runtime import reply

from irswitch.contracts.config import parse_commentary_mapping
from irswitch.events.commentary_model import ModelClient, ModelFailure, ModelSettings

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "provider,url,valid",
    [
        ("local", "http://192.168.0.38:11434/v1", True),
        ("local", "https://llm.buchtovo.cz/v1", False),
        ("remote", "https://llm.buchtovo.cz/v1", True),
        ("remote", "http://llm.buchtovo.cz/v1", False),
        ("remote", "https://name:secret@llm.buchtovo.cz/v1", False),
        ("remote", "https://llm.buchtovo.cz/v1?token=secret", False),
        ("remote", "https://llm.buchtovo.cz/v1#secret", False),
        ("remote", "https://llm.buchtovo.cz/api/v1", False),
    ],
)
def test_explicit_provider_url_policy(provider, url, valid):
    result = parse_commentary_mapping(
        {"commentary.llm.provider": provider, "commentary.llm.base_url": url}, repository_root=ROOT
    )
    assert result.valid is valid


def test_environment_name_cannot_contain_a_token():
    result = parse_commentary_mapping(
        {"commentary.llm.api_key_env": "Bearer secret"}, repository_root=ROOT
    )
    assert not result.valid


def test_global_commentary_disable_invalidates_model_configuration():
    active = ModelSettings.from_values({"commentary.enabled": True, "commentary.llm.enabled": True})
    disabled = ModelSettings.from_values(
        {"commentary.enabled": False, "commentary.llm.enabled": True}
    )
    assert active.enabled and not disabled.enabled
    assert active.signature != disabled.signature
    authored = ModelSettings.from_values({"commentary.enabled": True})
    all_off = ModelSettings.from_values({"commentary.enabled": False})
    assert not authored.enabled and not all_off.enabled
    assert authored.signature != all_off.signature


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,content,reason",
    [
        (302, b"{}", "http_302"),
        (200, b"x" * 65537, "response_oversize"),
        (200, b"{bad", "response_json"),
    ],
    ids=["redirect", "oversize", "invalid_json"],
)
async def test_wire_redirect_size_and_json_guards(monkeypatch, status, content, reason):
    import aiohttp

    cfg = ModelSettings(enabled=True, base_url="http://127.0.0.1:11434")
    client = ModelClient(lambda: cfg)
    captured = {}

    class Content:
        async def iter_chunked(self, size):
            for offset in range(0, len(content), size):
                yield content[offset : offset + size]

    class Response:
        content_type = "application/json"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    response = Response()
    response.status, response.content = status, Content()

    class Session:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def post(self, url, **kwargs):
            captured.update(url=url, **kwargs)
            return response

    monkeypatch.setattr(aiohttp, "ClientSession", Session)
    with pytest.raises(ModelFailure, match=reason):
        await client._post({}, client._headers(cfg), 0.5)
    assert captured["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert captured["allow_redirects"] is False and captured["trust_env"] is False
    assert captured["timeout"].total == 0.5
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,reason",
    [
        (ModelFailure("http_401"), "http_401"),
        (ModelFailure("http_403"), "http_403"),
        (ModelFailure("http_429"), "http_429"),
        (ModelFailure("http_503"), "http_503"),
        (TimeoutError(), "timeout"),
        (ConnectionError("secret server error"), "transport_error"),
    ],
)
async def test_external_failure_never_retries_or_exposes_error(monkeypatch, failure, reason):
    cfg = ModelSettings(enabled=True)
    client = ModelClient(lambda: cfg)
    calls = 0

    async def post(*args):
        nonlocal calls
        calls += 1
        raise failure

    monkeypatch.setattr(client, "_post", post)
    current = plan()
    assert await client.realize(current) is None
    assert await client.realize(current) is None
    assert calls == 1 and client.status()["lastReason"] == reason
    assert "secret" not in json.dumps(client.status())
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "length",
        "reasoning",
        "multiple",
        "invalid_json",
        "skip",
        "wrong_ids",
        "two_candidates",
        "secret",
    ],
)
@pytest.mark.parametrize("wording_policy", ["strict", "experimental_free"])
async def test_protocol_edges_cannot_reach_speech(monkeypatch, kind, wording_policy):
    monkeypatch.setenv("IRSWITCH_LLM_API_KEY", "unit-secret")
    cfg = ModelSettings(
        enabled=True,
        provider="remote",
        base_url="https://llm.buchtovo.cz/v1",
        wording_policy=wording_policy,
    )
    client = ModelClient(lambda: cfg)
    current = plan()
    response = reply(current.allowed[0], current)
    choice = response["choices"][0]
    data = json.loads(choice["message"]["content"])
    if kind == "length":
        choice["finish_reason"] = "length"
    elif kind == "reasoning":
        choice["message"] = {"reasoning_content": "not speech", "content": None}
    elif kind == "multiple":
        response["choices"] *= 2
    elif kind == "invalid_json":
        choice["message"]["content"] = "{bad"
    else:
        if kind == "skip":
            data["action"] = "skip"
        elif kind == "wrong_ids":
            data["used_fact_ids"] = ["invented"]
        elif kind == "two_candidates":
            data["candidates"] *= 2
        else:
            data["candidates"][0]["text"] = "unit-secret"
        choice["message"]["content"] = json.dumps(data)

    async def post(*args):
        return response

    monkeypatch.setattr(client, "_post", post)
    assert await client.realize(current) is None
    assert "unit-secret" not in json.dumps(client.status())
    await client.close()


@pytest.mark.asyncio
async def test_deadline_heartbeat_and_expiry(monkeypatch):
    cfg = ModelSettings(enabled=True, timeout_s=0.02)
    client = ModelClient(lambda: cfg)
    ticks = 0

    async def post(*args):
        await asyncio.Event().wait()

    async def heartbeat():
        nonlocal ticks
        for _ in range(5):
            await asyncio.sleep(0.001)
            ticks += 1

    monkeypatch.setattr(client, "_post", post)
    current = plan()
    await asyncio.gather(client.realize(current), heartbeat())
    assert ticks == 5 and client.status()["lastReason"] == "timeout"
    before = client.status()["totalAttempts"]
    assert await client.realize(replace(current, expires_ms=0)) is None
    assert client.status()["totalAttempts"] == before
    await client.close()


@pytest.mark.asyncio
async def test_auth_preflight_and_generation_share_headers(monkeypatch):
    monkeypatch.setenv("IRSWITCH_LLM_API_KEY", "unit-secret")
    cfg = ModelSettings(enabled=True, provider="remote", base_url="https://llm.buchtovo.cz/v1")
    client = ModelClient(lambda: cfg)
    captured = []

    async def post(body, headers, timeout):
        captured.append((headers, timeout))
        return {"choices": [{"finish_reason": "stop", "message": {"content": "OK"}}]}

    monkeypatch.setattr(client, "_post", post)
    client.start()
    await asyncio.sleep(0.001)
    assert client.status()["preflight"] == "ready"
    await client.realize(plan())
    assert len(captured) == 2 and captured[0] == captured[1]
    assert captured[0][0]["Authorization"] == "Bearer unit-secret"
    await client.close()
