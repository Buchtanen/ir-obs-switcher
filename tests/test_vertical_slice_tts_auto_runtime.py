"""#278 Slice 17 — offline F30 TTS auto-resolution drivers.

Consumes frozen machine rows and proves ``speech_lane`` ownership of auto
backend snapshotting: auto prefers SAPI over eSpeak, never fails over the same
utterance text, later rebuilds may pick another backend only with a higher
generation, and SuperTonic is explicit-only. Does not rewrite
``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_speech_lane import _cb, _intent

from irswitch.events.speech_lane import (
    AUTO_BACKEND_ORDER,
    EXPLICIT_ONLY,
    SpeechLane,
    resolve_backend,
)

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE17_IDS = ("F30",)


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_tts_auto_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE17_IDS)
def test_slice17_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f30_tts_auto_resolution_never_retries_an_utterance(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F30: auto snapshots SAPI; failure never fails over; SuperTonic is explicit."""

    expected = set(fixtures_by_id["F30"]["expectations"])
    observed: set[str] = set()

    assert AUTO_BACKEND_ORDER == ("sapi", "espeak")
    assert resolve_backend("auto", available=("espeak", "sapi")) == "sapi"

    lane = SpeechLane()
    opened = lane.try_start(
        _intent(
            backend="auto",
            available_backends=("sapi", "espeak"),
            backend_generation=4,
            config_generation=4,
            text="Hold the inside line.",
        )
    )
    assert opened.utterance is not None
    assert opened.utterance.backend == "sapi"
    assert opened.utterance.backend_generation == 4
    # Utterance freezes the resolved backend/generation; text stays on the intent.
    snapshot = opened.utterance
    observed.add("snapshot_sapi")

    lane.commit("utt:1", now_ms=10_100)
    failed = lane.callback(_cb("failed", backend="sapi", detail="backend_timeout", sequence=1))
    assert failed.reason == "speech_failed"
    assert failed.failover_attempted is False
    assert lane.lane == "idle"
    # Same utterance must not be re-dispatched to eSpeak after the SAPI failure.
    assert snapshot.backend == "sapi"
    assert lane.lane == "idle"
    observed.add("no_same_text_fallback")

    later = SpeechLane()
    rebuilt = later.try_start(
        _intent(
            utterance_id="utt:2",
            backend="auto",
            available_backends=("espeak",),
            backend_generation=5,
            config_generation=5,
            text="Hold the inside line.",
        )
    )
    assert rebuilt.utterance is not None
    assert rebuilt.utterance.backend == "espeak"
    assert rebuilt.utterance.backend_generation == 5
    assert rebuilt.utterance.backend_generation > snapshot.backend_generation
    observed.add("later_generation_only")

    assert "supertonic" in EXPLICIT_ONLY
    assert resolve_backend("auto", available=("supertonic", "sapi")) == "sapi"
    assert resolve_backend("auto", available=("supertonic",)) is None
    assert resolve_backend("supertonic", available=("supertonic",)) == "supertonic"
    explicit = SpeechLane().try_start(
        _intent(
            utterance_id="utt:3",
            backend="supertonic",
            available_backends=("supertonic", "sapi", "espeak"),
            adapter="supertonic",
            backend_generation=6,
        )
    )
    assert explicit.utterance is not None
    assert explicit.utterance.backend == "supertonic"
    observed.add("supertonic_explicit")

    assert observed == expected
