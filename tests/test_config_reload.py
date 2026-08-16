"""Unit tests for config reload live vs restart classification."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from irswitch.config import AppConfig
from irswitch.config_reload import classify_reload_diff
from irswitch.models import DrivingMode


def _load_minimal(tmp_path: Path) -> AppConfig:
    path = tmp_path / "config.ini"
    path.write_text("""[app]
http_host = 127.0.0.1
http_port = 17321
log_level = INFO

[iracing]
poll_hz = 5

[obs]
ws_url = ws://127.0.0.1:4455
password = test_password

[switching]
autoswitch_default = true
debounce_ms = 900
cooldown_ms = 1000
override_seconds = 120
safe_scene = Idle

[scenes]
IDLE = Idle
GARAGE = Pits
RACE = Race
REPLAY = Replay
""")
    return AppConfig.from_file(path)


def test_classify_no_old_config_returns_empty(tmp_path: Path) -> None:
    new = _load_minimal(tmp_path)
    applied, restart = classify_reload_diff(None, new)
    assert applied == []
    assert restart == []


def test_classify_unchanged_returns_empty(tmp_path: Path) -> None:
    cfg = _load_minimal(tmp_path)
    applied, restart = classify_reload_diff(cfg, cfg)
    assert applied == []
    assert restart == []


def test_classify_live_keys(tmp_path: Path) -> None:
    old = _load_minimal(tmp_path)
    new = replace(
        old,
        debounce_ms=777,
        poll_hz=20,
        scenes={**dict(old.scenes), DrivingMode.IDLE: "IdleNew"},
    )
    applied, restart = classify_reload_diff(old, new)
    assert applied == [
        "iracing.poll_hz",
        "scenes.IDLE",
        "switching.debounce_ms",
    ]
    assert restart == []


def test_classify_restart_keys(tmp_path: Path) -> None:
    old = _load_minimal(tmp_path)
    new = replace(
        old,
        http_port=18000,
        log_level="DEBUG",
        obs_password="changed",
        oauth_client_id="cid",
    )
    applied, restart = classify_reload_diff(old, new)
    assert applied == []
    assert restart == [
        "app.http_port",
        "app.log_level",
        "oauth.client_id",
        "obs.password",
    ]


def test_classify_mixed_live_and_restart(tmp_path: Path) -> None:
    old = _load_minimal(tmp_path)
    new = replace(old, debounce_ms=100, http_host="0.0.0.0")
    applied, restart = classify_reload_diff(old, new)
    assert applied == ["switching.debounce_ms"]
    assert restart == ["app.http_host"]
