"""Executable acceptance for the frozen v2 commentary config candidate."""

from __future__ import annotations

import configparser
import json
from pathlib import Path

import pytest

from irswitch.contracts.config import ConfigLedger, parse_commentary_ini, parse_commentary_mapping
from irswitch.contracts.resources import packaged_schema_bytes

ROOT = Path(__file__).resolve().parents[1]
GOLDENS = json.loads((ROOT / "docs/v2.0.0/machine/config-goldens.json").read_text(encoding="utf-8"))


def test_absent_commentary_section_matches_every_frozen_default() -> None:
    parser = configparser.ConfigParser()

    candidate = parse_commentary_ini(parser, repository_root=ROOT)

    assert candidate.valid is True
    assert candidate.diagnostics == ()
    assert candidate.snapshot is not None
    assert candidate.snapshot.to_dict() == GOLDENS["valid"][0]["values"]
    assert candidate.snapshot.values["commentary.enabled"] is False
    with pytest.raises(TypeError):
        candidate.snapshot.values["commentary.enabled"] = True  # type: ignore[index]


def test_packaged_config_and_detector_contracts_match_the_frozen_sources() -> None:
    for name in ("config-contract.json", "detector-catalog.json"):
        assert json.loads(packaged_schema_bytes(name)) == json.loads(
            (ROOT / f"docs/v2.0.0/machine/{name}").read_bytes()
        )


def test_enabled_private_llm_full_capture_golden_is_accepted() -> None:
    fixture = GOLDENS["valid"][1]

    candidate = parse_commentary_mapping(fixture["values"], repository_root=ROOT)

    assert candidate.valid is True
    assert candidate.snapshot is not None
    for key, value in fixture["values"].items():
        expected = tuple(value) if isinstance(value, list) else value
        assert candidate.snapshot.values[key] == expected


@pytest.mark.parametrize("fixture", GOLDENS["invalid"], ids=lambda row: row["id"])
def test_frozen_invalid_mapping_goldens_fail_closed(fixture: dict[str, object]) -> None:
    candidate = parse_commentary_mapping(fixture["values"], repository_root=ROOT)

    assert candidate.valid is False
    assert candidate.snapshot is None
    assert fixture["errorContains"] in " ".join(item.message for item in candidate.diagnostics)


def test_strict_ini_scalar_grammar_and_normalization() -> None:
    parser = configparser.ConfigParser()
    parser.read_string("""
[commentary]
enabled = true
driver_name =  Max   Mustermann

[commentary.llm]
timeout_s = 1.25
max_tokens = 128

[commentary.tape]
channels = llm_eval, flow
""")

    candidate = parse_commentary_ini(parser, repository_root=ROOT)

    assert candidate.valid is True
    assert candidate.snapshot is not None
    assert candidate.snapshot.values["commentary.driver_name"] == "Max Mustermann"
    assert candidate.snapshot.values["commentary.llm.timeout_s"] == 1.25
    assert candidate.snapshot.values["commentary.llm.max_tokens"] == 128
    assert candidate.snapshot.values["commentary.tape.channels"] == ("flow", "llm_eval")


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("commentary.enabled", "yes", "must be exactly true or false"),
        ("commentary.llm.max_tokens", "1e2", "base-10 integer"),
        ("commentary.llm.timeout_s", "NaN", "finite base-10 number"),
        ("commentary.tape.channels", "flow, flow", "duplicate set member"),
    ],
)
def test_strict_ini_rejects_permissive_configparser_forms(
    key: str, value: str, message: str
) -> None:
    section, option = key.rsplit(".", 1)
    parser = configparser.ConfigParser()
    parser.read_dict({section: {option: value}})

    candidate = parse_commentary_ini(parser, repository_root=ROOT)

    assert candidate.valid is False
    assert candidate.snapshot is None
    assert message in " ".join(item.message for item in candidate.diagnostics)


@pytest.mark.parametrize(
    ("section", "option", "replacement"),
    [
        ("commentary", "decision_log_size", "commentary.director.decision_capacity"),
        ("commentary.graph_runtime", "mode", None),
    ],
)
def test_legacy_keys_diagnose_but_never_install_a_candidate(
    section: str, option: str, replacement: str | None
) -> None:
    parser = configparser.ConfigParser()
    parser.read_dict({section: {option: "32"}})

    candidate = parse_commentary_ini(parser, repository_root=ROOT)

    assert candidate.valid is False
    assert candidate.snapshot is None
    assert candidate.diagnostics[0].reason == "legacy_key"
    assert replacement in candidate.diagnostics[0].replacement_keys if replacement else True


def test_every_frozen_v1_migration_row_has_runtime_diagnostic_coverage() -> None:
    contract = json.loads(packaged_schema_bytes("config-contract.json"))
    entries = contract["migrationContract"]["entries"]

    assert len(entries) == 13
    exercised_sources: list[str] = []
    for entry in entries:
        match_kind = entry["matchKind"]
        source = entry["source"]
        if match_kind == "group":
            keys = [
                key.replace("commentary.llm.", "commentary.llm_")
                for key in entry["replacementKeys"]
            ]
        elif match_kind == "prefix":
            keys = [source.removesuffix("*") + "representative"]
        else:
            keys = [source]

        for key in keys:
            if match_kind == "section":
                parser = configparser.ConfigParser()
                parser.read_dict({key.removeprefix("[").removesuffix("]"): {"legacy": "1"}})
                candidate = parse_commentary_ini(parser, repository_root=ROOT)
            else:
                candidate = parse_commentary_mapping({key: "legacy"}, repository_root=ROOT)

            assert candidate.valid is False
            assert candidate.snapshot is None
            assert candidate.diagnostics == (candidate.diagnostics[0],)
            diagnostic = candidate.diagnostics[0]
            assert diagnostic.reason == entry["diagnosticReason"]
            assert diagnostic.source_key == key
            assert diagnostic.replacement_keys == tuple(entry["replacementKeys"])
            assert entry["result"] in diagnostic.message
            exercised_sources.append(key)

    assert len(exercised_sources) == 16


def test_real_normalized_sensitive_values_participate_in_hash() -> None:
    first = parse_commentary_mapping({"commentary.driver_name": "Alice"}, repository_root=ROOT)
    second = parse_commentary_mapping({"commentary.driver_name": "Bob"}, repository_root=ROOT)

    assert first.snapshot is not None
    assert second.snapshot is not None
    assert first.snapshot.config_hash != second.snapshot.config_hash
    assert first.snapshot.replay_values()["commentary.driver_name"] == {"redacted": True}


def test_exported_detector_override_uses_catalog_type_and_range() -> None:
    valid = parse_commentary_mapping(
        {"commentary.detector.battle_ahead_v1.max_closing_slope": -0.08},
        repository_root=ROOT,
    )
    invalid = parse_commentary_mapping(
        {"commentary.detector.battle_ahead_v1.max_closing_slope": -0.5},
        repository_root=ROOT,
    )
    unknown = parse_commentary_mapping(
        {"commentary.detector.not_exported.enabled": True}, repository_root=ROOT
    )

    assert valid.valid is True
    assert invalid.valid is False
    assert "out of range" in invalid.diagnostics[0].message
    assert unknown.valid is False
    assert "unknown config key" in unknown.diagnostics[0].message


def test_local_url_without_explicit_port_and_ipv6_literal_are_valid() -> None:
    no_port = parse_commentary_mapping(
        {"commentary.llm.base_url": "http://127.0.0.1/v1"}, repository_root=ROOT
    )
    ipv6 = parse_commentary_mapping(
        {"commentary.llm.base_url": "http://[fd00::7]:11434//v1"}, repository_root=ROOT
    )

    assert no_port.valid is True
    assert ipv6.valid is True
    assert ipv6.snapshot is not None
    assert ipv6.snapshot.values["commentary.llm.base_url"] == "http://[fd00::7]:11434/v1"


@pytest.mark.parametrize("host", ["192.0.2.1", "203.0.113.9", "0.0.0.0", "2001:db8::1"])
def test_non_rfc1918_or_non_unique_local_literals_are_rejected(host: str) -> None:
    authority = f"[{host}]" if ":" in host else host

    candidate = parse_commentary_mapping(
        {"commentary.llm.base_url": f"http://{authority}:11434/v1"},
        repository_root=ROOT,
    )

    assert candidate.valid is False
    assert "URL outside local/LAN" in candidate.diagnostics[0].message


def test_relative_output_path_rejects_existing_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    working = tmp_path / "working"
    working.mkdir()
    (working / "escape").symlink_to(outside, target_is_directory=True)

    candidate = parse_commentary_mapping(
        {"commentary.tape.output_dir": "escape/records"},
        repository_root=ROOT,
        working_directory=working,
        home_directory=tmp_path / "home",
    )

    assert candidate.valid is False
    assert "symlink outside output parent" in candidate.diagnostics[0].message


def test_default_output_path_is_also_checked_against_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    working = tmp_path / "working"
    working.mkdir()
    (working / "recordings").symlink_to(outside, target_is_directory=True)

    candidate = parse_commentary_mapping(
        {},
        repository_root=ROOT,
        working_directory=working,
        home_directory=tmp_path / "home",
    )

    assert candidate.valid is False
    assert "symlink outside output parent" in candidate.diagnostics[0].message


def test_directional_detector_cross_field_invariants_are_exact() -> None:
    invalid = parse_commentary_mapping(
        {
            "commentary.detector.battle_ahead_v1.sample_interval_s": 0.75,
            "commentary.detector.battle_ahead_v1.bucket_s": 0.5,
        },
        repository_root=ROOT,
    )

    assert invalid.valid is False
    assert "sample_interval_s < bucket_s <= trend_window_s" in invalid.diagnostics[0].message


def test_required_tuning_detector_needs_calibration_capture_preflight() -> None:
    values = {
        "commentary.detector.battle_ahead_v1.enabled": True,
        "commentary.detectors.profile": "calibration",
        "commentary.tape.enabled": True,
        "commentary.tape.channels": ["flow", "detector_tuning"],
        "commentary.tape.detector_tuning.trigger_allowlist": ["battle_ahead_v1"],
        "commentary.tape.detector_tuning.capture_input_windows": True,
    }

    missing_preflight = parse_commentary_mapping(values, repository_root=ROOT)
    ready = parse_commentary_mapping(
        values, repository_root=ROOT, detector_capture_preflight_ready=True
    )

    assert missing_preflight.valid is False
    assert "writable recorder preflight" in missing_preflight.diagnostics[0].message
    assert ready.valid is True


def _candidate(**values: object):
    candidate = parse_commentary_mapping(values, repository_root=ROOT)
    assert candidate.valid is True
    return candidate


def test_ledger_installs_whole_candidate_and_recomputes_sorted_pending() -> None:
    initial = _candidate()
    assert initial.snapshot is not None
    ledger = ConfigLedger(
        initial.snapshot,
        desired_generation=6,
        apply_sequence=20,
        ready_components=("llm", "tts"),
    )
    candidate = _candidate(
        **{
            "commentary.detector.battle_ahead_v1.max_closing_slope": -0.08,
            "commentary.director.selection_threshold": 42.0,
            "commentary.max_utterance_s": 12.0,
            "commentary.tape.detail": "full",
            "commentary.tts.backend": "supertonic",
            "commentary.tts.voice": "M1",
        }
    )

    outcome = ledger.install(candidate)

    assert outcome.installed is True
    assert outcome.desired_generation == 7
    assert [(item.component, item.generation) for item in outcome.preflights] == [("tts", 7)]
    assert [item.key for item in ledger.pending_changes] == sorted(
        item.key for item in ledger.pending_changes
    )
    assert {item.boundary for item in ledger.pending_changes} == {
        "next_director_pass",
        "next_plan_or_manual",
        "next_record",
        "next_stream",
        "next_utterance",
    }
    assert ledger.effective_snapshot == initial.snapshot


def test_ledger_applies_only_matching_boundary_and_never_emits_noop() -> None:
    initial = _candidate()
    changed = _candidate(**{"commentary.tape.detail": "full"})
    assert initial.snapshot is not None
    ledger = ConfigLedger(initial.snapshot, desired_generation=6, apply_sequence=20)
    ledger.install(changed)

    assert ledger.apply_boundary("next_stream") is None
    record = ledger.apply_boundary("next_record")

    assert record is not None
    assert record.apply_sequence == 21
    assert record.desired_generation == 7
    assert record.changed_keys == ("commentary.tape.detail",)
    assert record.effective_patch[0].value == "full"
    assert record.effective_patch[0].redacted is False
    assert ledger.pending_changes == ()


def test_ledger_revert_recomputes_pending_from_whole_desired_map() -> None:
    initial = _candidate()
    changed = _candidate(**{"commentary.driver_name": "Alice"})
    assert initial.snapshot is not None
    ledger = ConfigLedger(initial.snapshot, desired_generation=6)
    ledger.install(changed)
    assert len(ledger.pending_changes) == 1

    ledger.install(initial)

    assert ledger.desired_generation == 8
    assert ledger.pending_changes == ()


def test_ledger_stale_preflight_cannot_make_old_generation_available() -> None:
    initial = _candidate()
    generation_7 = _candidate(**{"commentary.tts.voice": "M1"})
    generation_8 = _candidate(**{"commentary.tts.voice": "M2"})
    assert initial.snapshot is not None
    ledger = ConfigLedger(initial.snapshot, desired_generation=6, ready_components=("tts",))
    ledger.install(generation_7)
    ledger.install(generation_8)

    assert ledger.record_preflight("tts", 7, success=True) is False
    assert ledger.component_available("tts", 7) is False
    assert ledger.component_available("tts", 8) is False
    assert ledger.record_preflight("tts", 8, success=True) is True
    assert ledger.component_available("tts", 8) is True


def test_invalid_candidate_installs_no_generation_and_disables_automatic_only() -> None:
    initial = _candidate()
    invalid = parse_commentary_mapping({"commentary.magic": True}, repository_root=ROOT)
    assert initial.snapshot is not None
    ledger = ConfigLedger(initial.snapshot, desired_generation=6, ready_components=("tts",))

    outcome = ledger.install(invalid)

    assert outcome.installed is False
    assert outcome.desired_generation == 6
    assert outcome.automatic_enabled is False
    assert ledger.desired_generation == 6
    assert ledger.component_available("tts", 6) is True


def test_ledger_reproduces_the_frozen_mixed_boundary_hash_chain() -> None:
    scenario = GOLDENS["ledgerScenario"]
    dynamic_key = "commentary.detector.battle_ahead_v1.max_closing_slope"
    initial = _candidate(**{dynamic_key: -0.04})
    generation_7 = _candidate(
        **{
            dynamic_key: -0.05,
            "commentary.director.selection_threshold": 42.0,
            "commentary.max_utterance_s": 12.0,
            "commentary.tts.backend": "supertonic",
            "commentary.tts.voice": "golden-voice",
            "commentary.tape.detail": "full",
        }
    )
    assert initial.snapshot is not None
    ledger = ConfigLedger(initial.snapshot, desired_generation=6, apply_sequence=20)

    outcome = ledger.install(generation_7)

    assert ledger.effective_snapshot.config_hash == scenario["initialEffectiveHash"]
    assert ledger.desired_snapshot.config_hash == scenario["generation7DesiredHash"]
    assert [(item.component, item.generation) for item in outcome.preflights] == [("tts", 7)]
    for expected in scenario["appliedTransitions"]:
        actual = ledger.apply_boundary(expected["boundary"])
        assert actual is not None
        assert actual.apply_sequence == expected["applySequence"]
        assert actual.changed_keys == tuple(expected["changedKeys"])
        assert actual.old_effective_hash == expected["oldEffectiveHash"]
        assert actual.new_effective_hash == expected["newEffectiveHash"]
    assert [
        {
            "key": item.key,
            "boundary": item.boundary,
            "desiredGeneration": item.desired_generation,
        }
        for item in ledger.pending_changes
    ] == scenario["pendingAfterAvailableBoundaries"]

    generation_8_values = generation_7.snapshot.to_dict() if generation_7.snapshot else {}
    generation_8_values[dynamic_key] = -0.04
    generation_8 = parse_commentary_mapping(generation_8_values, repository_root=ROOT)
    ledger.install(generation_8)

    assert ledger.desired_snapshot.config_hash == scenario["generation8DesiredHash"]
    assert ledger.pending_changes == ()
