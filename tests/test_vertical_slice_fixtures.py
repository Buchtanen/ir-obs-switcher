"""#278 Slice 1 — offline consumer of frozen F01–F44 vertical-slice fixtures.

Loads the checked-in machine projection and re-runs the builder validator.
Does not rewrite frozen ``docs/v2.0.0/machine/*`` hashes and does not claim
live Windows §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
MUTATIONS_PATH = MACHINE / "vertical-slice-mutations.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

# Named F scenarios already covered by adjacent unit tests (docstring inventory).
WIRED_UNIT_COVERAGE: dict[str, tuple[str, ...]] = {
    "F01": ("tests/test_vertical_slice_silence_runtime.py",),
    "F02": ("tests/test_vertical_slice_transition_runtime.py",),
    "F03": ("tests/test_vertical_slice_transition_runtime.py",),
    "F04": ("tests/test_vertical_slice_transition_runtime.py",),
    "F05": ("tests/test_vertical_slice_scoring_runtime.py",),
    "F06": ("tests/test_vertical_slice_scoring_runtime.py",),
    "F07": ("tests/test_vertical_slice_scoring_runtime.py",),
    "F08": ("tests/test_vertical_slice_expiry_runtime.py",),
    "F09": ("tests/test_vertical_slice_qwen_runtime.py",),
    "F10": ("tests/test_vertical_slice_silence_runtime.py",),
    "F11": ("tests/test_vertical_slice_qwen_runtime.py",),
    "F12": ("tests/test_vertical_slice_manual_lexicon_runtime.py",),
    "F29": ("tests/test_vertical_slice_manual_lexicon_runtime.py",),
    "F32": ("tests/test_vertical_slice_facts_freshness_runtime.py",),
    "F38": ("tests/test_vertical_slice_facts_freshness_runtime.py",),
    "F13": ("tests/test_vertical_slice_mailbox_manual_runtime.py",),
    "F20": ("tests/test_vertical_slice_mailbox_manual_runtime.py",),
    "F15": ("tests/test_vertical_slice_expiry_runtime.py",),
    "F17": ("tests/test_vertical_slice_silence_runtime.py",),
    "F21": ("tests/test_vertical_slice_partition_silence_runtime.py",),
    "F22": ("tests/test_stream_timeline.py",),
    "F23": ("tests/test_vertical_slice_policy_runtime.py",),
    "F24": ("tests/test_vertical_slice_expiry_runtime.py",),
    "F25": ("tests/test_stream_timeline.py",),
    "F27": ("tests/test_narrative_tape_queue.py",),
    "F31": ("tests/test_stream_timeline.py",),
    "F34": ("tests/test_narrative_tape_replay.py",),
    "F37": ("tests/test_vertical_slice_policy_runtime.py",),
    "F42": ("tests/test_vertical_slice_partition_silence_runtime.py",),
    "F44": (
        "tests/test_narrative_capture_plan.py",
        "tests/test_narrative_capture_safety.py",
    ),
}


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_fixtures_builder_under_test"
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
def fixture_bundle() -> dict[str, Any]:
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def mutations() -> list[dict[str, str]]:
    return json.loads(MUTATIONS_PATH.read_text(encoding="utf-8"))


def test_frozen_vertical_slice_artifacts_match_builder(
    fixture_bundle: dict[str, Any], mutations: list[dict[str, str]]
) -> None:
    assert builder.canonical(fixture_bundle) == builder.canonical(builder.build_fixtures())
    assert builder.canonical(mutations) == builder.canonical(builder.build_mutations())


def test_vertical_slice_fixture_counts_and_ids(fixture_bundle: dict[str, Any]) -> None:
    fixtures = fixture_bundle["fixtures"]
    assert [row["id"] for row in fixtures] == [f"F{n:02d}" for n in range(1, 45)]
    assert len(fixtures) == 44
    expectation_count = sum(len(row["expectations"]) for row in fixtures)
    calculation_count = sum(len(row["calculations"]) for row in fixtures)
    assert expectation_count == 248
    assert calculation_count == 14
    for row in fixtures:
        assert len(row["contractHashes"]) == 7


def test_vertical_slice_validate_all_accepts_frozen_bundle(
    fixture_bundle: dict[str, Any], mutations: list[dict[str, str]]
) -> None:
    builder.validate_all(fixture_bundle, mutations)


def test_vertical_slice_mutations_are_fail_closed(
    fixture_bundle: dict[str, Any], mutations: list[dict[str, str]]
) -> None:
    assert len(mutations) == 16
    for mutation in mutations:
        errors = builder.fixture_errors(builder.mutate(fixture_bundle, mutation["id"]))
        assert errors, mutation["id"]
        assert mutation["errorContains"] in errors[0]


def test_vertical_slice_gap_inventory_lists_unwired_runtime_scenarios(
    fixture_bundle: dict[str, Any],
) -> None:
    """Inventory: machine harness covers all 44; runtime unit wiring grows per slice."""

    all_ids = {row["id"] for row in fixture_bundle["fixtures"]}
    assert set(WIRED_UNIT_COVERAGE) <= all_ids
    unwired = sorted(all_ids - set(WIRED_UNIT_COVERAGE))
    assert len(unwired) == 14
    assert "F09" not in unwired
    assert "F11" not in unwired
    assert "F12" not in unwired
    assert "F29" not in unwired
    assert "F32" not in unwired
    assert "F38" not in unwired
    assert "F13" not in unwired
    assert "F20" not in unwired
    assert "F21" not in unwired
    assert "F23" not in unwired
    assert "F37" not in unwired
    assert "F42" not in unwired
    assert "F01" not in unwired
    assert "F10" not in unwired
    assert "F17" not in unwired
    assert "F05" not in unwired
    assert "F06" not in unwired
    assert "F07" not in unwired
    assert "F02" not in unwired
    assert "F03" not in unwired
    assert "F04" not in unwired
    assert "F08" not in unwired
    assert "F15" not in unwired
    assert "F24" not in unwired
    # Named coverage stays an explicit allow-list so later slices shrink it deliberately.
    assert WIRED_UNIT_COVERAGE["F44"] == (
        "tests/test_narrative_capture_plan.py",
        "tests/test_narrative_capture_safety.py",
    )
    assert WIRED_UNIT_COVERAGE["F01"] == ("tests/test_vertical_slice_silence_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F02"] == ("tests/test_vertical_slice_transition_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F05"] == ("tests/test_vertical_slice_scoring_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F08"] == ("tests/test_vertical_slice_expiry_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F09"] == ("tests/test_vertical_slice_qwen_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F11"] == ("tests/test_vertical_slice_qwen_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F12"] == ("tests/test_vertical_slice_manual_lexicon_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F29"] == ("tests/test_vertical_slice_manual_lexicon_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F32"] == ("tests/test_vertical_slice_facts_freshness_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F38"] == ("tests/test_vertical_slice_facts_freshness_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F13"] == ("tests/test_vertical_slice_mailbox_manual_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F20"] == ("tests/test_vertical_slice_mailbox_manual_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F10"] == ("tests/test_vertical_slice_silence_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F17"] == ("tests/test_vertical_slice_silence_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F21"] == ("tests/test_vertical_slice_partition_silence_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F23"] == ("tests/test_vertical_slice_policy_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F42"] == ("tests/test_vertical_slice_partition_silence_runtime.py",)
    assert WIRED_UNIT_COVERAGE["F37"] == ("tests/test_vertical_slice_policy_runtime.py",)
