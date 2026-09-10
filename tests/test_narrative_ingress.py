"""#284 NarrativeIngress — shadow fanout→mailbox adapter (not live-wired)."""

from __future__ import annotations

from pathlib import Path

from test_narrative_context_batch import _event, _fact_view, _timeline

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.events import __all__ as events_exports
from irswitch.events.narrative_ingress import NarrativeIngress, project_runtime_status
from irswitch.events.narrative_runtime import NarrativeRuntime, RuntimeStatus

SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "narrative_ingress.py"
)


def test_ingress_source_documents_shadow_boundary() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "Not exported from ``events/__init__.py``" in text
    assert "race.runtime" in text
    assert "commentary.consumer" in text
    assert "NarrativeIngress" not in events_exports
    assert "project_runtime_status" not in events_exports


def test_admit_context_publication_preserves_order_and_sequences() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    events = tuple(_event(index) for index in range(3))
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(3),
        events=events,
        fanout_stream_sequence=11,
        command_id_prefix="pub:1",
        enqueued_mono_ms=2_000,
    )
    assert result.accepted
    assert result.reason == "accepted"
    assert result.command_ids == ("pub:1:0",)
    assert result.mailbox_sequences == (1,)
    assert "ingress_publication_complete" in result.effects
    assert len(mailbox) == 1
    command = mailbox.dequeue()
    assert command is not None
    assert command.kind == "APPLY_CONTEXT_BATCH"
    assert command.external_order is not None
    assert command.external_order.fanout_stream_sequence == 11
    assert command.external_order.first_source_ordinal == 0
    assert command.external_order.last_source_ordinal == 2


def test_admit_splits_at_64_events_preserving_total_order() -> None:
    ingress = NarrativeIngress()
    events = tuple(_event(index) for index in range(65))
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(65),
        events=events,
        fanout_stream_sequence=11,
        command_id_prefix="pub:split",
        enqueued_mono_ms=2_100,
    )
    assert result.accepted
    assert result.command_ids == ("pub:split:0", "pub:split:1")
    assert result.mailbox_sequences == (1, 2)
    first = ingress.mailbox.dequeue()
    second = ingress.mailbox.dequeue()
    assert first is not None and second is not None
    assert first.mailbox_sequence < second.mailbox_sequence
    assert first.external_order is not None and second.external_order is not None
    assert first.external_order.first_source_ordinal == 0
    assert first.external_order.last_source_ordinal == 63
    assert second.external_order.first_source_ordinal == 64
    assert second.external_order.last_source_ordinal == 64


def test_ingress_mailbox_can_feed_narrative_runtime_without_live_wiring() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(1),
        events=(_event(0),),
        fanout_stream_sequence=11,
        command_id_prefix="pub:rt",
        enqueued_mono_ms=2_200,
    )
    assert result.accepted
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    reduced = runtime.reduce_next()
    assert reduced is not None
    assert reduced.kind == "APPLY_CONTEXT_BATCH"
    assert reduced.disposition == "handled"
    assert "plan_dispatched" in reduced.effects


def test_project_runtime_status_emits_commentary_runtime_subset() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    status = runtime.status()
    assert isinstance(status, RuntimeStatus)
    projection = project_runtime_status(status)
    assert projection["schemaVersion"] == "commentary-runtime/2"
    assert projection["status"] == "ready"
    assert projection["language"] == "en"
    assert projection["speech"] == {
        "state": "idle",
        "sourceKind": None,
        "utteranceId": None,
        "beatId": None,
        "opportunityId": None,
        "backend": None,
        "backendGeneration": None,
        "dispatchedAtMonoMs": None,
        "acceptedAtMonoMs": None,
        "lastTerminal": None,
    }
    assert projection["queues"]["mailbox"]["capacity"] == 64
    assert projection["queues"]["mailbox"]["depth"] == 0
    assert projection["timeline"] == {
        "broadcastEpoch": 0,
        "streamEpoch": 0,
        "narrativeRunActive": False,
        "streamActive": None,
        "streamState": "unknown",
        "historyComplete": True,
    }
    assert projection["components"]["llm"]["status"] == "ready"
    assert projection["components"]["tts"]["status"] == "ready"
    assert projection["components"]["tape"]["status"] == "disabled"
    assert projection["recovery"]["count"] == 0
    assert "admissionDiagnostics" in projection["diagnostics"]


def test_project_runtime_status_speech_retains_last_terminal_after_completion() -> None:
    """#273 speech projection keeps lastTerminal after the lane returns to idle."""
    from irswitch.contracts.command import NarrativeCommand

    runtime = NarrativeRuntime()
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "speech:proj:manual", 12_000, text="Gap is closing.", admission_ordinal=1
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.disposition == "handled"
    projection = project_runtime_status(runtime.status())
    assert projection["speech"]["state"] == "committed"
    assert projection["speech"]["sourceKind"] == "manual"
    assert projection["speech"]["utteranceId"] is not None
    assert projection["speech"]["beatId"] is None
    utterance = runtime.current_utterance_token()
    assert utterance is not None

    def _tts(kind: str, command_id: str, *, at_mono_ms: int) -> NarrativeCommand:
        return NarrativeCommand.tts_callback(
            command_id,
            kind,  # type: ignore[arg-type]
            at_mono_ms,
            utterance_id=str(utterance["utteranceId"]),
            utterance_ordinal=int(utterance["utteranceOrdinal"]),
            backend_generation=int(utterance["backendGeneration"]),
            dispatch_generation=int(utterance["dispatchGeneration"]),
            callback={
                "schemaVersion": "tts-callback/2",
                "callbackId": f"cb:{command_id}",
                "kind": {
                    "PLAYBACK_ACCEPTED": "playback_accepted",
                    "SPEECH_COMPLETED": "completed",
                }[kind],
                "utteranceId": utterance["utteranceId"],
                "utteranceOrdinal": utterance["utteranceOrdinal"],
                "backend": "sapi",
                "backendGeneration": utterance["backendGeneration"],
                "dispatchGeneration": utterance["dispatchGeneration"],
                "workerSequence": 1,
                "observedMonoMs": at_mono_ms,
                "detailCode": None,
            },
        )

    runtime.admit(_tts("PLAYBACK_ACCEPTED", "speech:proj:pb", at_mono_ms=12_200))
    accepted = runtime.reduce_next()
    assert accepted is not None
    assert accepted.lane_after == "speaking"
    speaking = project_runtime_status(runtime.status())
    assert speaking["speech"]["state"] == "speaking"
    assert speaking["speech"]["acceptedAtMonoMs"] == 12_200

    runtime.admit(_tts("SPEECH_COMPLETED", "speech:proj:done", at_mono_ms=12_500))
    done = runtime.reduce_next()
    assert done is not None
    projection = project_runtime_status(runtime.status())
    assert projection["speech"]["state"] == "idle"
    assert projection["speech"]["utteranceId"] is None
    assert projection["speech"]["lastTerminal"] == {
        "utteranceId": utterance["utteranceId"],
        "sourceKind": "manual",
        "reason": "completed",
        "atMonoMs": 12_500,
    }


def test_project_runtime_status_speech_idle_golden() -> None:
    import json
    from pathlib import Path

    golden_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "commentary_runtime"
        / "status_speech_idle.json"
    )
    projection = project_runtime_status(NarrativeRuntime().status())
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert projection["language"] == expected["language"]
    assert projection["speech"] == expected["speech"]
    assert projection["components"]["llm"]["status"] == expected["components"]["llm"]["status"]
    assert projection["components"]["tts"]["status"] == expected["components"]["tts"]["status"]
    assert projection["components"]["tape"]["status"] == expected["components"]["tape"]["status"]


def test_project_runtime_status_identity_follows_context_timeline() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(1),
        events=(_event(0),),
        fanout_stream_sequence=11,
        command_id_prefix="pub:identity",
        enqueued_mono_ms=3_000,
    )
    assert result.accepted
    reduced = runtime.reduce_next()
    assert reduced is not None
    projection = project_runtime_status(runtime.status())
    timeline = projection["timeline"]
    assert timeline["broadcastEpoch"] == 4
    assert timeline["streamEpoch"] == 1
    assert timeline["narrativeRunActive"] is True
    assert timeline["streamActive"] is True
    assert timeline["streamState"] == "active"
    assert timeline["historyComplete"] is True


def test_project_commentary_health_component_disabled_default() -> None:
    from irswitch.events.narrative_ingress import project_commentary_health_component

    assert project_commentary_health_component() == {"status": "disabled", "reason": None}
    runtime = NarrativeRuntime()
    runtime.enable()
    assert project_commentary_health_component(runtime.status()) == {
        "status": "ready",
        "reason": None,
    }


def test_project_runtime_status_identity_golden_disabled() -> None:
    import json
    from pathlib import Path

    golden_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "commentary_runtime"
        / "status_identity_disabled.json"
    )
    projection = project_runtime_status(NarrativeRuntime().status())
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert projection["timeline"] == expected["timeline"]
    assert projection["schemaVersion"] == expected["schemaVersion"]
    assert projection["status"] == expected["status"]


def test_project_runtime_decisions_selected_golden() -> None:
    import json
    from pathlib import Path

    from irswitch.events.narrative_decision_projection import project_runtime_decisions

    golden_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "commentary_runtime"
        / "decisions_selected.json"
    )
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    projection = project_runtime_decisions(expected["decisions"], runtime=True)
    assert projection == expected


def test_project_runtime_decisions_clamps_limit_newest_first() -> None:
    from irswitch.events.narrative_decision_projection import project_runtime_decisions

    entries = [
        {
            "reducerSequence": seq,
            "atMonoMs": seq,
            "decision": "silence",
            "reason": "no_candidate",
            "beatId": None,
            "episodeId": None,
            "opportunityId": None,
            "tapeChannel": None,
            "candidateSource": None,
            "candidateOrder": None,
            "relation": None,
            "urgency": None,
            "score": None,
            "threshold": 35.0,
            "runnerUp": None,
            "terminalReason": None,
        }
        for seq in (3, 2, 1)
    ]
    projection = project_runtime_decisions(entries, runtime=True, limit=2)
    assert [item["reducerSequence"] for item in projection["decisions"]] == [3, 2]
    assert (
        project_runtime_decisions(entries, runtime=True, limit=0)["decisions"][0]["reducerSequence"]
        == 3
    )
    assert len(project_runtime_decisions(entries, runtime=True, limit=999)["decisions"]) == 3
    assert project_runtime_decisions([], runtime=False) == {
        "schemaVersion": "commentary-runtime/2",
        "runtime": False,
        "decisions": [],
    }


def test_build_runtime_decision_entry_selected_and_silence() -> None:
    from test_story_director import _cand as _director_cand
    from test_story_director import _world as _director_world

    from irswitch.events.beat_plan import CandidateOrder
    from irswitch.events.narrative_decision_projection import build_runtime_decision_entry
    from irswitch.events.story_director import StoryDirector

    director = StoryDirector()
    primary = _director_cand(
        source="event_opportunity",
        opportunity_id="opp:401",
        from_accepted_event=True,
        relation="updates_active_episode",
        tape_channel="race.battle.closing",
        candidate_order=CandidateOrder(417, 0),
    )
    runner = _director_cand(
        beat_id="battle.pursuit",
        source="event_opportunity",
        opportunity_id="opp:402",
        from_accepted_event=True,
        base_priority=50.0,
        candidate_order=CandidateOrder(417, 1),
    )
    selected = director.evaluate(_director_world(now_ms=15_000), (primary, runner))
    entry = build_runtime_decision_entry(
        selected,
        (primary, runner),
        reducer_sequence=418,
        at_mono_ms=90_231,
    )
    assert entry["decision"] == "selected"
    assert entry["beatId"] == "battle.approach"
    assert entry["opportunityId"] == "opp:401"
    assert entry["candidateOrder"] == {"reducerSequence": 417, "sourceOrdinal": 0}
    assert entry["runnerUp"] is not None
    assert entry["runnerUp"]["beatId"] == "battle.pursuit"
    assert entry["threshold"] == 35.0
    assert entry["terminalReason"] is None
    assert entry["atMonoMs"] == 90_231

    silenced = director.evaluate(
        _director_world(lane="building", impulse="timer", now_ms=15_000),
        (primary,),
    )
    quiet = build_runtime_decision_entry(
        silenced,
        (primary,),
        reducer_sequence=419,
        at_mono_ms=90_231,
    )
    assert quiet["decision"] == "silence"
    assert quiet["beatId"] is None
    assert quiet["episodeId"] is None
    assert quiet["opportunityId"] is None
    assert quiet["tapeChannel"] is None
    assert quiet["candidateSource"] is None
    assert quiet["candidateOrder"] is None
    assert quiet["relation"] is None
    assert quiet["urgency"] is None
    assert quiet["score"] is None
    assert quiet["runnerUp"] is None


def test_build_runtime_decision_entry_replaced_precommit() -> None:
    from test_story_director import _cand as _director_cand

    from irswitch.events.beat_plan import CandidateOrder
    from irswitch.events.narrative_decision_projection import build_runtime_decision_entry
    from irswitch.events.story_director import CandidateRecord, DirectorDecision

    primary = _director_cand(
        source="event_opportunity",
        opportunity_id="opp:401",
        from_accepted_event=True,
        candidate_order=CandidateOrder(417, 0),
    )
    selected = CandidateRecord(
        beat_id=primary.beat_id,
        episode_id=primary.episode_id,
        episode_revision=primary.episode_revision,
        source=primary.source,
        eligible=True,
        reject_reason=None,
        score=70.0,
        candidate_order=primary.candidate_order,
    )
    decision = DirectorDecision(
        reason="replaced_precommit",
        selected=selected,
        records=(selected,),
        speech="speak",
        schema_version="director-decision/2",
        planning_cycle_id=1,
        cycle_attempt_ordinal=1,
    )
    entry = build_runtime_decision_entry(
        decision,
        (primary,),
        reducer_sequence=420,
        at_mono_ms=90_231,
    )
    assert entry["decision"] == "replaced"
    assert entry["reason"] == "replaced_precommit"
    assert entry["beatId"] == primary.beat_id
    assert entry["opportunityId"] == "opp:401"


def test_project_validate_response_supported_golden() -> None:
    import json
    from pathlib import Path

    from irswitch.events.narrative_validate_projection import project_validate_response

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "validate_request.json").read_text(encoding="utf-8"))
    expected = json.loads((fixtures / "validate_supported.json").read_text(encoding="utf-8"))
    assert project_validate_response(request) == expected


def test_project_validate_response_actor_reversed_golden() -> None:
    import json
    from pathlib import Path

    from irswitch.events.narrative_validate_projection import project_validate_response

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "validate_request.json").read_text(encoding="utf-8"))
    request = {
        **request,
        "text": "Morgan is closing on the driver, the gap at one point four seconds.",
    }
    expected = json.loads((fixtures / "validate_rejected.json").read_text(encoding="utf-8"))
    assert project_validate_response(request) == expected


def test_project_validate_response_rejects_malformed_request() -> None:
    from irswitch.contracts.primitives import ContractViolation
    from irswitch.events.narrative_validate_projection import project_validate_response

    try:
        project_validate_response({"schemaVersion": "commentary-runtime/2"})
    except ContractViolation:
        return
    raise AssertionError("expected ContractViolation")
