"""Event catalog ↔ V4 manifest state wiring (S0/S1 gate)."""

from __future__ import annotations

import json

import pytest

from irswitch.events.adapters import _ADAPTERS
from irswitch.events.event_catalog import (
    catalog_entries,
    catalog_fallbacks,
    catalog_path,
    debug_key_for_event_type,
    event_type_for_debug_key,
    load_v4_manifest,
    state_for_event_type,
)
from irswitch.events.manager import DEBUG_EVENT_NAMES
from irswitch.overlay.http import web_root
from irswitch.overlay.protocol import RaceEvent


def _manifest_states() -> dict[str, dict]:
    return load_v4_manifest()["states"]


def test_event_catalog_file_exists_and_version() -> None:
    data = json.loads(catalog_path().read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["entries"]
    assert data["fallbacks"]


def test_catalog_states_exist_in_manifest() -> None:
    states = _manifest_states()
    for event_type, entry in catalog_entries().items():
        state = entry["state"]
        assert state in states, event_type
        assert entry.get("family") == states[state]["family"], event_type


def test_catalog_fallbacks_exist_in_manifest() -> None:
    states = _manifest_states()
    for event_type, state in catalog_fallbacks().items():
        assert state in states, event_type


def test_debug_keys_map_to_catalog_entries() -> None:
    for debug_key in DEBUG_EVENT_NAMES:
        event_type = event_type_for_debug_key(debug_key)
        assert event_type is not None, debug_key
        assert debug_key_for_event_type(event_type) == debug_key


def test_adapter_event_types_have_catalog_states() -> None:
    """Every eventType produced by shipped adapters resolves to a manifest state."""
    now = 1000.0
    samples = [
        RaceEvent(
            name="lap_complete",
            channel="lap",
            priority=40,
            phase="trigger",
            timestamp=now,
            data={"lap": 1, "lapTime": 90.0, "bestLap": 91.0, "deltaToBest": -1.0},
        ),
        RaceEvent(
            name="personal_best",
            channel="lap",
            priority=60,
            phase="trigger",
            timestamp=now,
            data={"lap": 1, "lapTime": 90.0, "bestLap": 90.0, "deltaToBest": 0.0},
        ),
        RaceEvent(
            name="battle",
            channel="battle",
            priority=20,
            phase="enter",
            timestamp=now,
            data={"state": "hunting", "targetPosition": 5, "gap": 1.2},
        ),
        RaceEvent(
            name="battle",
            channel="battle",
            priority=20,
            phase="enter",
            timestamp=now,
            data={"state": "hunted", "targetPosition": 6, "gap": 0.8},
        ),
    ]
    for race_event in samples:
        envelope = None
        for adapter in _ADAPTERS:
            envelope = adapter(
                race_event,
                session_id="session:test",
                mode="RACE",
                now=now,
            )
            if envelope is not None:
                break
        assert envelope is not None, race_event.name
        state = state_for_event_type(envelope.event_type)
        assert state is not None
        assert state in _manifest_states()


def test_state_for_event_type_unknown_returns_none() -> None:
    assert state_for_event_type("NOT_A_REAL_EVENT") is None


@pytest.mark.parametrize(
    ("event_type", "state"),
    [
        ("LAP_COMPLETE", "lap_complete"),
        ("PERSONAL_BEST", "personal_best"),
        ("HUNTING", "hunting"),
        ("TIME_LOST", "gain_found"),
        ("SECTOR_SPLIT", "gain_found"),
    ],
)
def test_state_resolution(event_type: str, state: str) -> None:
    assert state_for_event_type(event_type) == state


def test_battle_catalog_states_are_battle_family() -> None:
    states = _manifest_states()
    for event_type in ("HUNTING", "HUNTED", "APPROACH", "ATTACK_RANGE"):
        state = state_for_event_type(event_type)
        assert state is not None
        assert states[state]["family"] == "battle"


def test_catalog_manifest_sample_slots() -> None:
    states = _manifest_states()
    for entry in catalog_entries().values():
        sample = states[entry["state"]].get("sample") or {}
        for slot in ("title", "subtitle", "value", "meta"):
            assert slot in sample, entry["state"]


def test_catalog_json_shipped_under_web_root() -> None:
    path = web_root() / "themes-v4" / "event_catalog.json"
    assert path.is_file()
