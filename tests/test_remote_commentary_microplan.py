"""Regression gates for current facts, independent validation and remote IO."""

import asyncio
import json
from dataclasses import replace

import pytest
from test_n12_consumers import _batch

from irswitch.events.commentary_microplan import Microplan, plan_from_accepted
from irswitch.events.commentary_model import ModelClient, ModelSettings
from irswitch.events.stream import freeze_accepted_event, thaw_envelope


def plan(event_type="PERSONAL_BEST", metrics=None):
    batch = _batch()
    envelope = thaw_envelope(batch.events[0].envelope)
    envelope.event_type = event_type
    envelope.metrics = metrics or {"lapTime": 102.315}
    envelope.subject = replace(envelope.subject, display_name="Buchtanen")
    accepted = freeze_accepted_event(
        envelope, audiences=("commentary",), source="test", source_ordinal=0
    )
    return plan_from_accepted(accepted, replace(batch, events=(accepted,)))


def test_current_plan_is_independent_and_roundtrips():
    first = plan()
    second = plan(metrics={"lapTime": 101.123})
    assert first is not None and second is not None
    assert first.digest != second.digest
    assert "1:42.315" in first.facts[0][1]
    assert "Alex" not in first.prompt_json()
    assert Microplan.from_dict(first.to_dict()) == first
    assert first.accepts("Buchtanen sets a personal best of 1:42.315.")
    for hallucination in (
        "Buchtanen sets a track record of 1:42.315.",
        "Buchtanen sets a personal best of 1:41.123.",
        "Buchtanen overtakes Rossi.",
        "Buchtanen sets a personal best of 1:42.315 because Rossi pitted.",
    ):
        assert not first.accepts(hallucination)


def test_no_unknown_or_invalid_fact_becomes_speech():
    assert plan("STREAM_STARTED") is None
    with pytest.raises(ValueError):
        plan(metrics={"lapTime": float("nan")})
    assert plan(metrics={"lapTime": -1}) is None


def test_completed_lap_accepts_spoken_time_but_rejects_changed_facts():
    current = plan("LAP_COMPLETE")
    assert current is not None
    text = "Buchtanen completes the lap in one minute, forty-two point three one five."
    assert current.accepts(text)
    assert not current.accepts(text.replace("forty-two", "forty-one"))
    assert not current.accepts(text.replace("Buchtanen", "Rossi"))
    assert not current.accepts(text[:-1] + " for a personal best.")


@pytest.mark.asyncio
async def test_one_attempt_async_cancel_and_shadow_is_owned(monkeypatch):
    current = plan()
    assert current is not None
    settings = ModelSettings(
        provider="remote",
        mode="live",
        enabled=True,
        base_url="https://llm.buchtovo.cz/v1",
        model="openai/gpt-oss-120b",
    )
    monkeypatch.setenv("IRSWITCH_LLM_API_KEY", "test-secret")
    client = ModelClient(lambda: settings)
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def slow(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(client, "_post", slow)
    task = asyncio.create_task(client.realize(current))
    await asyncio.wait_for(entered.wait(), 0.5)
    assert await client.realize(current) is None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
    assert await client.realize(current) is None
    await client.close()


def test_numeric_hero_identity_is_bound_to_current_context():
    import time

    from irswitch.events.adapters.battle import battle_race_event_to_envelope
    from irswitch.events.stream import freeze_context, thaw_context
    from irswitch.overlay.protocol import RaceEvent

    batch = _batch()
    context = thaw_context(batch.context_payload)
    context["story"]["hero"].update(car_idx=7, speakable_names=["Buchtanen"])
    batch = replace(batch, context_payload=freeze_context(context))
    event = RaceEvent(
        name="battle",
        channel="battle",
        timestamp=time.time(),
        phase="enter",
        priority=50,
        data={
            "state": "hunting",
            "heroCarIdx": 7,
            "targetCarIdx": 9,
            "targetName": "Rossi",
            "direction": "front",
            "gap": 0.3,
        },
    )
    envelope = battle_race_event_to_envelope(
        event, session_id=batch.session_id, mode="RACE", now=time.monotonic()
    )
    envelope.stamp("event:battle:1", 1)
    accepted = freeze_accepted_event(
        envelope, audiences=("commentary",), source="test", source_ordinal=0
    )
    current = plan_from_accepted(accepted, batch)
    assert current is not None
    assert current.subject == "Buchtanen"
    assert len(current.facts) == 2
    assert current.accepts("Buchtanen is just 0.3 seconds behind Rossi and closing.")
    assert not current.accepts("Buchtanen is just 0.3 seconds ahead of Rossi and closing.")
    assert not current.accepts("Buchtanen overtakes Rossi.")
    context["story"]["hero"]["car_idx"] = 8
    assert (
        plan_from_accepted(accepted, replace(batch, context_payload=freeze_context(context)))
        is None
    )


@pytest.mark.asyncio
async def test_response_facts_not_model_fact_ids_are_authority(monkeypatch):
    current = plan()
    assert current is not None
    monkeypatch.setenv("IRSWITCH_LLM_API_KEY", "test-secret")
    settings = ModelSettings(
        provider="remote",
        mode="live",
        enabled=True,
        base_url="https://llm.buchtovo.cz/v1",
        model="openai/gpt-oss-120b",
    )
    client = ModelClient(lambda: settings)

    async def reply(body, headers, timeout_s):
        assert headers["Authorization"] == "Bearer test-secret"
        assert body["temperature"] == 0.3 and body["top_p"] == 1
        assert body["max_tokens"] == 192
        assert "options" not in body and "think" not in body
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "action": "speak",
                                "used_fact_ids": [f[0] for f in current.facts],
                                "candidates": [
                                    {"style_id": "natural", "text": "Buchtanen wins the race."}
                                ],
                            }
                        )
                    },
                }
            ]
        }

    monkeypatch.setattr(client, "_post", reply)
    assert await client.realize(current) is None
    assert client.status()["lastReason"] == "semantic_rejected"
    assert "test-secret" not in json.dumps(client.status())
    await client.close()
