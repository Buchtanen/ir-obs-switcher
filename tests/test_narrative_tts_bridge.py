"""#284 NarrativeRuntime-owned tts_effect bridge."""

from __future__ import annotations

from pathlib import Path

import pytest

from irswitch.commentary.tts import NullTtsSink
from irswitch.contracts.command import NarrativeCommand
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_tts_bridge import build_tts_effect

RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"
BRIDGE_SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "narrative_tts_bridge.py"
)


@pytest.mark.asyncio
async def test_tts_effect_enqueues_text_and_returns_terminal_callbacks() -> None:
    sink = NullTtsSink()
    effect = build_tts_effect(sink, locale="en")
    token = {
        "utteranceId": "utterance:bridge:1",
        "utteranceOrdinal": 1,
        "backendGeneration": 1,
        "dispatchGeneration": 1,
        "text": "Clear gap ahead.",
    }
    produced = await effect(token)
    assert len(sink.spoken) == 1
    assert sink.spoken[0].text == "Clear gap ahead."
    assert [command.kind for command in produced] == [
        "PLAYBACK_ACCEPTED",
        "SPEECH_COMPLETED",
    ]


@pytest.mark.asyncio
async def test_manual_speak_token_carries_text_for_tts_effect() -> None:
    sink = NullTtsSink()
    runtime = NarrativeRuntime(tts_effect=build_tts_effect(sink, locale="en"))
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "manual:bridge",
            8_000,
            text="Box this lap.",
            admission_ordinal=1,
        )
    )
    reduced = runtime.reduce_next()
    assert reduced is not None
    token = runtime.current_utterance_token()
    assert token is not None
    assert token.get("text") == "Box this lap."
    await runtime.apply_effects(reduced.effects)
    assert any(item.text == "Box this lap." for item in sink.spoken)


def test_race_wires_tts_effect_and_drops_speech_mirror() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    bridge = BRIDGE_SOURCE.read_text(encoding="utf-8")
    assert "build_tts_effect" in bridge
    assert "tts_effect=tts_effect" in race or "tts_effect=build_tts_effect" in race
    assert "build_tts_effect(" in race
    assert "legacy_stream_handler=self._mirror_lifecycle_without_speech" in race
    assert "legacy_stream_handler=self.commentary_consumer.handle" not in race
    assert "cache_mirrored_context" in race
    assert "_narrative_subscription_cutover = True" in race
