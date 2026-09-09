"""#251 deterministic S/F and sector crossing edges."""

from __future__ import annotations

from pathlib import Path

from irswitch.contracts import SessionRef
from irswitch.events.direct_edges import DirectEdgeBank, DirectEdgeIdentity, DirectEdgeSample
from irswitch.events.lap import LapEmitter
from irswitch.events.sector_split import SectorSplitEmitter
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import EventPrioritySettings, EventSettings
from irswitch.race.timing import CrossingDetector, TimingStore, default_sectors

ROOT = Path(__file__).resolve().parents[1]


def _sample(**overrides: object) -> DirectEdgeSample:
    payload: dict[str, object] = {
        "sample_sequence": 1,
        "observed_mono_ms": 1_000,
        "source_snapshot_id": "snap:1",
        "broadcast_epoch": 4,
        "stream_epoch": 1,
        "session_ref": SessionRef("sub:1", 2),
        "occurrence_id": "1:race:0",
        "lineage_id": "1:practice:0>1:race:0",
        "overlay_mode": "RACE",
        "hero_id": "car:12",
        "connected": True,
        "lap_completed": 2,
        "last_lap_time_s": 112.5,
        "best_lap_time_s": 111.0,
        "incidents": 0,
        "session_finished": False,
        "player_finished": False,
    }
    payload.update(overrides)
    return DirectEdgeSample(**payload)  # type: ignore[arg-type]


def _kinds(step: object) -> list[str]:
    return [item.kind for item in step.candidates]


def _race_state(**overrides: object) -> RaceState:
    base: dict[str, object] = {
        "connected": True,
        "lap_completed": 3,
        "last_lap_time": 112.5,
        "best_lap_time": 111.0,
        "incidents": 0,
        "overlay_mode": "PRACTICE",
    }
    base.update(overrides)
    return RaceState(**base)  # type: ignore[arg-type]


def test_current_lap_emitter_emits_once_on_increment() -> None:
    emitter = LapEmitter(EventSettings(), EventPrioritySettings())
    assert emitter.tick(_race_state(lap_completed=2, last_lap_time=113.0), 1.0) == []
    out = emitter.tick(_race_state(lap_completed=3, last_lap_time=112.5), 2.0)
    assert [item.name for item in out] == ["lap_complete"]
    assert out[0].data["lap"] == 3


def test_current_sector_emitter_is_silent_in_race() -> None:
    store = TimingStore()
    det = CrossingDetector(points=default_sectors())
    emitter = SectorSplitEmitter(store, EventSettings(), EventPrioritySettings())
    for ev in det.update(car_id="player", lap_number=2, lap_dist_pct=0.40, timestamp=35.0):
        store.ingest_crossing(ev)
    assert emitter.tick(_race_state(overlay_mode="RACE"), 35.0) == []


def test_lap_identity_includes_occurrence_and_does_not_reuse_after_restart() -> None:
    key = DirectEdgeIdentity(
        kind="LAP_COMPLETE",
        stream_epoch=1,
        occurrence_id="1:race:0",
        hero_id="car:12",
        lap=3,
    )
    restarted = DirectEdgeIdentity(
        kind="LAP_COMPLETE",
        stream_epoch=1,
        occurrence_id="1:race:1",
        hero_id="car:12",
        lap=3,
    )
    assert key.candidate_id() != restarted.candidate_id()
    bank = DirectEdgeBank()
    bank.observe(_sample(lap_completed=2, last_lap_time_s=113.0))
    first = bank.observe(_sample(sample_sequence=2, observed_mono_ms=2_000, lap_completed=3))
    assert _kinds(first) == ["LAP_COMPLETE"]
    assert first.candidates[0].identity.occurrence_id == "1:race:0"
    replay = bank.observe(
        _sample(
            sample_sequence=3,
            observed_mono_ms=3_000,
            occurrence_id="1:race:1",
            lineage_id="1:practice:0>1:race:1",
            lap_completed=2,
            last_lap_time_s=113.0,
        )
    )
    assert _kinds(replay) == []
    again = bank.observe(
        _sample(
            sample_sequence=4,
            observed_mono_ms=4_000,
            occurrence_id="1:race:1",
            lineage_id="1:practice:0>1:race:1",
            lap_completed=3,
        )
    )
    assert _kinds(again) == ["LAP_COMPLETE"]
    assert again.candidates[0].identity.occurrence_id == "1:race:1"


def test_one_physical_sf_crossing_emits_one_lap_complete() -> None:
    bank = DirectEdgeBank()
    bank.observe(_sample())
    started = bank.observe(_sample(sample_sequence=2, observed_mono_ms=2_000, lap_completed=3))
    assert _kinds(started) == ["LAP_COMPLETE"]
    assert started.candidates[0].source_class == "direct"
    assert started.candidates[0].narrative_kind == "timing.lap_completed"
    assert started.candidates[0].tape_channel == "race.timing.lap"
    assert started.candidates[0].detector_observation_id is None
    storm = [
        _kinds(
            bank.observe(
                _sample(sample_sequence=seq, observed_mono_ms=2_000 + seq, lap_completed=3)
            )
        )
        for seq in range(3, 8)
    ]
    assert storm == [[], [], [], [], []]


def test_same_occurrence_reset_cannot_reuse_prior_lap_identity() -> None:
    bank = DirectEdgeBank()
    bank.observe(_sample(lap_completed=2, last_lap_time_s=113.0))
    bank.observe(_sample(sample_sequence=2, observed_mono_ms=2_000, lap_completed=3))
    reset = bank.observe(
        _sample(sample_sequence=3, observed_mono_ms=3_000, lap_completed=1, last_lap_time_s=90.0)
    )
    assert _kinds(reset) == []
    reuse = bank.observe(
        _sample(sample_sequence=4, observed_mono_ms=4_000, lap_completed=3, last_lap_time_s=112.5)
    )
    assert _kinds(reuse) == []


def test_missing_lap_time_waits_then_emits_once() -> None:
    bank = DirectEdgeBank()
    bank.observe(_sample(lap_completed=2, last_lap_time_s=113.0))
    waiting = bank.observe(
        _sample(sample_sequence=2, observed_mono_ms=2_000, lap_completed=3, last_lap_time_s=None)
    )
    assert _kinds(waiting) == []
    scored = bank.observe(_sample(sample_sequence=3, observed_mono_ms=2_250, lap_completed=3))
    assert _kinds(scored) == ["LAP_COMPLETE"]


def test_incident_during_lap_is_not_lap_complete() -> None:
    bank = DirectEdgeBank()
    bank.observe(_sample(lap_completed=2, last_lap_time_s=113.0, incidents=1))
    out = bank.observe(
        _sample(sample_sequence=2, observed_mono_ms=2_000, lap_completed=3, incidents=2)
    )
    assert _kinds(out) == []


def test_completed_race_is_not_a_lap_edge() -> None:
    bank = DirectEdgeBank()
    bank.observe(_sample(lap_completed=2, last_lap_time_s=113.0))
    finished = bank.observe(
        _sample(
            sample_sequence=2,
            observed_mono_ms=2_000,
            lap_completed=3,
            session_finished=True,
            player_finished=True,
        )
    )
    assert _kinds(finished) == []


def test_lap_eligibility_is_explicit_by_overlay_mode() -> None:
    bank = DirectEdgeBank()
    generic = bank.observe(_sample(overlay_mode="GENERIC", lap_completed=3))
    assert _kinds(generic) == []
    for mode, occurrence, lineage in (
        ("PRACTICE", "1:practice:0", "1:practice:0"),
        ("QUALIFYING", "1:qualifying:0", "1:practice:0>1:qualifying:0"),
        ("RACE", "1:race:0", "1:practice:0>1:race:0"),
    ):
        local = DirectEdgeBank()
        local.observe(
            _sample(
                overlay_mode=mode,
                occurrence_id=occurrence,
                lineage_id=lineage,
                lap_completed=2,
                last_lap_time_s=113.0,
            )
        )
        step = local.observe(
            _sample(
                sample_sequence=2,
                observed_mono_ms=2_000,
                overlay_mode=mode,
                occurrence_id=occurrence,
                lineage_id=lineage,
                lap_completed=3,
            )
        )
        assert _kinds(step) == ["LAP_COMPLETE"], mode


def test_sector_crossing_emits_once_and_handles_missing_metadata() -> None:
    bank = DirectEdgeBank()
    missing = bank.observe(
        _sample(
            overlay_mode="PRACTICE",
            occurrence_id="1:practice:0",
            lineage_id="1:practice:0",
            sector_id=None,
            sector_lap=2,
            sector_segment_time_s=33.0,
            sector_valid=True,
        )
    )
    assert _kinds(missing) == []
    first = bank.observe(
        _sample(
            sample_sequence=2,
            observed_mono_ms=2_000,
            overlay_mode="PRACTICE",
            occurrence_id="1:practice:0",
            lineage_id="1:practice:0",
            sector_id="S1",
            sector_lap=2,
            sector_segment_time_s=33.0,
            sector_valid=True,
        )
    )
    assert _kinds(first) == ["SECTOR_SPLIT"]
    assert first.candidates[0].narrative_kind == "timing.sector_split"
    assert first.candidates[0].tape_channel == "race.timing.sector"
    dup = bank.observe(
        _sample(
            sample_sequence=3,
            observed_mono_ms=2_250,
            overlay_mode="PRACTICE",
            occurrence_id="1:practice:0",
            lineage_id="1:practice:0",
            sector_id="S1",
            sector_lap=2,
            sector_segment_time_s=33.0,
            sector_valid=True,
        )
    )
    assert _kinds(dup) == []


def test_sector_best_on_improvement_and_silent_in_race() -> None:
    bank = DirectEdgeBank()
    kwargs = {
        "overlay_mode": "QUALIFYING",
        "occurrence_id": "1:qualifying:0",
        "lineage_id": "1:practice:0>1:qualifying:0",
        "sector_id": "S1",
        "sector_valid": True,
    }
    bank.observe(_sample(sector_lap=2, sector_segment_time_s=33.0, **kwargs))
    improved = bank.observe(
        _sample(
            sample_sequence=2,
            observed_mono_ms=2_000,
            sector_lap=3,
            sector_segment_time_s=32.4,
            **kwargs,
        )
    )
    assert _kinds(improved) == ["SECTOR_SPLIT", "SECTOR_BEST"]
    race = DirectEdgeBank()
    silent = race.observe(
        _sample(
            overlay_mode="RACE",
            sector_id="S1",
            sector_lap=2,
            sector_segment_time_s=33.0,
            sector_valid=True,
        )
    )
    assert _kinds(silent) == []


def test_duplicate_and_older_samples_are_audited_noops() -> None:
    bank = DirectEdgeBank()
    bank.observe(_sample())
    bank.observe(_sample(sample_sequence=2, observed_mono_ms=2_000, lap_completed=3))
    duplicate = bank.observe(_sample(sample_sequence=2, observed_mono_ms=2_000, lap_completed=3))
    assert duplicate.accepted is False
    assert duplicate.diagnostic == "direct_edge_sample_duplicate"
    assert _kinds(duplicate) == []
    older = bank.observe(_sample(sample_sequence=1, observed_mono_ms=500, lap_completed=4))
    assert older.accepted is False
    assert older.diagnostic == "direct_edge_sample_stale"
    assert _kinds(older) == []


def test_bank_stays_isolated_from_detector_bank_and_runtime() -> None:
    source = (ROOT / "src/irswitch/events/direct_edges.py").read_text(encoding="utf-8")
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
    imports = [
        line
        for line in source.splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "detector_bank" not in joined
    assert "irswitch.commentary" not in joined
    assert "overlay.tape" not in joined
    init = (ROOT / "src/irswitch/events/__init__.py").read_text(encoding="utf-8")
    assert "direct_edges" not in init
    assert "DirectEdgeBank" not in init
