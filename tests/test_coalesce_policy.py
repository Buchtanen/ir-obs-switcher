"""Health/deadline coalesce allowlist is identical across runtime and model."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from irswitch.contracts.coalesce_policy import (
    COALESCE_FIELD_PATHS,
    DEADLINE_COALESCE_FIELDS,
    HEALTH_COALESCE_FIELDS,
)
from irswitch.contracts.command import NarrativeCommand

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
BUILDER_PATH = MACHINE / "build_actor_transition_model.py"


def _load_builder():
    module_name = "irswitch_actor_transition_builder_coalesce_under_test"
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


def test_health_and_deadline_lists_compose_identical_allowlist() -> None:
    assert COALESCE_FIELD_PATHS == {**DEADLINE_COALESCE_FIELDS, **HEALTH_COALESCE_FIELDS}
    assert set(DEADLINE_COALESCE_FIELDS) | set(HEALTH_COALESCE_FIELDS) == set(COALESCE_FIELD_PATHS)
    assert set(DEADLINE_COALESCE_FIELDS).isdisjoint(HEALTH_COALESCE_FIELDS)


def test_runtime_coalesce_paths_match_actor_transition_model() -> None:
    builder = _load_builder()
    assert builder.COALESCE == {kind: list(paths) for kind, paths in COALESCE_FIELD_PATHS.items()}


def test_command_coalesce_key_uses_shared_policy() -> None:
    silence = NarrativeCommand.deadline(
        "c:silence",
        "LONG_SILENCE_ELAPSED",
        10,
        generation=4,
        deadline_mono_ms=100,
    )
    assert silence.coalesce_key == ("LONG_SILENCE_ELAPSED", 4)
    health = NarrativeCommand.component_health(
        "c:health",
        11,
        component="tts",
        generation=2,
        status="ready",
        reason=None,
    )
    assert health.coalesce_key == ("COMPONENT_HEALTH_CHANGED", "tts", 2, "ready")
    assert "APPLY_CONTEXT_BATCH" not in COALESCE_FIELD_PATHS
