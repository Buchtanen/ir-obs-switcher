"""Executable acceptance for the frozen v2 commentary config candidate."""

from __future__ import annotations

import configparser
import json
from pathlib import Path

import pytest

from irswitch.contracts.config import parse_commentary_ini, parse_commentary_mapping
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
