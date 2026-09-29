"""#349 Slice 5 — live HTTP/mediums: tape.enabled, journal off hot path, clean shutdown.

Sol tip audit: race always opened narrative tape + sync command journal on every
reduce, ignoring ``commentary.tape.enabled`` (default false).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from irswitch.contracts.command import NarrativeCommand
from irswitch.events.narrative_ingress import project_runtime_status
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import OverlaySettings
from irswitch.race.runtime import (
    RaceRuntime,
    _overlay_with_v2_commentary,
    commentary_live_enabled,
    commentary_llm_enabled,
    commentary_tape_enabled,
)

RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"


def test_race_gates_tape_and_drops_hot_path_command_journal() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "commentary_tape_enabled" in race
    assert "commentary.tape.enabled" in race
    # Live path must not hard-wire the sync journal file onto every reduce.
    assert 'command_journal_path=journal_dir / "narrative-command-journal.ndjson"' not in race
    assert "command_journal_path=None" in race
    assert "open_narrative_tape_writer" in race


def test_commentary_tape_enabled_fail_closed_without_v2() -> None:
    assert commentary_tape_enabled(None) is False
    assert commentary_tape_enabled(object()) is False  # type: ignore[arg-type]


def test_commentary_tape_enabled_reads_snapshot_values() -> None:
    class _Snap:
        values = {"commentary.tape.enabled": True}

    class _Cand:
        valid = True
        snapshot = _Snap()

    class _Cfg:
        commentary_v2 = _Cand()

    assert commentary_tape_enabled(_Cfg()) is True
    _Snap.values = {"commentary.tape.enabled": False}
    assert commentary_tape_enabled(_Cfg()) is False


def test_commentary_gates_accept_mappingproxy_values() -> None:
    from types import MappingProxyType

    class _Snap:
        values = MappingProxyType(
            {
                "commentary.enabled": True,
                "commentary.llm.enabled": False,
                "commentary.tape.enabled": True,
            }
        )

    class _Cand:
        valid = True
        snapshot = _Snap()

    class _Cfg:
        commentary_v2 = _Cand()

    assert commentary_live_enabled(_Cfg()) is True
    assert commentary_llm_enabled(_Cfg()) is False
    assert commentary_tape_enabled(_Cfg()) is True


def test_commentary_live_and_llm_gates_read_v2_snapshot() -> None:
    class _Snap:
        values = {"commentary.enabled": True, "commentary.llm.enabled": False}

    class _Cand:
        valid = True
        snapshot = _Snap()

    class _Cfg:
        commentary_v2 = _Cand()

    assert commentary_live_enabled(_Cfg()) is True
    assert commentary_llm_enabled(_Cfg()) is False
    assert commentary_live_enabled(None) is False
    assert commentary_llm_enabled(None) is False
    _Snap.values = {"commentary.enabled": True, "commentary.llm.enabled": True}
    assert commentary_llm_enabled(_Cfg()) is True


def test_llm_generation_does_not_enable_legacy_tts_polish() -> None:
    class _Snap:
        values = {"commentary.enabled": True, "commentary.llm.enabled": True}

    class _Cand:
        valid = True
        snapshot = _Snap()

    class _Cfg:
        commentary_v2 = _Cand()

    settings = _overlay_with_v2_commentary(OverlaySettings(), _Cfg())
    assert settings.commentary.llm_polish is False


def test_silence_request_samples_current_race_position_and_lap() -> None:
    class _Snap:
        values = {"commentary.enabled": True}

    class _Cand:
        valid = True
        snapshot = _Snap()

    cfg = SimpleNamespace(overlay=OverlaySettings(), commentary_v2=_Cand())
    runtime = RaceRuntime(lambda: cfg, None, OverlayBus())
    state = RaceState(connected=True, overlay_mode="RACE", class_position=30, lap=4)
    runtime._request_narrative_silence_fact()
    records = runtime._collect_narrative_silence_fact(state, 100.0)
    assert len(records) == 1
    assert records[0].envelope.event_type == "FIELD_FACT"
    assert records[0].envelope.metrics == {"fact": "position", "position": 30, "lap": 4}
    assert runtime._collect_narrative_silence_fact(state, 101.0) == []
    runtime._request_narrative_silence_fact()
    assert (
        runtime._collect_narrative_silence_fact(
            RaceState(connected=True, overlay_mode="RACE", class_position=30, stale_for_ms=5000),
            102.0,
        )
        == []
    )


def test_runtime_without_journal_path_does_not_create_journal_file(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "narrative-command-journal.ndjson"
    runtime = NarrativeRuntime(command_journal_path=None)
    runtime.enable()
    runtime.admit(NarrativeCommand.shutdown("mediums:shutdown", 1_000, "application_exit"))
    result = runtime.reduce_next()
    assert result is not None
    assert not journal.exists()


def test_runtime_journal_path_still_optional_for_offline_capture(tmp_path: Path) -> None:
    journal = tmp_path / "narrative-command-journal.ndjson"
    runtime = NarrativeRuntime(command_journal_path=journal)
    runtime.enable()
    runtime.admit(NarrativeCommand.shutdown("mediums:journal", 1_000, "application_exit"))
    runtime.reduce_next()
    assert journal.is_file()


def test_shutdown_without_tape_effect_completes_cleanly() -> None:
    runtime = NarrativeRuntime(tape_effect=None, tape_writer=None)
    runtime.enable()
    runtime.admit(NarrativeCommand.shutdown("mediums:no-tape", 2_000, "application_exit"))
    result = runtime.reduce_next()
    assert result is not None
    assert result.kind == "SHUTDOWN"
    assert "effect:flush_tape" not in result.effects
    assert result.runtime_state == "stopped"
    assert runtime.status().runtime_state == "stopped"


def test_http_tape_component_reports_enabled_false_when_writer_absent() -> None:
    projection = project_runtime_status(NarrativeRuntime().status())
    tape = projection["components"]["tape"]
    assert tape["status"] == "disabled"
    assert tape["enabled"] is False
