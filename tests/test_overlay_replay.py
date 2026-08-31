"""Mock generator and JSONL replay roundtrip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irswitch.overlay.bus import OverlayRecorder, load_jsonl, strip_secrets
from irswitch.overlay.mock import mock_race_state
from irswitch.overlay.protocol import snapshot_envelope
from irswitch.overlay.replay import OverlayReplayer


def test_mock_hunting_sequence_gaps_decrease() -> None:
    early = mock_race_state(0.0)
    late = mock_race_state(6.0)
    assert early.gap_ahead is not None and late.gap_ahead is not None
    assert late.gap_ahead < early.gap_ahead
    assert late.closing_rate_ahead and late.closing_rate_ahead > 0


def test_jsonl_roundtrip_strips_secrets(tmp_path: Path) -> None:
    path = tmp_path / "battle.jsonl"
    rec = OverlayRecorder(str(path))
    rec.write(
        1.0, {"type": "state", "domain": "race", "password": "nope", "data": {"gap_ahead": 2.0}}
    )
    rec.write(1.5, snapshot_envelope(mock_race_state(1.0), None, None, []))
    rows = load_jsonl(str(path))
    assert rows[0]["t"] == 0.0
    assert "password" not in rows[0]
    assert rows[1]["type"] == "snapshot"
    assert strip_secrets({"token": "x", "a": 1}) == {"a": 1}
    assert strip_secrets(
        {
            "copy": {"headlineToken": "position.rival_threat", "statusToken": ""},
            "password": "nope",
            "access_token": "nope",
        }
    ) == {"copy": {"headlineToken": "position.rival_threat", "statusToken": ""}}


@pytest.mark.asyncio
async def test_replayer_applies_state(tmp_path: Path) -> None:
    from irswitch.overlay.bus import OverlayBus

    path = tmp_path / "replay.jsonl"
    path.write_text(
        json.dumps(
            {
                "t": 0.0,
                "type": "state",
                "domain": "race",
                "data": {"connected": True, "position": 3},
            }
        )
        + "\n"
    )
    bus = OverlayBus()
    await OverlayReplayer(str(path), bus).run()
    assert bus.race.position == 3
