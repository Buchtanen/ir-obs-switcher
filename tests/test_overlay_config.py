"""Overlay config load/write, schema, secrets redaction."""

from pathlib import Path

import pytest

from irswitch.config import AppConfig
from irswitch.config_reload import LIVE_CONFIG_KEYS
from irswitch.overlay.bus import strip_secrets
from irswitch.overlay.config_io import apply_overlay_values
from irswitch.overlay.schema import (
    OVERLAY_FIELDS,
    coerce_value,
    field_by_key,
    overlay_values,
)


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


def test_feature_flags_default_off_and_language_en(tmp_path: Path) -> None:
    cfg = AppConfig.from_file(_minimal_ini(tmp_path))
    assert cfg.overlay.language == "en"
    assert cfg.overlay.v4.assets is False
    assert cfg.overlay.v4.renderer is False
    ee = cfg.overlay.event_engine
    assert (
        ee.v2_payload
        or ee.practice
        or ee.quali_projection
        or ee.overtake_classifier
        or ee.pit_story
        or ee.hr_pressure
    ) is False
    assert cfg.overlay.commentary.enabled is False
    assert cfg.overlay.commentary.use_hr_emotion is True
    assert cfg.overlay.commentary.gap_hunt_tts_in_practice is False
    assert cfg.overlay.commentary.gap_hunt_tts_in_qualifying is False
    assert cfg.overlay.race_observer.leader_pace_cooldown_s == 300.0
    assert cfg.overlay.race_observer.incident_classify is False
    assert cfg.overlay.race_observer.flags is False
    values = overlay_values(cfg.overlay)
    flag_keys = [k for k in values if k.startswith("event_engine.") or k.startswith("overlay.v4_")]
    assert len(flag_keys) == 8
    assert all(values[key] is False for key in flag_keys)


def test_feature_flags_and_language_load_from_ini(tmp_path: Path) -> None:
    path = _minimal_ini(tmp_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("""
[overlay]
language = cs
v4_assets = true
[event_engine]
v2_payload = true
pit_story = true
""")
    cfg = AppConfig.from_file(path)
    assert cfg.overlay.language == "cs"
    assert cfg.overlay.v4.assets is True
    assert cfg.overlay.v4.renderer is False
    assert cfg.overlay.event_engine.v2_payload is True
    assert cfg.overlay.event_engine.pit_story is True
    assert cfg.overlay.event_engine.practice is False
    assert cfg.overlay.commentary.enabled is False


def test_commentary_section_loads_from_ini(tmp_path: Path) -> None:
    path = _minimal_ini(tmp_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("""
[commentary]
enabled = true
use_hr_emotion = false
cooldown_s = 2.5
max_utterance_s = 5.0
tts_backend = espeak
tts_rate = -3
audio_device = CABLE Input
duck_input = Zvuk plochy
duck_ratio = 0.25
duck_fade_ms = 400
gap_hunt_tts_in_practice = true
[race_observer]
leader_pace_cooldown_s = 120
incident_classify = true
flags = true
""")
    cfg = AppConfig.from_file(path)
    assert cfg.overlay.commentary.enabled is True
    assert cfg.overlay.commentary.use_hr_emotion is False
    assert cfg.overlay.commentary.cooldown_s == 2.5
    assert cfg.overlay.commentary.max_utterance_s == 5.0
    assert cfg.overlay.commentary.tts_backend == "espeak"
    assert cfg.overlay.commentary.tts_rate == -3
    assert cfg.overlay.commentary.audio_device == "CABLE Input"
    assert cfg.overlay.commentary.duck_input == "Zvuk plochy"
    assert cfg.overlay.commentary.duck_ratio == 0.25
    assert cfg.overlay.commentary.duck_fade_ms == 400
    assert cfg.overlay.commentary.gap_hunt_tts_in_practice is True
    assert cfg.overlay.race_observer.leader_pace_cooldown_s == 120.0
    assert cfg.overlay.race_observer.incident_classify is True
    assert cfg.overlay.race_observer.flags is True
    values = overlay_values(cfg.overlay)
    assert values["commentary.enabled"] is True
    assert values["commentary.audio_device"] == "CABLE Input"
    assert values["commentary.duck_input"] == "Zvuk plochy"
    assert values["commentary.duck_ratio"] == 0.25
    assert values["commentary.duck_fade_ms"] == 400
    assert values["race_observer.incident_classify"] is True
    assert values["race_observer.flags"] is True


def test_session_tape_defaults_on(tmp_path: Path) -> None:
    cfg = AppConfig.from_file(_minimal_ini(tmp_path))
    assert cfg.overlay.tape.enabled is True
    assert cfg.overlay.tape.directory == "recordings"


def test_unknown_language_falls_back_to_en(tmp_path: Path) -> None:
    path = _minimal_ini(tmp_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n[overlay]\nlanguage = klingon\n")
    assert AppConfig.from_file(path).overlay.language == "en"


def test_feature_flag_put_roundtrip(tmp_path: Path) -> None:
    path = _minimal_ini(tmp_path)
    applied = apply_overlay_values(
        path,
        {
            "overlay.language": "cs",
            "overlay.v4_renderer": True,
            "event_engine.overtake_classifier": True,
        },
    )
    assert applied == [
        "event_engine.overtake_classifier",
        "overlay.language",
        "overlay.v4_renderer",
    ]
    cfg = AppConfig.from_file(path)
    assert cfg.overlay.language == "cs"
    assert cfg.overlay.v4.renderer is True
    assert cfg.overlay.event_engine.overtake_classifier is True
    values = overlay_values(cfg.overlay)
    assert values["overlay.language"] == "cs"
    assert values["event_engine.overtake_classifier"] is True


def test_live_overlay_fields_are_hot_reloadable() -> None:
    live_keys = {spec.key for spec in OVERLAY_FIELDS if spec.live}
    assert live_keys <= LIVE_CONFIG_KEYS


def test_language_choice_is_validated() -> None:
    spec = field_by_key("overlay.language")
    assert spec is not None
    assert spec.choices == ("en", "cs")
    assert coerce_value(spec, "cs") == "cs"
    with pytest.raises(ValueError):
        coerce_value(spec, "klingon")


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
