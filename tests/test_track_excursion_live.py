"""Synthetic current-signal traces; not a replay of the Test 7 recording."""

from dataclasses import replace

import pytest

from irswitch.events.scenarios.track_excursion import TrackExcursionDetector
from irswitch.overlay.models import RaceState


def state(**kwargs: object) -> RaceState:
    return replace(
        RaceState(
            connected=True,
            subsession_id="test",
            session_num=1,
            player_car_idx=2,
            overlay_mode="RACE",
            player_track_surface=3,
            player_tow_time=0.0,
            speed_mps=30.0,
            player_lap_dist_pct=0.5,
        ),
        **kwargs,
    )


def opened(detector: TrackExcursionDetector) -> list:
    assert detector.tick(state(), 0.0) == []
    assert detector.tick(state(player_track_surface=0), 0.2) == []
    return detector.tick(state(player_track_surface=0), 0.41)


def test_short_stale_window_still_opens_offtrack() -> None:
    detector = TrackExcursionDetector()
    assert detector.tick(state(), 0.0) == []
    assert detector.tick(state(stale_for_ms=1200, player_track_surface=0), 0.2) == []
    opened_events = detector.tick(state(stale_for_ms=1200, player_track_surface=0), 0.41)
    assert [event.metrics["beatId"] for event in opened_events] == ["offtrack"]


def test_offtrack_does_not_require_incident_points_and_keeps_parent_identity() -> None:
    detector = TrackExcursionDetector()
    root = opened(detector)
    assert [e.metrics["beatId"] for e in root] == ["offtrack"]
    assert detector.tick(state(), 0.6) == []
    rejoin = detector.tick(state(), 0.81)
    moving = detector.tick(state(), 1.21)
    assert rejoin[0].metrics["beatId"] == "track_rejoined"
    assert moving[0].metrics["beatId"] == "motion_restored"
    beats = root + rejoin + moving
    assert len({e.metrics["parentStoryId"] for e in beats}) == 1
    assert len({e.correlation_id for e in beats}) == 3
    assert all(e.metrics["cause"] == "unknown" for e in beats)


def test_stopped_is_not_inferred_from_offtrack_or_missing_speed() -> None:
    detector = TrackExcursionDetector()
    opened(detector)
    assert detector.tick(state(player_track_surface=0, speed_mps=None), 0.6) == []
    assert detector.tick(state(player_track_surface=0, speed_mps=None), 1.0) == []
    assert detector.tick(state(player_track_surface=0, speed_mps=0.0), 1.2) == []
    stop = detector.tick(state(player_track_surface=0, speed_mps=0.0), 1.56)
    assert stop[0].metrics["beatId"] == "stopped"
    assert detector.tick(state(player_track_surface=0, speed_mps=0.0), 1.9) == []


def test_tow_is_terminal_in_race_and_does_not_create_recovery() -> None:
    detector = TrackExcursionDetector()
    opened(detector)
    tow = detector.tick(state(player_tow_time=30.0, player_track_surface=-1), 0.6)
    assert tow[0].metrics["beatId"] == "tow_started_race"
    assert detector.tick(state(), 0.8) == []
    assert detector.tick(state(), 1.5) == []


@pytest.mark.parametrize(
    "change",
    [
        {"connected": False},
        {"run_epoch": 1},
        {"player_car_idx": 3},
        {"subsession_id": "other"},
        {"data_quality": "stale"},
    ],
)
def test_invalidated_scope_never_emits_old_closure(change: dict) -> None:
    detector = TrackExcursionDetector()
    opened(detector)
    assert detector.tick(state(**change), 0.6) == []
    assert detector.tick(state(), 0.8) == []
    assert detector.tick(state(), 1.5) == []


def test_unknown_surface_breaks_hold_and_large_time_gap_invalidates() -> None:
    detector = TrackExcursionDetector()
    opened(detector)
    assert detector.tick(state(), 0.6) == []
    assert detector.tick(state(player_track_surface=None), 0.8) == []
    assert detector.tick(state(player_track_surface=None), 1.81) == []
    traces = detector.take_trace()
    assert any(t["reason"] == "surface_unavailable" for t in traces)
    assert detector._episode == ""


def test_open_episode_survives_sample_gap() -> None:
    detector = TrackExcursionDetector()
    root = opened(detector)
    episode = root[0].metrics["parentStoryId"]
    assert detector.tick(state(player_track_surface=0), 1.8) == []
    assert detector._episode == episode
    assert detector.tick(state(), 2.0) == []
    rejoin = detector.tick(state(), 2.21)
    moving = detector.tick(state(), 2.61)
    assert rejoin[0].metrics["beatId"] == "track_rejoined"
    assert moving[0].metrics["beatId"] == "motion_restored"
    assert rejoin[0].metrics["parentStoryId"] == episode


def test_preopen_sample_gap_still_resets() -> None:
    detector = TrackExcursionDetector()
    assert detector.tick(state(), 0.0) == []
    assert detector.tick(state(player_track_surface=0), 0.2) == []
    assert detector._episode == ""
    assert detector.tick(state(player_track_surface=0), 1.3) == []
    assert detector._episode == ""
    assert detector._armed is False


def test_duplicate_or_out_of_order_frames_never_advance_holds() -> None:
    detector = TrackExcursionDetector()
    opened(detector)
    assert detector.tick(state(), 0.41) == []
    assert detector.tick(state(), 0.3) == []
    assert detector.tick(state(), 0.6) == []


def test_pit_return_never_claims_repairs_or_esc_without_evidence() -> None:
    detector = TrackExcursionDetector()
    opened(detector)
    assert detector.tick(state(on_pit_road=True, player_track_surface=2), 0.6) == []
    pit = detector.tick(state(on_pit_road=True, player_track_surface=1), 0.81)
    assert pit[0].metrics["beatId"] == "pit_return_observed"
    assert pit[0].metrics["damage"] == "unknown"


def test_episode_timeout_logs_silent_invalidation_not_invented_outcome() -> None:
    detector = TrackExcursionDetector()
    opened(detector)
    for i in range(1, 182):
        detector.tick(state(player_track_surface=0), 0.41 + i * 0.5)
    traces = detector.take_trace()
    assert any(t["reason"] == "episode_timeout" for t in traces)
    assert not any(t.get("beatId") == "run_continuation_lost" for t in traces)


@pytest.mark.parametrize("mode", ["active", "shadow", "legacy"])
def test_observer_mode_has_exactly_one_audible_owner(mode: str) -> None:
    from irswitch.overlay.models import TelemetrySnapshot
    from irswitch.overlay.settings import RaceObserverSettings
    from irswitch.race.observer import RaceObserver

    observer = RaceObserver(settings=RaceObserverSettings(scenario_mode=mode))
    snap = TelemetrySnapshot(connected=True, timestamp=0, subsession_id="test", session_num=1)
    for now, sample in [
        (0.0, state(incidents=0)),
        (0.2, state(incidents=0, player_track_surface=0)),
        (0.41, state(incidents=2, player_track_surface=0)),
    ]:
        observer.observe(snap, sample, now=now)
    types = [env.event_type for env in observer.take_derived_envelopes()]
    assert ("TRACK_EXCURSION" in types) == (mode == "active")
    assert ("INCIDENT_AFTERMATH" in types) == (mode != "active")
    assert bool(observer.excursion.take_trace()) == (mode != "legacy")


@pytest.mark.asyncio
@pytest.mark.parametrize("graph_mode", ["legacy", "active"])
async def test_observer_pipeline_consumer_tts_keeps_latest_truth_while_busy(
    monkeypatch, graph_mode: str
) -> None:
    from irswitch.commentary.consumer import CommentaryConsumer
    from irswitch.commentary.director import CommentaryDirector
    from irswitch.commentary.tts import NullTtsSink
    from irswitch.events.async_fanout import AsyncEventFanout
    from irswitch.overlay.models import BioState, TelemetrySnapshot
    from irswitch.overlay.settings import CommentarySettings
    from irswitch.race.ministory import MiniStoryRegistry
    from irswitch.race.observer import RaceObserver
    from irswitch.race.pipeline import RacePipeline

    clock = [0.0]
    monkeypatch.setattr("time.monotonic", lambda: clock[0])
    settings = CommentarySettings(enabled=True, graph_runtime_mode=graph_mode)
    sink = NullTtsSink()
    fanout = AsyncEventFanout()
    director = CommentaryDirector.from_defaults(settings, sink=sink)
    records = []
    consumer = CommentaryConsumer(
        fanout.subscribe("commentary"),
        director,
        lambda: (settings, "en"),
        decision_hook=lambda entry, now: records.append((now, entry)),
    )
    pipeline = RacePipeline(fanout, story_registry=MiniStoryRegistry())
    reset = pipeline.reset_session("test:1", reason="session_changed")
    await consumer.handle(reset)
    observer = RaceObserver()
    snap = TelemetrySnapshot(connected=True, timestamp=0, subsession_id="test", session_num=1)
    detected = []
    for now, sample in [
        (0.0, state()),
        (0.2, state(player_track_surface=0)),
        (0.41, state(player_track_surface=0)),
        (1.0, state(player_track_surface=0, speed_mps=0)),
        (1.4, state(player_track_surface=0, speed_mps=0)),
        (1.8, state()),
        (2.01, state()),
        (2.41, state()),
    ]:
        clock[0] = now + 10.0
        observer.observe(snap, sample, now=now)
        beats = [e for e in observer.take_derived_envelopes() if e.event_type == "TRACK_EXCURSION"]
        detected.extend(beats)
        pipeline.capture_context(
            race=sample,
            bio=BioState(),
            story=observer.context,
            telemetry_data={},
            captured_monotonic_ms=int(clock[0] * 1000),
            language="en",
            commentary_enabled=True,
        )
        batch = pipeline.publish_envelopes(
            beats, source="race_scenario", accepted_monotonic_ms=int(clock[0] * 1000)
        )
        if batch:
            assert all(event.audiences == ("commentary",) for event in batch.events)
            await consumer.handle(batch)
        if now == 0.41:
            sink.force_busy = True
    sink.force_busy = False
    clock[0] = 17.0
    director.tick(17.0, allow_filler=False)
    consumer._drain_graph_lifecycle()
    assert [env.metrics["beatId"] for env in detected] == [
        "offtrack",
        "stopped",
        "track_rejoined",
        "motion_restored",
    ]
    assert [utterance.node_id for utterance in sink.spoken] == [
        "track_excursion",
        "motion_restored",
    ]
    assert len({e.event_id for e in detected}) == 4
    assert len({e.metrics["parentStoryId"] for e in detected}) == 1
    assert any(
        entry.get("action") == "speaking" and entry.get("beatId") == "motion_restored"
        for _, entry in records
    )
    assert not any("incident" in u.text.lower() for u in sink.spoken)


def test_pending_old_phase_is_invalidated_but_audible_phase_is_not() -> None:
    from irswitch.race.ministory import MiniStoryRegistry, MiniStoryState

    detector = TrackExcursionDetector()
    root = opened(detector)[0]
    registry = MiniStoryRegistry()
    root_token = registry.observe(root).token
    assert root_token is not None
    registry.commit(root_token, None, locale="en")
    registry.mark_speaking(root_token)
    detector.tick(state(speed_mps=0, player_track_surface=0), 0.6)
    stopped = detector.tick(state(speed_mps=0, player_track_surface=0), 1.0)[0]
    stopped_token = registry.observe(stopped).token
    detector.tick(state(), 1.2)
    rejoin = detector.tick(state(), 1.41)[0]
    registry.observe(rejoin)
    assert registry.state_of(root_token) == MiniStoryState.SPEAKING
    assert registry.state_of(stopped_token) == MiniStoryState.INVALIDATED


def test_confirmed_offtrack_vocabulary_survives_every_speech_validation_stage() -> None:
    from irswitch.commentary.graph import load_sequence_graph
    from irswitch.commentary.validator import validate_utterance

    node = load_sequence_graph().nodes["track_excursion"]
    for wrong in [
        "An incident happened.",
        "He lost control.",
        "A contact sends him off track.",
        "Po incidentu je mimo trať.",
        "Má poškozené auto mimo trať.",
    ]:
        assert validate_utterance(wrong, node), wrong
    assert not validate_utterance("He has gone off track.", node)


def test_finish_tier_still_dominates_excursion_and_counter_is_lower() -> None:
    from irswitch.commentary.priorities import editorial_priority

    assert editorial_priority("FINISH") > editorial_priority("TRACK_EXCURSION")
    assert editorial_priority("TRACK_EXCURSION") > editorial_priority(
        "INCIDENT", {"branch": "points"}
    )


@pytest.mark.parametrize(
    "change",
    [{"connected": False}, {"player_car_idx": 9}, {"data_quality": "stale"}, {"speed_mps": 15.0}],
)
def test_context_invalidates_waiting_stopped_speech(change: dict) -> None:
    from dataclasses import asdict

    from irswitch.race.ministory import MiniStoryRegistry, MiniStoryState

    detector = TrackExcursionDetector()
    opened(detector)
    detector.tick(state(player_track_surface=0, speed_mps=0), 0.6)
    stop = detector.tick(state(player_track_surface=0, speed_mps=0), 1.0)[0]
    registry = MiniStoryRegistry()
    token = registry.observe(stop).token
    registry.observe_context({"race": asdict(state(**change))})
    assert registry.state_of(token) == MiniStoryState.INVALIDATED


def test_final_tts_vocabulary_gate_and_correlated_diagnostics(monkeypatch) -> None:
    from irswitch.commentary.director import CommentaryDirector
    from irswitch.commentary.tts import ProcessTtsSink, TtsResult
    from irswitch.overlay.settings import CommentarySettings

    event = opened(TrackExcursionDetector())[0]
    cfg = CommentarySettings(enabled=True)
    director = CommentaryDirector.from_defaults(cfg)
    utterance = director.observe([event], None, 1.0)
    assert utterance is not None
    playback = []
    diagnostics = []

    def speak(text, **kwargs):
        kwargs["wait_before_play"]()
        playback.append(text)
        return TtsResult("test", True)

    monkeypatch.setattr("irswitch.commentary.tts.speak_text", speak)
    sink = ProcessTtsSink(cfg, on_speech_diagnostic=diagnostics.append)
    sink._speak(replace(utterance, text="An incident happened."))
    assert playback == []
    sink._speak(utterance)
    assert len(playback) == 1
    assert [row["action"] for row in diagnostics] == [
        "tts_requested",
        "playback_requested",
        "tts_result",
    ]
    assert all(row["parentStoryId"] == event.metrics["parentStoryId"] for row in diagnostics)
    assert diagnostics[-1]["reason"] == "played"


def test_disconnected_idle_emits_no_trace() -> None:
    detector = TrackExcursionDetector()
    idle = state(connected=False, overlay_mode="GENERIC", subsession_id=None, session_num=None)
    assert detector.tick(idle, 0.0) == []
    assert detector.take_trace() == []
    assert detector.tick(idle, 0.2) == []
    assert detector.take_trace() == []


def test_disconnect_after_episode_still_traces_invalidation() -> None:
    detector = TrackExcursionDetector()
    opened(detector)
    assert detector.tick(state(connected=False), 0.6) == []
    traces = detector.take_trace()
    assert any(row.get("action") == "invalidated" for row in traces)
    assert any(row.get("reason") == "evidence_unavailable" for row in traces)


def test_observation_trace_is_change_based_not_per_tick() -> None:
    detector = TrackExcursionDetector()
    detector.tick(state(), 0.0)
    detector.take_trace()
    for i in range(1, 20):
        detector.tick(state(speed_mps=30 + i), i * 0.2)
    assert detector.take_trace() == []
    detector.tick(state(player_tow_time=None), 4.0)
    trace = detector.take_trace()
    assert len(trace) == 1 and trace[0]["towEvidence"] == "unknown"


def test_new_offtrack_after_confirmed_rejoin_starts_new_episode() -> None:
    detector = TrackExcursionDetector()
    first = opened(detector)[0]
    detector.tick(state(speed_mps=0), 0.6)
    assert detector.tick(state(speed_mps=0), 0.81)[0].metrics["beatId"] == "track_rejoined"
    assert detector.tick(state(player_track_surface=0), 1.0) == []
    second = detector.tick(state(player_track_surface=0), 1.21)[0]
    assert second.metrics["beatId"] == "offtrack"
    assert second.metrics["parentStoryId"] != first.metrics["parentStoryId"]


def test_continuously_missing_surface_does_not_join_to_later_motion() -> None:
    detector = TrackExcursionDetector()
    opened(detector)
    for now in (0.6, 0.9, 1.2, 1.6):
        assert detector.tick(state(player_track_surface=None), now) == []
    assert detector.tick(state(), 1.8) == []
    assert detector.tick(state(), 2.5) == []
    assert any(row["reason"] == "surface_unavailable" for row in detector.take_trace())


def test_finish_arriving_when_excursion_is_ready_does_not_flush_lower_tier_first() -> None:
    from irswitch.commentary.director import CommentaryDirector
    from irswitch.commentary.tts import NullTtsSink
    from irswitch.events.envelope import make_envelope
    from irswitch.overlay.settings import CommentarySettings

    detector = TrackExcursionDetector()
    root = opened(detector)
    detector.tick(state(), 0.6)
    rejoin = detector.tick(state(), 0.81)
    sink = NullTtsSink()
    director = CommentaryDirector.from_defaults(CommentarySettings(enabled=True), sink=sink)
    director.observe(root, None, 1.0)
    director.observe(rejoin, None, 1.2)
    assert len(director._scheduler) == 1
    finish = make_envelope(
        event_type="FINISH", phase="RESULT", mode="RACE", metrics={"position": 3}
    )
    director.observe([finish], None, 8.0)
    assert sink.spoken[-1].event_type == "FINISH"


def _prime_pace(detector: TrackExcursionDetector, *, speed_mps: float = 40.0) -> float:
    now = 0.0
    dist = 0.10
    while dist <= 0.90:
        assert detector.tick(state(player_lap_dist_pct=dist, speed_mps=speed_mps), now) == []
        dist += 0.02
        now += 0.15
    detector.tick(state(player_track_surface=0, player_lap_dist_pct=0.52, speed_mps=speed_mps), now)
    now += 0.21
    root = detector.tick(
        state(player_track_surface=0, player_lap_dist_pct=0.52, speed_mps=speed_mps), now
    )
    assert root and root[0].metrics["beatId"] == "offtrack"
    return now


def test_motion_restored_keeps_episode_open_for_pace_watch() -> None:
    detector = TrackExcursionDetector()
    now = _prime_pace(detector)
    detector.tick(state(player_lap_dist_pct=0.52, speed_mps=40.0), now + 0.2)
    rejoin = detector.tick(state(player_lap_dist_pct=0.52, speed_mps=40.0), now + 0.41)
    moving = detector.tick(state(player_lap_dist_pct=0.52, speed_mps=40.0), now + 1.02)
    assert rejoin[0].metrics["beatId"] == "track_rejoined"
    assert moving[0].metrics["beatId"] == "motion_restored"
    later = detector.tick(state(player_lap_dist_pct=0.52, speed_mps=40.0), now + 1.22)
    assert later == []
    assert detector._episode


def test_missing_pace_bin_abstains() -> None:
    detector = TrackExcursionDetector()
    now = 0.0
    for dist in (0.20, 0.28, 0.36):
        detector.tick(state(player_lap_dist_pct=dist, speed_mps=40.0), now)
        now += 0.2
    detector.tick(state(player_track_surface=0, player_lap_dist_pct=0.36, speed_mps=40.0), now)
    now += 0.21
    detector.tick(state(player_track_surface=0, player_lap_dist_pct=0.36, speed_mps=40.0), now)
    detector.tick(state(player_lap_dist_pct=0.36, speed_mps=40.0), now + 0.2)
    detector.tick(state(player_lap_dist_pct=0.36, speed_mps=40.0), now + 0.41)
    detector.tick(state(player_lap_dist_pct=0.36, speed_mps=40.0), now + 1.02)
    produced = []
    dist = 0.80
    t = now + 1.22
    for _ in range(30):
        dist = min(0.90, dist + 0.004)
        t += 0.2
        produced.extend(detector.tick(state(player_lap_dist_pct=dist, speed_mps=12.0), t))
    assert [e.metrics["beatId"] for e in produced] == []


def test_sustained_local_pace_loss_emits_without_damage_claim() -> None:
    detector = TrackExcursionDetector()
    now = _prime_pace(detector)
    detector.tick(state(player_lap_dist_pct=0.52, speed_mps=40.0), now + 0.2)
    detector.tick(state(player_lap_dist_pct=0.52, speed_mps=40.0), now + 0.41)
    detector.tick(state(player_lap_dist_pct=0.52, speed_mps=40.0), now + 1.02)
    produced = []
    dist = 0.52
    t = now + 1.22
    for _ in range(30):
        dist = min(0.90, dist + 0.01)
        t += 0.2
        produced.extend(detector.tick(state(player_lap_dist_pct=dist, speed_mps=18.0), t))
    ids = [e.metrics["beatId"] for e in produced]
    assert "pace_loss_sustained" in ids
    assert "normal_running_resumed" not in ids
    loss = next(e for e in produced if e.metrics["beatId"] == "pace_loss_sustained")
    assert loss.metrics["damage"] == "unknown"
    assert loss.metrics["cause"] == "unknown"
    assert loss.metrics["paceRatio"] < 0.55
    assert detector._episode


def test_observer_active_publishes_pace_loss_derived_envelope() -> None:
    from irswitch.overlay.models import TelemetrySnapshot
    from irswitch.overlay.settings import RaceObserverSettings
    from irswitch.race.observer import RaceObserver

    observer = RaceObserver(settings=RaceObserverSettings(scenario_mode="active"))
    snap = TelemetrySnapshot(connected=True, timestamp=0, subsession_id="test", session_num=1)
    now = 0.0
    dist = 0.10
    beats: list = []
    while dist <= 0.90:
        observer.observe(snap, state(player_lap_dist_pct=dist, speed_mps=40.0), now=now)
        beats.extend(
            e for e in observer.take_derived_envelopes() if e.event_type == "TRACK_EXCURSION"
        )
        dist += 0.02
        now += 0.15
    observer.observe(
        snap, state(player_track_surface=0, player_lap_dist_pct=0.52, speed_mps=40.0), now=now
    )
    beats.extend(e for e in observer.take_derived_envelopes() if e.event_type == "TRACK_EXCURSION")
    now += 0.21
    observer.observe(
        snap, state(player_track_surface=0, player_lap_dist_pct=0.52, speed_mps=40.0), now=now
    )
    beats.extend(e for e in observer.take_derived_envelopes() if e.event_type == "TRACK_EXCURSION")
    for later, sample in (
        (now + 0.2, state(player_lap_dist_pct=0.52, speed_mps=40.0)),
        (now + 0.41, state(player_lap_dist_pct=0.52, speed_mps=40.0)),
        (now + 1.02, state(player_lap_dist_pct=0.52, speed_mps=40.0)),
    ):
        observer.observe(snap, sample, now=later)
        beats.extend(
            e for e in observer.take_derived_envelopes() if e.event_type == "TRACK_EXCURSION"
        )
    dist = 0.52
    t = now + 1.22
    for _ in range(30):
        dist = min(0.90, dist + 0.01)
        t += 0.2
        observer.observe(snap, state(player_lap_dist_pct=dist, speed_mps=18.0), now=t)
        beats.extend(
            e for e in observer.take_derived_envelopes() if e.event_type == "TRACK_EXCURSION"
        )
    ids = [e.metrics["beatId"] for e in beats]
    assert "offtrack" in ids
    assert "motion_restored" in ids
    assert "pace_loss_sustained" in ids
    assert all(e.metrics["damage"] == "unknown" for e in beats)


def test_recovered_local_pace_closes_with_normal_running() -> None:
    detector = TrackExcursionDetector()
    now = _prime_pace(detector)
    detector.tick(state(player_lap_dist_pct=0.52, speed_mps=40.0), now + 0.2)
    detector.tick(state(player_lap_dist_pct=0.52, speed_mps=40.0), now + 0.41)
    detector.tick(state(player_lap_dist_pct=0.52, speed_mps=40.0), now + 1.02)
    produced = []
    dist = 0.52
    t = now + 1.22
    for _ in range(30):
        dist = min(0.90, dist + 0.01)
        t += 0.2
        produced.extend(detector.tick(state(player_lap_dist_pct=dist, speed_mps=38.0), t))
    ids = [e.metrics["beatId"] for e in produced]
    assert "normal_running_resumed" in ids
    assert "pace_loss_sustained" not in ids
    assert detector._episode == ""


def test_slow_corner_matching_frozen_bin_is_not_pace_loss() -> None:
    detector = TrackExcursionDetector()
    now = _prime_pace(detector, speed_mps=12.0)
    detector.tick(state(player_lap_dist_pct=0.52, speed_mps=12.0), now + 0.2)
    detector.tick(state(player_lap_dist_pct=0.52, speed_mps=12.0), now + 0.41)
    detector.tick(state(player_lap_dist_pct=0.52, speed_mps=12.0), now + 1.02)
    produced = []
    dist = 0.52
    t = now + 1.22
    for _ in range(30):
        dist = min(0.80, dist + 0.01)
        t += 0.2
        produced.extend(detector.tick(state(player_lap_dist_pct=dist, speed_mps=8.0), t))
    ids = [e.metrics["beatId"] for e in produced]
    assert "pace_loss_sustained" not in ids
    assert "normal_running_resumed" not in ids


def test_pace_copy_rejects_damage_and_allows_slower_or_recovered() -> None:
    from irswitch.commentary.graph import load_sequence_graph
    from irswitch.commentary.validator import validate_utterance

    graph = load_sequence_graph()
    loss = graph.nodes["pace_loss_sustained"]
    resume = graph.nodes["normal_running_resumed"]
    assert validate_utterance("The car is damaged after going off.", loss)
    assert validate_utterance("Poškozené auto jede pomaleji.", loss)
    assert not validate_utterance("He is continuing much slower after going off track.", loss)
    assert validate_utterance("He crashed and then got back up to speed.", resume)
    assert not validate_utterance("He is back up to speed after that off-track.", resume)
