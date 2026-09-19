"""Editorial story lifecycle remains live while Qwen works."""

import threading
import time
from typing import Any

from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.polish import PolishOutcome
from irswitch.commentary.tts import CommentaryUtterance, ProcessTtsSink, TtsResult
from irswitch.events.envelope import EventSubject, make_envelope
from irswitch.overlay.settings import CommentarySettings
from irswitch.race.ministory import CommitStatus, MiniStoryRegistry, MiniStoryState


def _context(position: int = 5, *, epoch: int = 0) -> dict:
    return {
        "session_id": "s",
        "identity": {"run_epoch": epoch},
        "race": {"run_epoch": epoch, "class_position": position},
    }


def _relation(phase: str = "ENTER", *, epoch: int = 0):
    return make_envelope(
        event_type="HUNTING",
        phase=phase,
        mode="RACE",
        correlation_id=f"run:{epoch}:front:7:8:1",
        subject=EventSubject(car_id="7"),
        target=EventSubject(car_id="8", display_name="Gjoel"),
        metrics={"runEpoch": epoch, "targetCarIdx": 8, "direction": "ahead", "gap": 0.6},
    )


def test_exit_during_building_becomes_resolved_commit() -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context())
    token = registry.observe(_relation()).token
    assert token is not None
    exit_observation = registry.observe(_relation("EXIT"))
    assert exit_observation.narrate is False
    decision = registry.commit(
        token,
        {
            "version": "commentary-facts/3",
            "microplan": {
                "relation": "hero_attacks_target",
                "actor_roles": (("target", "Gjoel"),),
            },
        },
        locale="en",
    )
    assert decision.status == CommitStatus.RESOLVED
    assert decision.canonical == "The attacking window on Gjoel has closed for now."
    assert decision.fact_pack["microplan"]["story_state"] == "resolved"


def test_exit_after_speech_commit_does_not_cancel_lease() -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context())
    token = registry.observe(_relation()).token
    assert token is not None
    assert registry.commit(token, None, locale="en").status == CommitStatus.UNCHANGED
    assert registry.mark_speaking(token)
    exit_observation = registry.observe(_relation("EXIT"))
    assert exit_observation.state == MiniStoryState.RESOLVED
    assert registry.state_of(token) == MiniStoryState.SPEAKING
    registry.complete(token)
    assert registry.state_of(token) == MiniStoryState.COMPLETED


def test_order_change_interrupts_active_and_invalidates_waiting_story() -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context(5))
    active = registry.observe(_relation()).token
    waiting = registry.observe(
        make_envelope(
            event_type="HUNTED",
            phase="ENTER",
            correlation_id="rear:7:9:1",
            metrics={"targetCarIdx": 9, "direction": "behind"},
        )
    ).token
    assert active is not None and waiting is not None
    registry.commit(active, None, locale="en")
    registry.mark_speaking(active)
    assert registry.observe_context(_context(4)) is True
    assert registry.state_of(active) == MiniStoryState.INTERRUPTED
    assert registry.state_of(waiting) == MiniStoryState.INVALIDATED
    assert registry.commit(waiting, None, locale="en").status == CommitStatus.INVALIDATED


def test_epoch_change_invalidates_uncommitted_token() -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context(epoch=0))
    token = registry.observe(_relation(epoch=0)).token
    assert token is not None
    registry.observe_context(_context(epoch=1))
    assert registry.commit(token, None, locale="en").status == CommitStatus.INVALIDATED


def test_replay_adopt_applies_later_resolved_revision() -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context())
    envelope = _relation()
    token = registry.adopt(
        envelope,
        {
            "storyId": "story:0:9",
            "storyRevision": 1,
            "runEpoch": 0,
            "heroOrderRevision": 0,
            "correlationId": envelope.correlation_id,
            "eventType": envelope.event_type,
            "state": "ready",
        },
    )
    assert token is not None
    registry.adopt(
        _relation("EXIT"),
        {
            **token.to_dict(state=MiniStoryState.RESOLVED),
            "storyRevision": 2,
            "state": "resolved",
        },
    )

    assert registry.commit(token, None, locale="en").status == CommitStatus.RESOLVED
    assert registry.current_token(token).revision == 2


def test_position_event_advances_order_without_waiting_for_context() -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context(5))
    old = registry.observe(_relation()).token
    assert old is not None
    registry.commit(old, None, locale="en")
    registry.mark_speaking(old)
    position = registry.observe(
        make_envelope(
            event_type="POSITION_GAINED",
            phase="RESULT",
            correlation_id="position:5:4",
            metrics={"position": 4},
        )
    ).token
    assert position is not None
    assert position.hero_order_revision == 1
    assert registry.state_of(old) == MiniStoryState.INTERRUPTED


def test_partial_exit_matches_but_conflicting_exit_is_ignored() -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context())
    token = registry.observe(_relation()).token
    assert token is not None
    registry.observe(
        make_envelope(
            event_type="HUNTING",
            phase="EXIT",
            correlation_id=token.correlation_id,
            metrics={"targetCarIdx": 99},
        )
    )
    assert registry.commit(token, None, locale="en").status == CommitStatus.UNCHANGED


def _utterance(token, *, event_type: str = "HUNTING", text: str = "He attacks Gjoel."):
    node = next(
        node for node in load_sequence_graph().nodes.values() if event_type in node.event_types
    )
    return CommentaryUtterance(
        node_id=node.id,
        locale="en",
        emotion="unknown",
        text=text,
        event_type=event_type,
        event_id="e1",
        correlation_id=token.correlation_id,
        estimated_seconds=2.0,
        node=node,
        priority=80,
        fact_pack={
            "version": "commentary-facts/3",
            "canonical": text,
            "required_facts": [{"id": "relation", "text": text}],
            "optional_facts": [],
            "forbidden_claims": [],
            "microplan": {
                "relation": "hero_attacks_target",
                "actor_roles": (("target", "Gjoel"),),
                "story_state": "live",
            },
        },
        story_token=token,
    )


def test_resolution_during_qwen_gets_one_result_call_within_two_call_budget(
    monkeypatch: Any,
) -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context())
    token = registry.observe(_relation()).token
    assert token is not None
    polish_started = threading.Event()
    release = threading.Event()
    calls: list[bool] = []
    spoken: list[str] = []
    lifecycle: list[dict] = []

    def fake_polish(text: str, _node, _settings, *, past: bool = False, **kwargs):
        calls.append(past)
        if not past:
            polish_started.set()
            release.wait(timeout=2.0)
        output = "The attacking window on Gjoel has faded." if past else text
        return PolishOutcome(
            text=output,
            outcome="ok",
            latency_ms=1.0,
            skeleton=text,
            request={},
            attempts=1,
            fact_pack=kwargs.get("fact_pack"),
        )

    def fake_speak(text: str, **_kwargs) -> TtsResult:
        spoken.append(text)
        return TtsResult("test", True)

    monkeypatch.setattr("irswitch.commentary.tts.polish_skeleton", fake_polish)
    monkeypatch.setattr("irswitch.commentary.tts.speak_text", fake_speak)
    sink = ProcessTtsSink(
        CommentarySettings(llm_polish=True, tts_backend="null"),
        story_registry=registry,
        on_story_debug=lifecycle.append,
    )
    sink.enqueue(_utterance(token))
    assert polish_started.wait(timeout=1.0)
    registry.observe(_relation("EXIT"))
    release.set()
    assert sink.wait_idle(timeout_s=2.0)
    assert calls == [False, True]
    assert spoken == ["The attacking window on Gjoel has faded."]
    assert registry.state_of(token) == MiniStoryState.COMPLETED
    assert [row["action"] for row in lifecycle] == [
        "building",
        "committed",
        "speaking",
        "completed",
    ]
    assert lifecycle[1]["reason"] == "ministory_resolved"


def test_tts_lifecycle_opens_building_lease_before_worker_starts(monkeypatch: Any) -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context())
    token = registry.observe(_relation()).token
    assert token is not None
    release = threading.Event()
    lifecycle: list[dict] = []

    def fake_speak(text: str, **_kwargs) -> TtsResult:
        release.wait(timeout=2.0)
        return TtsResult("test", True)

    monkeypatch.setattr("irswitch.commentary.tts.speak_text", fake_speak)
    sink = ProcessTtsSink(
        CommentarySettings(tts_backend="null"),
        story_registry=registry,
        on_story_debug=lifecycle.append,
    )
    sink.enqueue(_utterance(token))
    assert lifecycle[0]["action"] == "building"
    release.set()
    assert sink.wait_idle(timeout_s=2.0)
    assert [row["action"] for row in lifecycle] == [
        "building",
        "committed",
        "speaking",
        "completed",
    ]


def test_replaced_tts_waiter_closes_its_presentation_lease(monkeypatch: Any) -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context())

    def token_for(target: int):
        envelope = make_envelope(
            event_type="HUNTING",
            phase="ENTER",
            correlation_id=f"front:7:{target}:1",
            subject=EventSubject(car_id="7"),
            target=EventSubject(car_id=str(target), display_name=f"Driver {target}"),
            metrics={"targetCarIdx": target, "direction": "ahead", "gap": 0.6},
        )
        token = registry.observe(envelope).token
        assert token is not None
        return token

    first, waiting, replacement = token_for(8), token_for(9), token_for(10)
    started = threading.Event()
    release = threading.Event()
    lifecycle: list[dict] = []

    def blocked_speak(_text: str, **_kwargs) -> TtsResult:
        started.set()
        release.wait(timeout=2.0)
        return TtsResult("test", True)

    monkeypatch.setattr("irswitch.commentary.tts.speak_text", blocked_speak)
    sink = ProcessTtsSink(
        CommentarySettings(tts_backend="null"),
        story_registry=registry,
        on_story_debug=lifecycle.append,
    )
    sink.enqueue(_utterance(first))
    assert started.wait(timeout=1.0)
    sink.enqueue(_utterance(waiting))
    sink.enqueue(_utterance(replacement))
    assert registry.state_of(waiting) == MiniStoryState.INVALIDATED
    assert any(
        row["storyId"] == waiting.story_id
        and row["action"] == "invalidated"
        and row["reason"] == "tts_queue_replaced"
        for row in lifecycle
    )
    release.set()
    assert sink.wait_idle(timeout_s=2.0)


def test_epoch_invalidation_during_qwen_blocks_tts(monkeypatch: Any) -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context())
    token = registry.observe(_relation()).token
    assert token is not None
    polish_started = threading.Event()
    release = threading.Event()
    spoken: list[str] = []

    def fake_polish(text: str, _node, _settings, **kwargs):
        polish_started.set()
        release.wait(timeout=2.0)
        return PolishOutcome(text, "ok", 1.0, text, {}, attempts=1)

    monkeypatch.setattr("irswitch.commentary.tts.polish_skeleton", fake_polish)
    monkeypatch.setattr(
        "irswitch.commentary.tts.speak_text",
        lambda text, **_kwargs: spoken.append(text) or TtsResult("test", True),
    )
    sink = ProcessTtsSink(
        CommentarySettings(llm_polish=True, tts_backend="null"), story_registry=registry
    )
    sink.enqueue(_utterance(token))
    assert polish_started.wait(timeout=1.0)
    registry.observe_context(_context(epoch=1))
    release.set()
    assert sink.wait_idle(timeout_s=2.0)
    assert spoken == []


def test_hero_order_interrupt_cancels_active_speech_and_worker_is_reusable(
    monkeypatch: Any,
) -> None:
    registry = MiniStoryRegistry()
    registry.observe_context(_context(5))
    first = registry.observe(_relation()).token
    assert first is not None
    started = threading.Event()
    spoken: list[str] = []

    def cancellable_speak(text: str, *, cancelled=None, **_kwargs) -> TtsResult:
        if text.startswith("He attacks"):
            started.set()
            deadline = time.monotonic() + 2.0
            while not cancelled() and time.monotonic() < deadline:
                time.sleep(0.005)
            return TtsResult("test", False, "interrupted")
        spoken.append(text)
        return TtsResult("test", True)

    monkeypatch.setattr("irswitch.commentary.tts.speak_text", cancellable_speak)
    sink = ProcessTtsSink(CommentarySettings(tts_backend="null"), story_registry=registry)
    sink.enqueue(_utterance(first))
    assert started.wait(timeout=1.0)
    assert registry.observe_context(_context(4)) is True
    sink.interrupt()
    position = make_envelope(
        event_type="POSITION_GAINED",
        phase="RESULT",
        correlation_id="position:5:4",
        metrics={"position": 4},
    )
    second = registry.observe(position).token
    assert second is not None
    sink.enqueue(_utterance(second, event_type="POSITION_GAINED", text="He moves into P4."))
    assert sink.wait_idle(timeout_s=2.0)
    assert registry.state_of(first) == MiniStoryState.INTERRUPTED
    assert spoken == ["He moves into P four."]
    assert registry.state_of(second) == MiniStoryState.COMPLETED
