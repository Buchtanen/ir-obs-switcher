"""Overlay config load/write, schema, secrets redaction."""

from pathlib import Path

from irswitch.config import AppConfig
from irswitch.overlay.bus import strip_secrets
from irswitch.overlay.config_io import apply_overlay_values
from irswitch.overlay.schema import coerce_value, field_by_key, overlay_values


def _minimal_ini(tmp_path: Path) -> Path:
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
    return path


def test_overlay_defaults_when_sections_missing(tmp_path: Path) -> None:
    cfg = AppConfig.from_file(_minimal_ini(tmp_path))
    assert cfg.overlay.enabled is True
    assert cfg.overlay.theme == "cyber_racing"
    assert cfg.overlay.sampling.default_hz == 5.0
    assert cfg.overlay.sampling.bio_hz is None


def test_overlay_sections_load(tmp_path: Path) -> None:
    path = _minimal_ini(tmp_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("""
[sampling]
default_hz = 8
[sampling.race]
hz = 12
[overlay]
theme = stealth_graphite
""")
    cfg = AppConfig.from_file(path)
    assert cfg.overlay.sampling.default_hz == 8
    assert cfg.overlay.sampling.race_hz == 12
    assert cfg.overlay.theme == "stealth_graphite"


def test_put_roundtrip_and_backup(tmp_path: Path) -> None:
    path = _minimal_ini(tmp_path)
    applied = apply_overlay_values(
        path, {"sampling.default_hz": 6.5, "overlay.theme": "night_attack"}
    )
    assert "sampling.default_hz" in applied
    assert path.with_suffix(".ini.bak").exists() or (path.parent / "config.ini.bak").exists()
    cfg = AppConfig.from_file(path)
    assert cfg.overlay.sampling.default_hz == 6.5
    assert cfg.overlay.theme == "night_attack"


def test_schema_rejects_traversal_and_strip_secrets(tmp_path: Path) -> None:
    spec = field_by_key("system_info.lhm_dll_path")
    assert spec is not None
    try:
        coerce_value(spec, "../evil.dll")
        raise AssertionError("should reject")
    except ValueError:
        pass
    redacted = strip_secrets({"obs": {"password": "x", "host": "127.0.0.1"}, "ok": 1})
    assert "password" not in redacted["obs"]
    assert redacted["ok"] == 1
    cfg = AppConfig.from_file(_minimal_ini(tmp_path))
    values = overlay_values(cfg.overlay)
    assert "sampling.default_hz" in values
