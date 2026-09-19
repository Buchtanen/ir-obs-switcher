"""#278 Slice 22 — offline F36 mixed-boundary config runtime drivers.

Consumes frozen machine rows and proves ConfigLedger + BeatPlanner + tape loss
+ CommentaryConfigCoordinator ownership of mixed-boundary apply groups, gen6
plan freeze, TTS no-old-backend admission, redacted manifest hashes, explicit
barrier loss, pending recomputation on revert, and invalid reload atomic
disable. Does not rewrite ``docs/v2.0.0/machine/*`` hashes and does not claim
live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_beat_plan import BeatPlanner, _intent
from test_narrative_tape_queue import _fill, _record
from test_v2_commentary_config import GOLDENS, ROOT, _candidate

from irswitch.commentary.tape_queue import TapeRecordQueue
from irswitch.config_reload import CommentaryConfigCoordinator
from irswitch.contracts.config import ConfigLedger, parse_commentary_mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
MACHINE = REPO_ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE22_IDS = ("F36",)
DYNAMIC_KEY = "commentary.detector.battle_ahead_v1.max_closing_slope"


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_config_boundary_builder_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]
    machine_path = str(MACHINE)
    if machine_path not in sys.path:
        sys.path.insert(0, machine_path)
    spec = importlib.util.spec_from_file_location(module_name, BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


@pytest.fixture(scope="module")
def fixtures_by_id() -> dict[str, dict[str, Any]]:
    bundle = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in bundle["fixtures"]}


@pytest.mark.parametrize("fixture_id", SLICE22_IDS)
def test_slice22_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f36_mixed_boundary_config_is_explicit_and_replayable(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F36: mixed-boundary config apply groups stay explicit and replayable."""

    expected = set(fixtures_by_id["F36"]["expectations"])
    observed: set[str] = set()
    scenario = GOLDENS["ledgerScenario"]

    initial = _candidate(**{DYNAMIC_KEY: -0.04})
    generation_7 = _candidate(
        **{
            DYNAMIC_KEY: -0.05,
            "commentary.director.selection_threshold": 42.0,
            "commentary.max_utterance_s": 12.0,
            "commentary.tts.backend": "supertonic",
            "commentary.tts.voice": "golden-voice",
            "commentary.tape.detail": "full",
        }
    )
    assert initial.snapshot is not None
    assert generation_7.snapshot is not None
    assert initial.snapshot.config_hash == scenario["initialEffectiveHash"]
    assert generation_7.snapshot.config_hash == scenario["generation7DesiredHash"]

    ledger = ConfigLedger(
        initial.snapshot,
        desired_generation=6,
        apply_sequence=20,
        ready_components=("tts",),
    )
    step = BeatPlanner().plan(
        _intent(
            effective_config_hash=ledger.effective_snapshot.config_hash,
            config_apply_sequence=ledger.apply_sequence,
        ),
        lane="idle",
        planning_cycle_id="f36",
    )
    assert step.plan is not None
    assert step.plan.effective_config_hash == scenario["initialEffectiveHash"]
    assert step.plan.config_apply_sequence == 20

    outcome = ledger.install(generation_7)
    assert outcome.installed is True
    assert ledger.desired_generation == 7
    assert ledger.desired_snapshot.config_hash == scenario["generation7DesiredHash"]
    assert ledger.effective_snapshot.config_hash == scenario["initialEffectiveHash"]
    assert step.plan.effective_config_hash == scenario["initialEffectiveHash"]
    assert step.plan.config_apply_sequence == 20
    assert [(item.component, item.generation) for item in outcome.preflights] == [("tts", 7)]
    assert [
        {
            "component": item.component,
            "generation": item.generation,
            "status": "pending",
        }
        for item in outcome.preflights
    ] == scenario["preflightsStarted"]
    observed.add("old_plan_keeps_gen6")

    applied = []
    for transition in scenario["appliedTransitions"]:
        actual = ledger.apply_boundary(transition["boundary"])
        assert actual is not None
        assert actual.apply_sequence == transition["applySequence"]
        assert actual.desired_generation == transition["desiredGeneration"]
        assert actual.changed_keys == tuple(transition["changedKeys"])
        assert actual.old_effective_hash == transition["oldEffectiveHash"]
        assert actual.new_effective_hash == transition["newEffectiveHash"]
        patch = [
            (
                {"key": item.key, "redacted": True}
                if item.redacted
                else {"key": item.key, "value": item.value}
            )
            for item in actual.effective_patch
        ]
        assert patch == transition["effectivePatch"]
        applied.append(actual)

    assert [
        {
            "key": item.key,
            "boundary": item.boundary,
            "desiredGeneration": item.desired_generation,
        }
        for item in ledger.pending_changes
    ] == scenario["pendingAfterAvailableBoundaries"]
    assert {
        transition["boundary"]: tuple(transition["changedKeys"])
        for transition in scenario["appliedTransitions"]
    } == {
        "next_record": ("commentary.tape.detail",),
        "next_director_pass": ("commentary.director.selection_threshold",),
        "next_plan_or_manual": ("commentary.max_utterance_s",),
        "next_utterance": ("commentary.tts.backend", "commentary.tts.voice"),
    }
    observed.add("exact_boundary_groups")

    assert ledger.effective_snapshot.values["commentary.tts.backend"] == "supertonic"
    assert ledger.component_available("tts", 7) is False
    assert ledger.component_available("tts", 6) is False
    assert ledger.record_preflight("tts", 6, success=True) is False
    assert ledger.component_available("tts", 6) is False
    assert ledger.record_preflight("tts", 7, success=True) is True
    assert ledger.component_available("tts", 7) is True
    assert (
        scenario["firstGeneration7TtsAdmission"]
        == "component_unavailable_no_old_generation_fallback"
    )
    assert scenario["currentPreflightSuccessEffect"] == "later_normal_admission_only"
    observed.add("no_old_backend")

    assert (
        ledger.effective_snapshot.config_hash == scenario["effectiveAfterAvailableBoundariesHash"]
    )
    assert ledger.apply_sequence == 24
    assert applied[-1].effective_patch[-1].redacted is True
    observed.add("manifest_snapshot")

    queue = TapeRecordQueue(capacity=1)
    _fill(
        queue,
        _record("critical:held", "health_change", "critical", reducer_sequence=7),
    )
    last = applied[-1]
    queue.note_config_transition_lost(
        apply_sequence=last.apply_sequence,
        old_effective_hash=last.old_effective_hash,
        new_effective_hash=last.new_effective_hash,
        recorded_mono_ms=1800,
    )
    loss = queue.loss_snapshot()
    assert loss is not None
    assert loss["configTransitions"] == [
        {
            "applySequence": last.apply_sequence,
            "oldEffectiveHash": last.old_effective_hash,
            "newEffectiveHash": last.new_effective_hash,
        }
    ]
    assert any(bucket["reason"] == "config_transition_lost" for bucket in loss["buckets"])
    observed.add("barrier_loss_explicit")

    generation_8_values = dict(generation_7.snapshot.to_dict())
    generation_8_values[DYNAMIC_KEY] = -0.04
    generation_8 = parse_commentary_mapping(generation_8_values, repository_root=ROOT)
    assert generation_8.valid is True
    ledger.install(generation_8)
    assert ledger.desired_snapshot.config_hash == scenario["generation8DesiredHash"]
    assert ledger.desired_generation == 8
    assert list(ledger.pending_changes) == []
    assert scenario["pendingAfterGeneration8Revert"] == []
    observed.add("pending_recomputed")

    enabled_initial = _candidate(**{"commentary.enabled": True, DYNAMIC_KEY: -0.04})
    coordinator = CommentaryConfigCoordinator.bootstrap(enabled_initial, ready_components=("tts",))
    assert coordinator.automatic_enabled is True
    enabled_generation_7 = _candidate(
        **{
            "commentary.enabled": True,
            DYNAMIC_KEY: -0.05,
            "commentary.director.selection_threshold": 42.0,
            "commentary.max_utterance_s": 12.0,
            "commentary.tts.backend": "supertonic",
            "commentary.tts.voice": "golden-voice",
            "commentary.tape.detail": "full",
        }
    )
    installed = coordinator.install(enabled_generation_7)
    assert installed.installed is True
    desired_before = coordinator.ledger.desired_generation
    for transition in scenario["appliedTransitions"]:
        coordinator.ledger.apply_boundary(transition["boundary"])
    for preflight in installed.preflights:
        assert (
            coordinator.ledger.record_preflight(
                preflight.component, preflight.generation, success=True
            )
            is True
        )
    assert coordinator.ledger.effective_snapshot.values["commentary.tts.backend"] == "supertonic"
    assert coordinator.automatic_enabled is True

    invalid = parse_commentary_mapping({"commentary.magic": True}, repository_root=ROOT)
    assert invalid.valid is False
    rejected = coordinator.install(invalid)
    assert rejected.installed is False
    assert rejected.automatic_enabled is False
    assert coordinator.ledger.desired_generation == desired_before
    assert coordinator.automatic_enabled is False
    assert coordinator.ledger.component_available("tts", desired_before) is True
    assert coordinator.ledger.effective_snapshot.values["commentary.tts.backend"] == "supertonic"
    assert (
        scenario["invalidReloadEffect"]
        == "no_generation_disable_automatic_preserve_last_valid_manual_backend"
    )
    observed.add("invalid_no_generation")
    observed.add("atomic_disable")

    assert observed == expected
