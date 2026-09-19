"""Unit tests for config reload live vs restart classification."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from irswitch.config import AppConfig
from irswitch.config_reload import CommentaryConfigCoordinator, classify_reload_diff
from irswitch.contracts.config import parse_commentary_mapping
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


def test_commentary_coordinator_bootstraps_valid_candidate_without_reload_generation(
    tmp_path: Path,
) -> None:
    candidate = parse_commentary_mapping({"commentary.enabled": True}, repository_root=tmp_path)

    coordinator = CommentaryConfigCoordinator.bootstrap(candidate)

    assert coordinator.ledger.desired_generation == 0
    assert coordinator.automatic_enabled is True
    assert coordinator.diagnostics == ()
    assert coordinator.speech_language == "en"


def test_commentary_language_is_not_configurable(tmp_path: Path) -> None:
    candidate = parse_commentary_mapping({"commentary.language": "cs"}, repository_root=tmp_path)

    coordinator = CommentaryConfigCoordinator.bootstrap(candidate)

    assert candidate.valid is False
    assert coordinator.automatic_enabled is False
    assert coordinator.speech_language == "en"


def test_invalid_commentary_reload_preserves_generation_and_manual_backend(
    tmp_path: Path,
) -> None:
    initial = parse_commentary_mapping({}, repository_root=tmp_path)
    coordinator = CommentaryConfigCoordinator.bootstrap(initial, ready_components=("tts",))
    invalid = parse_commentary_mapping({"commentary.tts.backend": "null"}, repository_root=tmp_path)

    outcome = coordinator.install(invalid)

    assert outcome.installed is False
    assert coordinator.ledger.desired_generation == 0
    assert coordinator.automatic_enabled is False
    assert coordinator.diagnostics == invalid.diagnostics
    assert coordinator.ledger.component_available("tts", 0) is True


def test_valid_commentary_reload_uses_one_persistent_ledger(tmp_path: Path) -> None:
    initial = parse_commentary_mapping({}, repository_root=tmp_path)
    coordinator = CommentaryConfigCoordinator.bootstrap(initial)
    enabled = parse_commentary_mapping(
        {
            "commentary.enabled": True,
            "commentary.tts.backend": "espeak",
        },
        repository_root=tmp_path,
    )

    outcome = coordinator.install(enabled)

    assert outcome.installed is True
    assert outcome.desired_generation == 1
    assert coordinator.ledger.desired_generation == 1
    assert coordinator.ledger.apply_sequence == 1
    assert coordinator.ledger.effective_snapshot.values["commentary.enabled"] is True
    assert all(item.boundary != "command" for item in coordinator.ledger.pending_changes)
    assert coordinator.automatic_enabled is True
    assert coordinator.diagnostics == ()
    assert [(item.component, item.generation) for item in outcome.preflights] == [("tts", 1)]
