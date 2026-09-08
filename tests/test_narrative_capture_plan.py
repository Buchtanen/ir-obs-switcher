"""F44 CapturePlan compiler: policy matrix, purpose vs tape_channel, windows."""

from __future__ import annotations

import json
from pathlib import Path

from irswitch.commentary.capture_plan import (
    PURPOSE_CHANNELS,
    compile_capture_plan,
)
from irswitch.contracts.primitives import ContractViolation
from irswitch.contracts.resources import packaged_schema_bytes

ROOT = Path(__file__).resolve().parents[1]
FROZEN_MACHINE = ROOT / "docs" / "v2.0.0" / "machine"


def _packaged_catalog() -> dict[str, object]:
    return json.loads(packaged_schema_bytes("detector-catalog.json"))


def _catalog_with(*extra: dict[str, object]) -> dict[str, object]:
    catalog = _packaged_catalog()
    definitions = list(catalog["definitions"])
    for item in extra:
        definitions.append(
            {
                "id": item["id"],
                "version": item.get("version", 1),
                "experimental": item["experimental"],
                "tuningPolicy": item["tuningPolicy"],
                "output": {"tapeChannel": item.get("tape_channel", "race.timing.lap")},
                "parameters": item.get(
                    "parameters",
                    (
                        {
                            "id": "confirm_s",
                            "default": 1.0,
                            "minimum": 0.1,
                            "maximum": 5.0,
                            "type": "number",
                        },
                    ),
                ),
            }
        )
    catalog["definitions"] = definitions
    return catalog


def _required_enablement() -> dict[str, object]:
    return {
        "commentary.detectors.profile": "calibration",
        "commentary.detector.battle_ahead_v1.enabled": True,
        "commentary.tape.enabled": True,
        "commentary.tape.channels": ("flow", "detector_tuning"),
        "commentary.tape.detector_tuning.trigger_allowlist": ("battle_ahead_v1",),
        "commentary.tape.detector_tuning.capture_input_windows": True,
    }


def test_every_catalog_detector_has_an_explicit_effective_policy() -> None:
    plan = compile_capture_plan()

    assert plan.valid is True
    assert {entry.detector_id for entry in plan.detectors} == {
        "battle_ahead_v1",
        "battle_behind_v1",
        "battle_two_front_v1",
    }
    status = plan.startup_status()
    assert [row["detectorId"] for row in status] == [
        "battle_ahead_v1",
        "battle_behind_v1",
        "battle_two_front_v1",
    ]
    for entry, row in zip(plan.detectors, status, strict=True):
        assert entry.catalog_policy == "required"
        assert entry.effective_policy == "required"
        assert entry.enabled is False
        assert entry.capture_active is False
        assert entry.tape_channel
        assert set(entry.purpose_channels) <= PURPOSE_CHANNELS
        assert row["effectivePolicy"] == "required"
        assert row["captureActive"] is False
        assert row["tapeChannel"] == entry.tape_channel


def test_default_off_tape_keeps_released_none_and_optional_enabled() -> None:
    catalog = _catalog_with(
        {"id": "direct_flag_v1", "experimental": False, "tuningPolicy": "none"},
        {"id": "optional_pace_v1", "experimental": False, "tuningPolicy": "optional"},
    )
    plan = compile_capture_plan(
        {
            "commentary.tape.enabled": False,
            "commentary.detector.direct_flag_v1.enabled": True,
            "commentary.detector.optional_pace_v1.enabled": True,
        },
        catalog=catalog,
    )

    assert plan.valid is True
    assert plan.tape_enabled is False
    none = plan.entry("direct_flag_v1")
    optional = plan.entry("optional_pace_v1")
    assert none.enabled is True
    assert none.effective_policy == "none"
    assert none.capture_active is False
    assert none.forces_feature_windows is False
    assert none.evidence_completeness == "not_applicable"
    assert optional.enabled is True
    assert optional.effective_policy == "optional"
    assert optional.capture_active is False
    assert optional.evidence_completeness == "not_applicable"


def test_none_never_forces_high_volume_windows_even_when_tuning_channel_is_on() -> None:
    catalog = _catalog_with({"id": "direct_flag_v1", "experimental": False, "tuningPolicy": "none"})
    plan = compile_capture_plan(
        {
            "commentary.detector.direct_flag_v1.enabled": True,
            "commentary.tape.enabled": True,
            "commentary.tape.channels": ("flow", "detector_tuning"),
            "commentary.tape.detector_tuning.trigger_allowlist": ("direct_flag_v1",),
            "commentary.tape.detector_tuning.capture_input_windows": True,
        },
        catalog=catalog,
        preflight_ready=True,
    )

    entry = plan.entry("direct_flag_v1")
    assert entry.capture_active is False
    assert entry.forces_feature_windows is False
    assert entry.window.pre_window == "none"
    assert entry.window.post_window_s == 0.0
    assert entry.required_record_kinds == ()
    assert entry.required_fields == ()


def test_optional_captures_only_when_channel_and_allowlist_match() -> None:
    catalog = _catalog_with(
        {"id": "optional_pace_v1", "experimental": False, "tuningPolicy": "optional"}
    )
    inactive = compile_capture_plan(
        {
            "commentary.detector.optional_pace_v1.enabled": True,
            "commentary.tape.enabled": True,
            "commentary.tape.channels": ("flow",),
            "commentary.tape.detector_tuning.trigger_allowlist": ("optional_pace_v1",),
        },
        catalog=catalog,
    )
    active = compile_capture_plan(
        {
            "commentary.detector.optional_pace_v1.enabled": True,
            "commentary.tape.enabled": True,
            "commentary.tape.channels": ("flow", "detector_tuning"),
            "commentary.tape.detector_tuning.trigger_allowlist": ("optional_pace_v1",),
            "commentary.tape.detector_tuning.capture_input_windows": True,
        },
        catalog=catalog,
    )

    assert inactive.entry("optional_pace_v1").capture_active is False
    captured = active.entry("optional_pace_v1")
    assert captured.capture_active is True
    assert captured.evidence_completeness == "optional_may_gap"
    assert captured.window.pre_window == "complete_trend_window"
    assert captured.window.post_window_s == 5.0
    assert "detector_tuning" in captured.purpose_channels
    assert captured.tape_channel == "race.timing.lap"


def test_production_rejects_enabled_required_policy() -> None:
    plan = compile_capture_plan({"commentary.detector.battle_ahead_v1.enabled": True})

    assert plan.valid is False
    assert plan.entry("battle_ahead_v1").effective_policy == "required"
    assert plan.entry("battle_ahead_v1").capture_active is False
    assert any(
        item.reason == "required_requires_calibration" and item.detector_id == "battle_ahead_v1"
        for item in plan.diagnostics
    )


def test_nonexperimental_required_is_invalid_even_when_disabled() -> None:
    catalog = _catalog_with(
        {"id": "released_required_v1", "experimental": False, "tuningPolicy": "required"}
    )
    plan = compile_capture_plan(catalog=catalog)

    assert plan.valid is False
    assert any(
        item.reason == "required_not_experimental" and item.detector_id == "released_required_v1"
        for item in plan.diagnostics
    )


def test_calibration_required_plan_includes_windows_parameters_and_record_kinds() -> None:
    plan = compile_capture_plan(_required_enablement(), preflight_ready=True)
    entry = plan.entry("battle_ahead_v1")

    assert plan.valid is True
    assert entry.enabled is True
    assert entry.effective_policy == "required"
    assert entry.capture_active is True
    assert entry.experimental is True
    assert entry.forces_feature_windows is True
    assert entry.evidence_completeness == "required"
    assert entry.window.pre_window == "complete_trend_window"
    assert entry.window.post_window_s == 5.0
    assert entry.required_fields == (
        "coverage",
        "effectiveParameters",
        "featureQuality",
        "nearThresholdNegatives",
        "predicateTrace",
        "transitionReason",
    )
    assert entry.required_record_kinds == ("detector_observation", "feature_frame")
    assert entry.tape_channel == "race.battle.closing"
    assert entry.purpose_channels == ("detector_tuning", "flow")
    assert entry.parameter_snapshot_id is not None
    assert "trend_window_s" in entry.parameters
    snapshots = plan.parameter_snapshots()
    assert snapshots[0]["detectorId"] == "battle_ahead_v1"
    assert snapshots[0]["parameterSnapshotId"] == entry.parameter_snapshot_id


def test_required_without_preflight_does_not_activate_capture() -> None:
    plan = compile_capture_plan(_required_enablement(), preflight_ready=False)

    assert plan.valid is False
    assert plan.entry("battle_ahead_v1").capture_active is False
    assert any(item.reason == "required_requires_preflight" for item in plan.diagnostics)


def test_purpose_channels_are_validated_separately_from_tape_channel_allowlists() -> None:
    mixed_purpose = compile_capture_plan({"commentary.tape.channels": ("race.battle.closing",)})
    mixed_allowlist = compile_capture_plan(
        {"commentary.tape.flow.tape_channel_allowlist": ("flow",)}
    )
    required = compile_capture_plan(_required_enablement(), preflight_ready=True)
    flow_only = compile_capture_plan(
        {
            **_required_enablement(),
            "commentary.tape.flow.tape_channel_allowlist": ("race.battle.pressure",),
        },
        preflight_ready=True,
    )

    assert mixed_purpose.valid is False
    assert any(
        item.reason == "purpose_channel_is_not_tape_channel" for item in mixed_purpose.diagnostics
    )
    assert mixed_allowlist.valid is False
    assert any(
        item.reason == "tape_channel_is_not_purpose_channel" for item in mixed_allowlist.diagnostics
    )
    ahead = required.entry("battle_ahead_v1")
    assert ahead.tape_channel == "race.battle.closing"
    assert "flow" not in (ahead.tape_channel,)
    assert PURPOSE_CHANNELS.isdisjoint({ahead.tape_channel})
    filtered = flow_only.entry("battle_ahead_v1")
    assert "flow" not in filtered.purpose_channels
    assert "detector_tuning" in filtered.purpose_channels
    assert filtered.tape_channel == "race.battle.closing"


def test_capture_plan_is_immutable_and_does_not_import_runtime() -> None:
    source = Path(__file__).resolve().parents[1] / "src/irswitch/commentary/capture_plan.py"
    imports = [
        line
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "DetectorBank" not in joined
    assert "tape_writer" not in joined
    assert "overlay.tape" not in joined

    plan = compile_capture_plan()
    try:
        plan.detectors = ()  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("StreamCapturePlan must be frozen")
    assert plan.entry("battle_ahead_v1").effective_policy == "required"


def test_unknown_detector_lookup_is_a_contract_violation() -> None:
    plan = compile_capture_plan()
    try:
        plan.entry("not_a_detector")
    except ContractViolation as error:
        assert "not_a_detector" in str(error)
    else:
        raise AssertionError("unknown detector must fail closed")
