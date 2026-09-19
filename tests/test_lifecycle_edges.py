"""#252 exact-once stream/session lifecycle triggers."""

from __future__ import annotations

from irswitch.commentary.opener import STREAM_START
from irswitch.contracts import SessionRef
from irswitch.events.lifecycle_edges import (
    CANONICAL_LIFECYCLE_KINDS,
    LEGACY_STREAM_START,
    LifecycleCommand,
    LifecycleIdentity,
    LifecycleSample,
    LifecycleStep,
    LifecycleTriggerBank,
)
from irswitch.race.session_end import SessionEndTracker


def _cmd(kind: str, **overrides: object) -> LifecycleCommand:
    payload: dict[str, object] = {
        "kind": kind,
        "start_reason": None,
        "session_ref": SessionRef("sub:1", 2),
        "occurrence_id": "1:race:0",
        "lineage_id": "1:practice:0>1:race:0",
        "end_reason": None,
    }
    payload.update(overrides)
    return LifecycleCommand(**payload)  # type: ignore[arg-type]


def _sample(**overrides: object) -> LifecycleSample:
    payload: dict[str, object] = {
        "timeline_revision": 1,
        "observed_mono_ms": 1_000,
        "source_snapshot_id": "snap:timeline:1",
        "broadcast_epoch": 4,
        "stream_epoch": 1,
        "narrative_run_active": True,
        "obs_state": "active",
        "session_ref": SessionRef("sub:1", 2),
        "stage": "race",
        "occurrence_id": "1:race:0",
        "lineage_id": "1:practice:0>1:race:0",
        "previous_occurrence_id": "1:practice:0",
        "previous_lineage_id": "1:practice:0",
        "transition_reasons": ("broadcast_started", "session_started"),
        "commands": (
            _cmd("STREAM_STARTED", start_reason="normal", occurrence_id=None, lineage_id=None),
            _cmd("SESSION_STARTED"),
        ),
        "checkered_active": False,
        "hero_finished": False,
        "hero_id": "car:12",
        "connected": True,
    }
    payload.update(overrides)
    return LifecycleSample(**payload)  # type: ignore[arg-type]


def _kinds(step: LifecycleStep) -> list[str]:
    return [item.kind for item in step.candidates]


def test_canonical_catalog_rejects_stream_start_alias() -> None:
    assert STREAM_START == "STREAM_START"
    assert LEGACY_STREAM_START == "STREAM_START"
    assert "STREAM_START" not in CANONICAL_LIFECYCLE_KINDS
    assert "STREAM_STARTED" in CANONICAL_LIFECYCLE_KINDS
    key = LifecycleIdentity(kind="STREAM_STARTED", stream_epoch=1)
    assert key.candidate_id().startswith("lifecycle:STREAM_STARTED:1")
    bank = LifecycleTriggerBank()
    rejected = bank.observe(_sample(commands=(_cmd(STREAM_START, start_reason="normal"),)))
    assert rejected.accepted is True
    assert rejected.diagnostic == "legacy_stream_start_rejected"
    assert _kinds(rejected) == []
    migrated = bank.observe(
        _sample(
            timeline_revision=2,
            observed_mono_ms=2_000,
            commands=(_cmd("STREAM_STARTED", start_reason="normal", occurrence_id=None),),
        )
    )
    assert _kinds(migrated) == ["STREAM_STARTED"]
    assert migrated.candidates[0].source_class == "lifecycle"
    assert migrated.candidates[0].detector_observation_id is None
    assert migrated.candidates[0].narrative_kind == "stream.started"
    assert migrated.candidates[0].tape_channel == "stream.lifecycle"


def test_live_session_end_tracker_keeps_checkered_and_hero_finish_distinct() -> None:
    tracker = SessionEndTracker()
    checkered, finished, _mute = tracker.update(
        session_state=5,
        lap_completed=12,
        on_pit_road=False,
        player_track_surface=3,
        player_lap_dist_pct=0.4,
    )
    assert checkered is True
    assert finished is False
    _checkered, finished, _mute = tracker.update(
        session_state=5,
        lap_completed=13,
        on_pit_road=False,
        player_track_surface=3,
        player_lap_dist_pct=0.02,
    )
    assert finished is True


def test_confirmed_transition_emits_once_and_replays_are_noops() -> None:
    bank = LifecycleTriggerBank()
    first = bank.observe(_sample())
    assert _kinds(first) == ["STREAM_STARTED", "SESSION_STARTED"]
    assert first.candidates[0].reason_code == "normal"
    assert first.candidates[1].previous_occurrence_id == "1:practice:0"
    assert first.candidates[1].occurrence_id == "1:race:0"
    replay = bank.observe(
        _sample(
            timeline_revision=2,
            observed_mono_ms=2_000,
            commands=(_cmd("SESSION_STARTED"),),
            transition_reasons=("session_started",),
        )
    )
    assert _kinds(replay) == []
    storm = [
        _kinds(
            bank.observe(
                _sample(
                    timeline_revision=3 + seq,
                    observed_mono_ms=3_000 + seq,
                    commands=(),
                    transition_reasons=(),
                    checkered_active=False,
                )
            )
        )
        for seq in range(4)
    ]
    assert storm == [[], [], [], []]


def test_duplicate_and_stale_revisions_are_audited_noops() -> None:
    bank = LifecycleTriggerBank()
    bank.observe(_sample())
    dup = bank.observe(_sample())
    assert dup.accepted is False
    assert dup.diagnostic == "lifecycle_revision_duplicate"
    assert _kinds(dup) == []
    bank.observe(
        _sample(timeline_revision=2, observed_mono_ms=2_000, commands=(), transition_reasons=())
    )
    stale = bank.observe(_sample(timeline_revision=1, observed_mono_ms=500, commands=()))
    assert stale.accepted is False
    assert stale.diagnostic == "lifecycle_revision_stale"
    assert _kinds(stale) == []


def test_checkered_session_end_and_hero_finish_are_distinct() -> None:
    bank = LifecycleTriggerBank()
    bank.observe(_sample())
    flagged = bank.observe(
        _sample(
            timeline_revision=2,
            observed_mono_ms=2_000,
            commands=(),
            transition_reasons=(),
            checkered_active=True,
        )
    )
    assert _kinds(flagged) == ["SESSION_CHECKERED"]
    assert flagged.candidates[0].narrative_kind == "session.checkered"
    assert flagged.candidates[0].tape_channel == "race.control.flag"
    hero = bank.observe(
        _sample(
            timeline_revision=3,
            observed_mono_ms=3_000,
            commands=(),
            transition_reasons=(),
            checkered_active=True,
            hero_finished=True,
        )
    )
    assert _kinds(hero) == ["FINISH"]
    assert hero.candidates[0].narrative_kind == "session.hero_finish"
    assert hero.candidates[0].tape_channel == "race.session.finish"
    ended = bank.observe(
        _sample(
            timeline_revision=4,
            observed_mono_ms=4_000,
            narrative_run_active=True,
            commands=(_cmd("SESSION_ENDED", end_reason="completed", occurrence_id="1:race:0"),),
            transition_reasons=("session_ended",),
            checkered_active=True,
            hero_finished=True,
            occurrence_id=None,
            lineage_id=None,
            session_ref=None,
            stage=None,
        )
    )
    assert _kinds(ended) == ["SESSION_ENDED"]
    assert ended.candidates[0].reason_code == "completed"
    assert {item.kind for item in (flagged.candidates + hero.candidates + ended.candidates)} == {
        "SESSION_CHECKERED",
        "FINISH",
        "SESSION_ENDED",
    }


def test_stream_end_follows_session_invalidation_before_disposal() -> None:
    bank = LifecycleTriggerBank()
    bank.observe(_sample())
    closing = bank.observe(
        _sample(
            timeline_revision=2,
            observed_mono_ms=8_000,
            narrative_run_active=False,
            obs_state="inactive",
            session_ref=None,
            stage=None,
            occurrence_id=None,
            lineage_id=None,
            transition_reasons=("session_ended", "broadcast_ended"),
            commands=(
                _cmd("SESSION_ENDED", end_reason="stream_ended", occurrence_id="1:race:0"),
                _cmd("STREAM_ENDED", occurrence_id=None, lineage_id=None, session_ref=None),
            ),
            checkered_active=True,
            hero_finished=True,
        )
    )
    assert _kinds(closing) == ["SESSION_ENDED", "SESSION_CHECKERED", "FINISH", "STREAM_ENDED"]
    assert closing.candidates[-1].kind == "STREAM_ENDED"
    assert closing.candidates[-1].invalidate_speech is True
    assert closing.candidates[0].occurrence_id == "1:race:0"
    assert closing.candidates[0].previous_occurrence_id == "1:practice:0"


def test_reconnect_loading_and_process_attach_do_not_emit_extra_starts() -> None:
    bank = LifecycleTriggerBank()
    attached = bank.observe(
        _sample(
            commands=(
                _cmd(
                    "STREAM_STARTED",
                    start_reason="attached_live",
                    occurrence_id=None,
                    lineage_id=None,
                ),
            ),
            transition_reasons=("attached_live",),
        )
    )
    assert _kinds(attached) == ["STREAM_STARTED"]
    assert attached.candidates[0].reason_code == "attached_live"
    flicker = bank.observe(
        _sample(
            timeline_revision=2,
            observed_mono_ms=1_200,
            obs_state="unknown",
            connected=False,
            commands=(),
            transition_reasons=("broadcast_unknown",),
            session_ref=None,
            stage=None,
            occurrence_id=None,
            lineage_id=None,
        )
    )
    assert _kinds(flicker) == []
    resumed = bank.observe(
        _sample(
            timeline_revision=3,
            observed_mono_ms=1_400,
            obs_state="active",
            commands=(),
            transition_reasons=("broadcast_resumed",),
        )
    )
    assert _kinds(resumed) == []
    recovered = LifecycleTriggerBank().observe(
        _sample(
            commands=(
                _cmd(
                    "STREAM_STARTED",
                    start_reason="process_recovery",
                    occurrence_id=None,
                    lineage_id=None,
                ),
            ),
            transition_reasons=("process_recovery",),
        )
    )
    assert _kinds(recovered) == ["STREAM_STARTED"]
    assert recovered.candidates[0].reason_code == "process_recovery"


def test_rewind_attaches_previous_and_current_occurrence() -> None:
    bank = LifecycleTriggerBank()
    bank.observe(_sample())
    rewind = bank.observe(
        _sample(
            timeline_revision=2,
            observed_mono_ms=5_000,
            session_ref=SessionRef("sub:1", 1),
            stage="qualifying",
            occurrence_id="1:qualifying:1",
            lineage_id="1:practice:0>1:qualifying:1",
            previous_occurrence_id="1:race:0",
            previous_lineage_id="1:practice:0>1:race:0",
            transition_reasons=("session_ended", "session_started"),
            commands=(
                _cmd(
                    "SESSION_ENDED",
                    end_reason="rewind_superseded",
                    occurrence_id="1:race:0",
                    lineage_id="1:practice:0>1:race:0",
                    session_ref=SessionRef("sub:1", 2),
                ),
                _cmd(
                    "SESSION_STARTED",
                    occurrence_id="1:qualifying:1",
                    lineage_id="1:practice:0>1:qualifying:1",
                    session_ref=SessionRef("sub:1", 1),
                ),
            ),
        )
    )
    assert _kinds(rewind) == ["SESSION_ENDED", "SESSION_STARTED"]
    ended, started = rewind.candidates
    assert ended.occurrence_id == "1:race:0"
    assert ended.reason_code == "rewind_superseded"
    assert started.occurrence_id == "1:qualifying:1"
    assert started.previous_occurrence_id == "1:race:0"
    assert started.previous_lineage_id == "1:practice:0>1:race:0"
    assert started.lineage_id == "1:practice:0>1:qualifying:1"


def test_same_ref_restart_is_session_restarted_not_session_ended_alias() -> None:
    bank = LifecycleTriggerBank()
    bank.observe(_sample())
    restart = bank.observe(
        _sample(
            timeline_revision=2,
            observed_mono_ms=6_000,
            occurrence_id="1:race:1",
            lineage_id="1:practice:0>1:race:1",
            previous_occurrence_id="1:race:0",
            previous_lineage_id="1:practice:0>1:race:0",
            transition_reasons=("session_ended", "session_restarted"),
            commands=(
                _cmd("SESSION_ENDED", end_reason="same_ref_restart", occurrence_id="1:race:0"),
                _cmd(
                    "SESSION_RESTARTED",
                    occurrence_id="1:race:1",
                    lineage_id="1:practice:0>1:race:1",
                ),
            ),
        )
    )
    assert _kinds(restart) == ["SESSION_ENDED", "SESSION_RESTARTED"]
    assert restart.candidates[1].narrative_kind == "session.restarted"
    assert restart.candidates[1].phase == "impulse"


def test_missing_occurrence_and_empty_epoch_fail_soft() -> None:
    bank = LifecycleTriggerBank()
    missing = bank.observe(
        _sample(
            commands=(_cmd("SESSION_STARTED", occurrence_id=None, lineage_id=None),),
            occurrence_id=None,
            lineage_id=None,
            session_ref=None,
            stage=None,
        )
    )
    assert missing.accepted is True
    assert missing.diagnostic == "lifecycle_missing_occurrence"
    assert _kinds(missing) == []
    empty = LifecycleTriggerBank().observe(_sample(stream_epoch=0, commands=()))
    assert empty.accepted is True
    assert _kinds(empty) == []


def test_checkered_and_finish_do_not_fire_outside_race() -> None:
    bank = LifecycleTriggerBank()
    bank.observe(
        _sample(
            stage="practice",
            occurrence_id="1:practice:0",
            lineage_id="1:practice:0",
            commands=(
                _cmd("STREAM_STARTED", start_reason="normal", occurrence_id=None),
                _cmd(
                    "SESSION_STARTED",
                    occurrence_id="1:practice:0",
                    lineage_id="1:practice:0",
                    session_ref=SessionRef("sub:1", 0),
                ),
            ),
        )
    )
    out = bank.observe(
        _sample(
            timeline_revision=2,
            observed_mono_ms=2_000,
            stage="practice",
            occurrence_id="1:practice:0",
            lineage_id="1:practice:0",
            commands=(),
            transition_reasons=(),
            checkered_active=True,
            hero_finished=True,
        )
    )
    assert _kinds(out) == []


def test_new_stream_epoch_can_reuse_session_numbers() -> None:
    bank = LifecycleTriggerBank()
    bank.observe(_sample())
    nxt = bank.observe(
        _sample(
            timeline_revision=2,
            observed_mono_ms=9_000,
            stream_epoch=2,
            occurrence_id="2:race:0",
            lineage_id="2:race:0",
            previous_occurrence_id=None,
            previous_lineage_id=None,
            commands=(
                _cmd("STREAM_STARTED", start_reason="normal", occurrence_id=None),
                _cmd(
                    "SESSION_STARTED",
                    occurrence_id="2:race:0",
                    lineage_id="2:race:0",
                ),
            ),
        )
    )
    assert _kinds(nxt) == ["STREAM_STARTED", "SESSION_STARTED"]
    assert nxt.candidates[0].identity.stream_epoch == 2
    assert nxt.candidates[1].occurrence_id == "2:race:0"


def test_reason_code_replay_fixture_is_stable() -> None:
    bank = LifecycleTriggerBank()
    first = bank.observe(_sample())
    second = bank.observe(
        _sample(
            timeline_revision=2,
            observed_mono_ms=2_000,
            commands=(),
            transition_reasons=(),
            checkered_active=True,
        )
    )
    third = bank.observe(
        _sample(
            timeline_revision=3,
            observed_mono_ms=3_000,
            narrative_run_active=False,
            obs_state="inactive",
            session_ref=None,
            stage=None,
            occurrence_id=None,
            lineage_id=None,
            transition_reasons=("session_ended", "broadcast_ended"),
            commands=(
                _cmd("SESSION_ENDED", end_reason="stream_ended"),
                _cmd("RESET", occurrence_id=None, lineage_id=None, session_ref=None),
                _cmd("STREAM_ENDED", occurrence_id=None, lineage_id=None, session_ref=None),
            ),
            checkered_active=True,
            hero_finished=True,
        )
    )
    assert [
        (_kinds(item), [candidate.reason_code for candidate in item.candidates])
        for item in (first, second, third)
    ] == [
        (["STREAM_STARTED", "SESSION_STARTED"], ["normal", "session_started"]),
        (["SESSION_CHECKERED"], ["session_checkered"]),
        (
            ["SESSION_ENDED", "FINISH", "STREAM_ENDED"],
            ["stream_ended", "hero_finished", "broadcast_ended"],
        ),
    ]
    assert "RESET" not in CANONICAL_LIFECYCLE_KINDS
    assert "SESSION_REWOUND" not in CANONICAL_LIFECYCLE_KINDS
