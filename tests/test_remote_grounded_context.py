"""Regression cases from the blind prompt evaluation (#389)."""

import json
from dataclasses import replace

import pytest
from test_remote_commentary_microplan import plan

from irswitch.events.commentary_grounding import free_grounding_reasons
from irswitch.events.commentary_microplan import Microplan
from irswitch.events.commentary_model import ModelClient, ModelSettings


def test_remote_prompt_names_units_and_only_played_history(monkeypatch):
    first = plan(metrics={"lapTime": 102.315})
    second = plan(metrics={"lapTime": 101.123})
    assert first is not None and second is not None
    cfg = ModelSettings(provider="remote", enabled=True, wording_policy="experimental_free")
    client = ModelClient(lambda: cfg)
    client.note_selection(first, "Buchtanen posts a lap of 1:42.315.", generated=True)
    body = client._body(cfg, second)
    assert body["messages"][1]["content"]
    assert "recent_commentary" in json.loads(body["messages"][1]["content"])
    assert json.loads(body["messages"][1]["content"])["recent_commentary"] == []
    client.note_spoken(first)
    content = json.loads(client._body(cfg, second)["messages"][1]["content"])
    assert content["recent_commentary"][0]["text"] == "Buchtanen posts a lap of 1:42.315."
    assert content["facts"][0]["fields"]["lap_time"] == "1:41.123"
    assert "structured facts" in body["messages"][0]["content"].lower()
    assert Microplan.from_dict(second.to_dict()) == second


@pytest.mark.parametrize(
    "text,fields,kind",
    [
        (
            "Alex is twenty seconds behind Sam, who is nineteenth.",
            (("gap_seconds", 0.8), ("target_position", 19)),
            "HUNTING",
        ),
        (
            "Alex has picked up four separate incidents after contact.",
            (("incident_points_added", 4),),
            "INCIDENT",
        ),
        ("Alex moved up to chase Lee at 0.9 seconds.", (("gap_seconds", 0.9),), "HUNTING"),
        (
            "Alex entered the pit lane, dropping to nineteenth.",
            (("entry_position", 19),),
            "PIT_ENTRY",
        ),
        ("Alex is back on track after running wide.", (), "RECOVERY"),
        ("Alex sets a track record of 1:31.759.", (("lap_time", "1:31.759"),), "PERSONAL_BEST"),
    ],
)
def test_known_unsupported_claims_are_rejected(text, fields, kind):
    current = replace(
        plan(),
        beat_id=kind,
        subject="Alex",
        actors=(("player", "Alex"), ("target", "Sam")),
        input_fields=fields,
    )
    assert free_grounding_reasons(text, current)


def test_supported_paraphrase_and_number_are_accepted():
    current = replace(
        plan(),
        beat_id="HUNTING",
        subject="Alex",
        actors=(("player", "Alex"), ("target", "Sam")),
        input_fields=(("gap_seconds", 0.8),),
    )
    assert (
        free_grounding_reasons("Alex is now just 0.8 seconds behind Sam and closing.", current)
        == []
    )
    assert free_grounding_reasons("Alex is now 0.9 seconds behind Sam and closing.", current)
    assert free_grounding_reasons("Sam is closing on Alex, now 0.8 seconds behind.", current)
    assert free_grounding_reasons("Alex is under pressure from Sam at 0.8 seconds.", current)
    assert free_grounding_reasons("Alex is 0.8 seconds behind Lee and closing.", current)
    derived = replace(
        current,
        input_fields=(("gap_seconds", 0.8), ("gap_reduction_seconds", 1.6)),
    )
    assert free_grounding_reasons("Alex is 1.6 seconds behind Sam and closing.", derived)
    assert (
        free_grounding_reasons(
            "Alex is 0.8 seconds behind Sam, the gap reduced by 1.600 seconds.", derived
        )
        == []
    )


def test_projected_incident_pit_and_lap_facts_have_explicit_units():
    incident = plan("INCIDENT", {"value": 4, "total": 6, "branch": "unknown"})
    pit_entry = plan("PIT_ENTRY", {"entryPosition": 19})
    pit_exit = plan("PIT_EXIT", {"entryPosition": 19, "exitPosition": 22})
    lap = plan("LAP_COMPLETE", {"lapTime": 94.054, "bestLap": 91.766, "deltaToBest": 2.288})
    assert incident and pit_entry and pit_exit and lap
    assert dict(incident.input_fields) == {
        "incident_points_added": 4,
        "incident_points_total": 6,
    }
    assert "incident points" in incident.allowed[0]
    assert dict(pit_entry.input_fields) == {"entry_position": 19}
    assert dict(pit_exit.input_fields) == {"exit_position": 22}
    assert "dropping" not in pit_entry.allowed[0]
    assert dict(lap.input_fields)["delta_to_best_seconds"] == 2.288
    assert "2.288 seconds slower" in lap.facts[1][1]
    assert plan("INCIDENT", {"value": 4, "total": 2}) is None
    assert plan("LAP_COMPLETE", {"lapTime": 94.054, "bestLap": 91.766, "deltaToBest": 8})
    assert "delta_to_best_seconds" not in dict(
        plan("LAP_COMPLETE", {"lapTime": 94.054, "bestLap": 91.766, "deltaToBest": 8}).input_fields
    )
    assert free_grounding_reasons(
        "Buchtanen has collected six more incident points, bringing his total to six.", incident
    )
    assert (
        free_grounding_reasons(
            "Buchtanen has picked up four incident points, bringing his total to six.", incident
        )
        == []
    )
    assert free_grounding_reasons("Buchtanen exits the pit lane in nineteenth place.", pit_exit)
    assert (
        free_grounding_reasons("Buchtanen enters the pit lane from nineteenth place.", pit_entry)
        == []
    )


def test_played_history_is_limited_by_session_and_age():
    now = [1000.0]
    cfg = ModelSettings(provider="remote", enabled=True)
    client = ModelClient(lambda: cfg, clock=lambda: now[0])
    first = plan()
    assert first
    client.note_selection(first, first.allowed[0], generated=False)
    client.note_spoken(first)
    newer = replace(first, event_id="next")
    assert json.loads(client._body(cfg, newer)["messages"][1]["content"])["recent_commentary"]
    assert not json.loads(
        client._body(cfg, replace(newer, session_id="other"))["messages"][1]["content"]
    )["recent_commentary"]
    now[0] += 61
    assert not json.loads(client._body(cfg, newer)["messages"][1]["content"])["recent_commentary"]


def test_gap_reduction_is_computed_only_from_played_same_target():
    now = [1000.0]
    cfg = ModelSettings(provider="remote", enabled=True)
    client = ModelClient(lambda: cfg, clock=lambda: now[0])
    first = plan("HUNTING", {"direction": "front", "targetName": "Rossi", "gap": 2.8})
    second = plan("HUNTING", {"direction": "front", "targetName": "Rossi", "gap": 1.2})
    assert first and second
    now[0] += 15
    assert client._request_plan(second) == second
    now[0] -= 15
    client.note_selection(first, first.allowed[0], generated=False)
    now[0] += 15
    assert client._request_plan(second) == second  # selected is not yet played
    now[0] -= 15
    client.note_spoken(first)
    now[0] += 15
    derived = client._request_plan(second)
    assert dict(derived.input_fields)["gap_reduction_seconds"] == 1.6
    assert "decreased by 1.600 seconds" in derived.facts[-1][1]
    assert "15 seconds" not in derived.facts[-1][1]
    other = replace(second, actors=(("player", "Buchtanen"), ("target", "Lee")))
    assert client._request_plan(other) == other
    same_name_new_car = replace(second, actors=(("player", "Buchtanen"), ("other-car", "Rossi")))
    assert client._request_plan(same_name_new_car) == same_name_new_car
    new_relation = replace(second, correlation_id="new-relation")
    assert client._request_plan(new_relation) == new_relation
    assert client._request_plan(replace(second, session_id="another")) == replace(
        second, session_id="another"
    )


@pytest.mark.asyncio
async def test_free_wording_rejects_wrong_units_before_speech(monkeypatch):
    current = replace(
        plan(),
        beat_id="HUNTING",
        subject="Alex",
        actors=(("player", "Alex"), ("target", "Sam")),
        input_fields=(("gap_seconds", 0.8),),
    )
    cfg = ModelSettings(provider="remote", enabled=True, wording_policy="experimental_free")
    client = ModelClient(lambda: cfg)
    monkeypatch.setenv("IRSWITCH_LLM_API_KEY", "test-secret")

    async def reply(*args):
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "action": "speak",
                                "used_fact_ids": [current.facts[0][0]],
                                "candidates": [
                                    {
                                        "style_id": "natural",
                                        "text": "Alex is twenty seconds behind Sam and closing.",
                                    }
                                ],
                            }
                        )
                    },
                }
            ]
        }

    monkeypatch.setattr(client, "_post", reply)
    assert await client.realize(current) is None
    assert client.status()["lastReason"] == "grounding_rejected"
    assert "test-secret" not in json.dumps(client.status())
    await client.close()
