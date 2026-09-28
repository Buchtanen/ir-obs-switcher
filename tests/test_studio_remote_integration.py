"""Studio's existing settings writer preserves remote commentary configuration."""

import configparser
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from test_overlay_config import _minimal_ini

from irswitch.config import AppConfig
from irswitch.events.commentary_model import ModelSettings
from irswitch.overlay.http import handle_get_config, handle_put_config
from irswitch.server import api
from irswitch.server.app_keys import APP_CONFIG, APP_CONFIG_PATH


@pytest.mark.asyncio
async def test_studio_partial_save_preserves_remote_config_and_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _minimal_ini(tmp_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("""
[commentary]
enabled = true
[commentary.llm]
enabled = true
provider = remote
mode = shadow
base_url = https://llm.buchtovo.cz/v1
model = openai/gpt-oss-120b
api_key_env = IRSWITCH_LLM_API_KEY
timeout_s = 1.5
max_tokens = 192
max_profile = tight
warmup = false
[commentary.tts]
backend = supertonic
voice = M1
[companion_apps]
obs = true
""")
    before = AppConfig.from_file(path)
    assert before.commentary_v2 is not None and before.commentary_v2.valid
    assert before.commentary_v2.snapshot is not None
    original = configparser.ConfigParser()
    original.read(path, encoding="utf-8")
    monkeypatch.setattr(api, "_config_container", [before])
    monkeypatch.setenv("IRSWITCH_LLM_API_KEY", "integration-test-token-not-for-network")
    app = web.Application()
    app[APP_CONFIG] = before
    app[APP_CONFIG_PATH] = path
    app.router.add_get("/api/config", handle_get_config)
    app.router.add_put("/api/config", handle_put_config)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/config")
        assert response.status == 200
        public = await response.text()
        assert "test_password" not in public
        assert "integration-test-token-not-for-network" not in public
        response = await client.put(
            "/api/config",
            headers={"X-Requested-With": "irswitch"},
            json={"values": {"overlay.debug": True}},
        )
        assert response.status == 200, await response.text()
        assert (await response.json())["applied"] == ["overlay.debug"]
        assert (await (await client.get("/api/config")).json())["overlay"]["overlay.debug"]
    after = AppConfig.from_file(path)
    assert after.commentary_v2 is not None and after.commentary_v2.valid
    assert after.commentary_v2.snapshot is not None
    assert after.commentary_v2.snapshot.values == before.commentary_v2.snapshot.values
    settings = ModelSettings.from_values(dict(after.commentary_v2.snapshot.values))
    assert settings.enabled and settings.speech_enabled
    assert settings.provider == "remote" and settings.mode == "shadow"
    assert settings.base_url == "https://llm.buchtovo.cz/v1"
    written = configparser.ConfigParser()
    written.read(path, encoding="utf-8")
    for section in (
        "obs",
        "scenes",
        "commentary",
        "commentary.llm",
        "commentary.tts",
        "companion_apps",
    ):
        assert dict(written[section]) == dict(original[section])
    assert "integration-test-token-not-for-network" not in path.read_text(encoding="utf-8")
