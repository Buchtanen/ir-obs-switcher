"""Unit tests for AppConfig validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from irswitch.config import AppConfig


def _write_config(tmp_path: Path, **overrides: int) -> Path:
    """Write a minimal INI matching other tests; override selected numeric keys."""
    values: dict[str, int] = {
        "http_port": 17321,
        "poll_hz": 5,
        "debounce_ms": 900,
        "cooldown_ms": 1000,
        "override_seconds": 120,
    }
    values.update(overrides)

    config_file = tmp_path / "config.ini"
    config_file.write_text(f"""[app]
http_host = 127.0.0.1
http_port = {values["http_port"]}
log_level = INFO

[iracing]
poll_hz = {values["poll_hz"]}

[obs]
ws_url = ws://127.0.0.1:4455
password = test_password

[switching]
autoswitch_default = true
debounce_ms = {values["debounce_ms"]}
cooldown_ms = {values["cooldown_ms"]}
override_seconds = {values["override_seconds"]}
safe_scene = Idle

[scenes]
IDLE = Idle
GARAGE = Pits
RACE = Race
REPLAY = Replay
""")
    return config_file


def test_valid_config_loads(tmp_path: Path) -> None:
    """Minimal valid INI loads without error."""
    config = AppConfig.from_file(_write_config(tmp_path))
    assert config.http_port == 17321
    assert config.poll_hz == 5
    assert config.debounce_ms == 900
    assert config.cooldown_ms == 1000
    assert config.override_seconds == 120
    assert config.stream_chapters.enabled is False
    assert config.stream_chapters.start_title == "Stream start"
    assert config.stream_chapters.end_title == "Stream end"
    assert config.stream_chapters.youtube_vod is False
    assert config.overlay.commentary.graph_runtime_mode == "legacy"


@pytest.mark.parametrize("mode", ["legacy", "shadow", "active"])
def test_commentary_graph_runtime_mode_loads(tmp_path: Path, mode: str) -> None:
    path = _write_config(tmp_path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n[commentary.graph_runtime]\nmode = {mode}\n")
    config = AppConfig.from_file(path)
    assert config.overlay.commentary.graph_runtime_mode == mode


def test_invalid_commentary_graph_runtime_mode_falls_back_to_legacy(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n[commentary.graph_runtime]\nmode = surprising\n")
    config = AppConfig.from_file(path)
    assert config.overlay.commentary.graph_runtime_mode == "legacy"


def test_stream_chapters_section_loads(tmp_path: Path) -> None:
    """Optional [stream_chapters] section is parsed."""
    path = _write_config(tmp_path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("""
[stream_chapters]
enabled = true
start_title = Go
trigger_session_types = Race
title_race = Feature Race
""")
    config = AppConfig.from_file(path)
    assert config.stream_chapters.enabled is True
    assert config.stream_chapters.start_title == "Go"
    assert config.stream_chapters.trigger_session_types == ("Race",)
    assert config.stream_chapters.session_titles["race"] == "Feature Race"


def test_poll_hz_zero_raises(tmp_path: Path) -> None:
    """iracing.poll_hz must be >= 1."""
    path = _write_config(tmp_path, poll_hz=0)
    with pytest.raises(ValueError, match="poll_hz"):
        AppConfig.from_file(path)


def test_debounce_ms_negative_raises(tmp_path: Path) -> None:
    """switching.debounce_ms must be >= 0."""
    path = _write_config(tmp_path, debounce_ms=-1)
    with pytest.raises(ValueError, match="debounce_ms"):
        AppConfig.from_file(path)


@pytest.mark.parametrize("http_port", [0, 70000])
def test_http_port_out_of_range_raises(tmp_path: Path, http_port: int) -> None:
    """app.http_port must be in 1..65535."""
    path = _write_config(tmp_path, http_port=http_port)
    with pytest.raises(ValueError, match="http_port"):
        AppConfig.from_file(path)
