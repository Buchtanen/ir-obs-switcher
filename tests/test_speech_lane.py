"""#264 single in-flight speech lane with no prepared waiter."""

from __future__ import annotations

import json
from pathlib import Path

from irswitch.events import __all__ as events_exports
from irswitch.events.beat_plan import CandidateOrder
from irswitch.events.opportunity_queue import OpportunityIntent, OpportunityQueue
from irswitch.events.speech_lane import (
    ACCEPTANCE_BOUNDARIES,
    AUTO_BACKEND_ORDER,
    MANUAL_LATCH_TIMEOUT_MS,
    SCHEMA_VERSION,
    START_TIMEOUT_MS,
    STOP_TIMEOUT_MS,
    SpeechIntent,
    SpeechLane,
    TtsCallback,
    resolve_backend,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "speech_lane.py"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "speech_lane"
HASH = "sha256:" + ("ab" * 32)
OCCURRENCE = "3:race:0"
LINEAGE = "3:practice:0>3:race:0"


def _opp(**overrides: object) -> OpportunityIntent:
    values: dict[str, object] = {
        "opportunity_id": "opp:1",
        "event_id": "event:1",
        "event_kind": "battle.pursuit",
        "current_identifier": "HUNTING",
        "source_class": "detector",
        "candidate_id": "cand:1",
        "detector_observation_id": "obs:1",
        "stream_epoch": 3,
        "occurrence_id": OCCURRENCE,
        "lineage_id": LINEAGE,
        "episode_id": "episode:battle-1",
        "correlation_key": ("hero", "car.22"),
        "tape_channel": None,
        "policy_id": "live_story",
        "created_mono_ms": 10_000,
        "material_revision": 1,
        "source_fact_ids": ("fact:closing-1",),
        "candidate_order": CandidateOrder(reducer_sequence=4, source_ordinal=1),
        "source_order": None,
        "relation": "opens",
        "beat_id": "battle.pursuit",
        "beat_ids": ("battle.pursuit", "battle.approach"),
        "story_id": "battle_ahead",
        "semantic_identity": ("hero", "car.22", "battle"),
    }
    values.update(overrides)
    return OpportunityIntent(**values)  # type: ignore[arg-type]


def _intent(**overrides: object) -> SpeechIntent:
    values: dict[str, object] = {
        "utterance_id": "utt:1",
        "source_kind": "narrative",
        "opportunity_id": "opp:1",
        "reservation_token": None,
        "plan_id": "plan:1",
        "beat_id": "battle.pursuit",
        "episode_id": "episode:battle-1",
        "episode_revision": 1,
        "backend": "auto",
        "adapter": "sapi",
        "backend_generation": 4,
        "config_generation": 4,
        "config_hash": HASH,
        "config_apply_sequence": 1,
        "tts_ready": True,
        "available_backends": ("sapi", "espeak"),
        "now_ms": 10_000,
        "dispatch_generation": 1,
        "max_seconds": 14.0,
        "manual_request_id": None,
        "text": None,
        "replace_building": False,
    }
    values.update(overrides)
    return SpeechIntent(**values)  # type: ignore[arg-type]


def _cb(
    kind: str,
    *,
    utterance_id: str = "utt:1",
    sequence: int = 1,
    now_ms: int = 11_000,
    backend: str = "sapi",
    generation: int = 4,
    dispatch: int = 1,
    detail: str | None = None,
) -> TtsCallback:
    return TtsCallback(
        schema_version="tts-callback/2",
        callback_id=f"ttscb:{utterance_id}:{sequence}",
        kind=kind,
        utterance_id=utterance_id,
        worker_sequence=sequence,
        backend=backend,
        backend_generation=generation,
        dispatch_generation=dispatch,
        observed_mono_ms=now_ms,
        detail_code=detail,
    )


def test_try_start_builds_and_busy_creates_no_waiter() -> None:
    lane = SpeechLane()
    opened = lane.try_start(_intent())
    assert opened.reason == "started_building"
    assert opened.lane == "building"
    assert opened.waiter_created is False
    busy = lane.try_start(_intent(utterance_id="utt:2"))
    assert busy.reason == "lane_busy"
    assert busy.lane == "building"
    assert busy.waiter_created is False
    assert lane.pending_count == 0
    assert lane.lane == "building"


def test_commit_accept_consumes_opportunity_once() -> None:
    queue = OpportunityQueue()
    queued = queue.admit(_opp())
    reserved = queue.reserve(queued.opportunity.opportunity_id, now_ms=10_000)
    lane = SpeechLane(queue)
    lane.try_start(_intent(reservation_token=reserved.opportunity.reservation_token))
    committed = lane.commit("utt:1", now_ms=10_100)
    assert committed.reason == "committed"
    assert committed.lane == "committed"
    duck = lane.note_progress("utt:1", "duck_complete", now_ms=10_200)
    assert duck.opportunity_effect is None
    assert duck.lane == "committed"
    accepted = lane.acknowledge(
        "utt:1", adapter="sapi", boundary="async_speak_positive_stream", now_ms=10_300
    )
    assert accepted.reason == "playback_accepted"
    assert accepted.lane == "speaking"
    assert accepted.public_command == "SPEECH_STARTED"
    assert accepted.opportunity_effect == "consumed"
    assert accepted.accepted is True
    again = lane.acknowledge(
        "utt:1", adapter="sapi", boundary="async_speak_positive_stream", now_ms=10_400
    )
    assert again.reason == "protocol_violation"
    assert reserved.opportunity.opportunity_id not in queue.live_ids()


def test_pre_accept_failure_releases_post_accept_stays_consumed() -> None:
    queue = OpportunityQueue()
    queued = queue.admit(_opp())
    reserved = queue.reserve(queued.opportunity.opportunity_id, now_ms=10_000)
    token = reserved.opportunity.reservation_token
    first = SpeechLane(queue)
    first.try_start(_intent(reservation_token=token))
    first.commit("utt:1", now_ms=10_100)
    failed = first.callback(_cb("failed", detail="backend_rejected", sequence=1))
    assert failed.reason == "speech_failed"
    assert failed.lane == "idle"
    assert failed.opportunity_effect == "released"
    assert "opp:1" in first.queue.live_ids()  # type: ignore[union-attr]

    queued2 = queue.admit(_opp(opportunity_id="opp:2", event_id="event:2", candidate_id="cand:2"))
    reserved2 = queue.reserve(queued2.opportunity.opportunity_id, now_ms=10_000)
    second = SpeechLane(queue)
    second.try_start(
        _intent(
            utterance_id="utt:2",
            opportunity_id="opp:2",
            reservation_token=reserved2.opportunity.reservation_token,
        )
    )
    second.commit("utt:2", now_ms=10_100)
    second.acknowledge(
        "utt:2", adapter="sapi", boundary="async_speak_positive_stream", now_ms=10_300
    )
    later = second.callback(
        _cb("failed", utterance_id="utt:2", sequence=2, detail="backend_audio_error")
    )
    assert later.reason == "speech_failed"
    assert later.opportunity_effect == "consumed"
    assert "opp:2" not in queue.live_ids()


def test_race_event_never_preempts_committed_or_speaking() -> None:
    lane = SpeechLane()
    lane.try_start(_intent())
    lane.commit("utt:1", now_ms=10_100)
    raced = lane.note_race_event(now_ms=10_200)
    assert raced.reason == "race_ignored"
    assert raced.lane == "committed"
    assert raced.waiter_created is False
    lane.acknowledge("utt:1", adapter="sapi", boundary="async_speak_positive_stream", now_ms=10_300)
    still = lane.note_race_event(now_ms=10_400)
    assert still.reason == "race_ignored"
    assert still.lane == "speaking"


def test_cancel_only_for_allowed_reasons() -> None:
    lane = SpeechLane()
    lane.try_start(_intent())
    lane.commit("utt:1", now_ms=10_100)
    rejected = lane.cancel("race_event", now_ms=10_200)
    assert rejected.reason == "cancel_rejected"
    assert rejected.lane == "committed"
    allowed = lane.cancel("commentary_disable", now_ms=10_300)
    assert allowed.reason == "cancel_requested"
    assert allowed.lane == "stopping"
    assert allowed.opportunity_effect != "consumed"


def test_manual_skips_building_and_stays_outside_opportunity() -> None:
    lane = SpeechLane()
    manual = lane.try_start(
        _intent(
            utterance_id="utt:man",
            source_kind="manual",
            opportunity_id=None,
            reservation_token=None,
            plan_id=None,
            beat_id=None,
            episode_id=None,
            manual_request_id="man:1",
            text="check one two",
        )
    )
    assert manual.reason == "manual_committed"
    assert manual.lane == "committed"
    assert manual.opportunity_effect is None
    disable = lane.cancel("commentary_disable", now_ms=10_200)
    assert disable.reason == "cancel_rejected"
    shutdown = lane.cancel("shutdown", now_ms=10_300)
    assert shutdown.reason == "cancel_requested"


def test_manual_latch_abandon_cannot_speak() -> None:
    lane = SpeechLane()
    abandoned = lane.abandon_manual("man:late")
    assert abandoned.reason == "latch_abandoned"
    late = lane.try_start(
        _intent(
            utterance_id="utt:late",
            source_kind="manual",
            opportunity_id=None,
            reservation_token=None,
            plan_id=None,
            beat_id=None,
            episode_id=None,
            manual_request_id="man:late",
            text="too late",
        )
    )
    assert late.reason == "latch_abandoned"
    assert late.lane == "idle"
    assert MANUAL_LATCH_TIMEOUT_MS == 1_000


def test_exactly_one_start_and_one_terminal() -> None:
    lane = SpeechLane()
    lane.try_start(_intent())
    lane.commit("utt:1", now_ms=10_100)
    lane.acknowledge("utt:1", adapter="sapi", boundary="async_speak_positive_stream", now_ms=10_300)
    done = lane.callback(_cb("completed", sequence=2, now_ms=12_000))
    assert done.reason == "speech_completed"
    assert done.lane == "idle"
    assert done.public_command == "SPEECH_COMPLETED"
    assert lane.start_count == 1
    assert lane.terminal_count == 1
    stale = lane.callback(_cb("completed", sequence=3, now_ms=12_100))
    assert stale.reason == "stale_callback"
    assert lane.terminal_count == 1


def test_backend_auto_order_and_no_failover() -> None:
    assert resolve_backend("auto", available=("espeak", "sapi")) == "sapi"
    assert resolve_backend("auto", available=("espeak",)) == "espeak"
    assert resolve_backend("auto", available=("supertonic",)) is None
    assert resolve_backend("supertonic", available=("supertonic",)) == "supertonic"
    assert AUTO_BACKEND_ORDER == ("sapi", "espeak")
    lane = SpeechLane()
    opened = lane.try_start(_intent(backend="auto", available_backends=("espeak",)))
    assert opened.utterance is not None
    assert opened.utterance.backend == "espeak"
    lane.commit("utt:1", now_ms=10_100)
    fail = lane.callback(_cb("failed", backend="espeak", detail="backend_unavailable"))
    assert fail.reason == "speech_failed"
    assert fail.failover_attempted is False


def test_acknowledgement_boundaries_never_use_synthesis() -> None:
    assert ACCEPTANCE_BOUNDARIES["sapi"] == "async_speak_positive_stream"
    assert ACCEPTANCE_BOUNDARIES["sapi_waveout"] == "waveout_write_success"
    assert ACCEPTANCE_BOUNDARIES["espeak"] == "owned_spawn_probe_ok"
    assert ACCEPTANCE_BOUNDARIES["supertonic"] == "sounddevice_play_accepted"
    lane = SpeechLane()
    lane.try_start(_intent(adapter="espeak", backend="espeak"))
    lane.commit("utt:1", now_ms=10_100)
    early = lane.acknowledge("utt:1", adapter="espeak", boundary="synthesis_pcm", now_ms=10_200)
    assert early.reason == "boundary_not_reached"
    assert early.lane == "committed"
    assert early.accepted is False
    ok = lane.acknowledge("utt:1", adapter="espeak", boundary="owned_spawn_probe_ok", now_ms=10_300)
    assert ok.reason == "playback_accepted"


def test_watchdog_quarantine_and_newer_preflight_restore() -> None:
    lane = SpeechLane()
    lane.try_start(_intent())
    lane.commit("utt:1", now_ms=10_000)
    timed = lane.watchdog("start", now_ms=10_000 + START_TIMEOUT_MS)
    assert timed.reason == "watchdog_start"
    assert timed.lane == "stopping"
    stop = lane.watchdog("stop", now_ms=10_000 + START_TIMEOUT_MS + STOP_TIMEOUT_MS)
    assert stop.reason == "quarantined"
    assert stop.lane == "idle"
    blocked = lane.try_start(_intent(utterance_id="utt:2", backend_generation=4))
    assert blocked.reason == "tts_unavailable"
    restored = lane.note_health(backend_generation=5, status="ready", now_ms=20_000)
    assert restored.reason == "health_ready"
    opened = lane.try_start(_intent(utterance_id="utt:3", backend_generation=5))
    assert opened.reason == "started_building"


def test_pending_generation_rejects_new_admission() -> None:
    lane = SpeechLane()
    lane.note_health(backend_generation=7, status="pending", now_ms=10_000)
    rejected = lane.try_start(_intent(backend_generation=7))
    assert rejected.reason == "tts_unavailable"
    assert rejected.lane == "idle"


def test_replay_fixtures_cover_transition_identity_and_expiry() -> None:
    transition = json.loads((FIXTURES / "transition.json").read_text(encoding="utf-8"))
    identity = json.loads((FIXTURES / "counterfactual_identity.json").read_text(encoding="utf-8"))
    expiry = json.loads((FIXTURES / "expiry.json").read_text(encoding="utf-8"))
    lane = SpeechLane()
    step = lane.try_start(
        _intent(utterance_id=transition["utteranceId"], now_ms=transition["nowMs"])
    )
    assert step.reason == transition["expectReason"]
    assert step.lane == transition["expectLane"]
    assert step.schema_version == SCHEMA_VERSION
    other = lane.try_start(_intent(utterance_id=identity["otherUtteranceId"]))
    assert other.reason == "lane_busy"
    assert other.utterance is None or other.utterance.utterance_id != identity["otherUtteranceId"]
    watchdog = SpeechLane()
    watchdog.try_start(_intent(now_ms=expiry["dispatchedMonoMs"]))
    watchdog.commit("utt:1", now_ms=expiry["dispatchedMonoMs"])
    fired = watchdog.watchdog("start", now_ms=expiry["nowMs"])
    assert fired.reason == expiry["expectReason"]
    assert expiry["nowMs"] - expiry["dispatchedMonoMs"] >= expiry["startTimeoutMs"]


def test_records_latency_and_exports_stay_out() -> None:
    lane = SpeechLane()
    lane.try_start(_intent())
    lane.commit("utt:1", now_ms=10_100)
    accepted = lane.acknowledge(
        "utt:1", adapter="sapi", boundary="async_speak_positive_stream", now_ms=10_400
    )
    assert accepted.latency_ms is not None
    assert accepted.latency_ms["commit_to_accept"] == 300
    source = SOURCE.read_text(encoding="utf-8")
    assert "speech_lane" not in events_exports
    for banned in (
        "NarrativeRuntime",
        "eval(",
        "exec(",
        "compile(",
        "irswitch.commentary",
        "irswitch.overlay",
        "import sounddevice",
        "sounddevice.play(",
        "win32com",
    ):
        assert banned not in source
