"""M4 sector commentary speak: flag, notability, per-lap cap, SECTOR_BEST."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector, slot_bindings
from irswitch.commentary.graph import parse_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.adapters.timing import timing_race_event_to_envelope
from irswitch.events.envelope import make_envelope
from irswitch.events.sector_split import (
    NOTABLE_GAIN_S,
    SectorBestEmitter,
    SectorBestTracker,
    SectorSplitEmitter,
)
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import RaceEvent
from irswitch.overlay.settings import CommentarySettings, EventPrioritySettings, EventSettings
from irswitch.race.timing.store import TimingRecord, TimingStore


def _sector_graph():
    return parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en", "cs"],
            "nodes": {
                "sector_split": {
                    "family": "timing",
                    "event_types": ["SECTOR_SPLIT", "SECTOR_BEST"],
                    "phases": ["RESULT"],
                    "speak_priority": 44,
                    "cooldown_s": 0.1,
                    "slots": [
                        {"name": "sector", "type": "label", "example": "S1"},
                        {"name": "segment_time", "type": "time", "example": "0:28.500"},
                    ],
                    "hr_states": ["unknown", "calm", "focused"],
                    "variants": {
                        "en": {
                            "neutral": ["That's {sector} in {segment_time}."],
                        }
                    },
                }
            },
            "edges": [],
        }
    )


def _sector_env(
    *,
    event_type: str = "SECTOR_SPLIT",
    notable: bool = False,
    is_best: bool = False,
    segment_time: float = 28.5,
    lap: int = 2,
    sector: str = "S1",
    delta: float | None = None,
):
    metrics: dict[str, object] = {
        "sector": sector,
        "timingPointId": sector,
        "segmentTime": segment_time,
        "lap": lap,
        "notable": notable,
        "isBest": is_best,
    }
    if delta is not None:
        metrics["delta"] = delta
    return make_envelope(
        event_type=event_type,
        phase="RESULT",
        priority=45,
        correlation_id=f"timing:{event_type}:{lap}:{sector}",
        metrics=metrics,
    )


def _clear_locks(director: CommentaryDirector) -> None:
    director._busy_until = 0.0
    director._global_ready_at = 0.0
    director._cooldowns.clear()


def test_sector_speak_flag_default_off_skips() -> None:
    director = CommentaryDirector(
        graph=_sector_graph(),
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    assert director.settings.sector_speak is False
    assert director.observe([_sector_env(notable=True, delta=-0.1)], None, 1.0) is None
    assert director.decisions()[-1]["reason"] == "sector_speak_disabled"


def test_sector_speak_skips_non_notable_split() -> None:
    director = CommentaryDirector(
        graph=_sector_graph(),
        settings=CommentarySettings(
            enabled=True,
            cooldown_s=0.0,
            use_hr_emotion=False,
            sector_speak=True,
        ),
        sink=NullTtsSink(),
    )
    assert director.observe([_sector_env(notable=False)], None, 1.0) is None
    assert director.decisions()[-1]["reason"] == "sector_not_notable"


def test_sector_speak_allows_notable_split_with_formatted_time() -> None:
    sink = NullTtsSink()
    director = CommentaryDirector(
        graph=_sector_graph(),
        settings=CommentarySettings(
            enabled=True,
            cooldown_s=0.0,
            use_hr_emotion=False,
            sector_speak=True,
            sector_speak_max_per_lap=2,
        ),
        sink=sink,
    )
    spoken = director.observe(
        [_sector_env(notable=True, delta=-0.12, segment_time=28.5)],
        None,
        1.0,
    )
    assert spoken is not None
    assert spoken.text == "That's S1 in 0:28.500."
    assert spoken.node_id == "sector_split"


def test_sector_best_always_notable_when_flag_on() -> None:
    director = CommentaryDirector(
        graph=_sector_graph(),
        settings=CommentarySettings(
            enabled=True,
            cooldown_s=0.0,
            use_hr_emotion=False,
            sector_speak=True,
        ),
        sink=NullTtsSink(),
    )
    spoken = director.observe(
        [_sector_env(event_type="SECTOR_BEST", notable=False, segment_time=27.1)],
        None,
        1.0,
    )
    assert spoken is not None
    assert "0:27.100" in spoken.text


def test_sector_speak_per_lap_cap() -> None:
    director = CommentaryDirector(
        graph=_sector_graph(),
        settings=CommentarySettings(
            enabled=True,
            cooldown_s=0.0,
            use_hr_emotion=False,
            sector_speak=True,
            sector_speak_max_per_lap=1,
        ),
        sink=NullTtsSink(),
    )
    assert (
        director.observe(
            [_sector_env(event_type="SECTOR_BEST", lap=4, sector="S1", segment_time=28.0)],
            None,
            1.0,
        )
        is not None
    )
    _clear_locks(director)
    assert (
        director.observe(
            [_sector_env(event_type="SECTOR_BEST", lap=4, sector="S2", segment_time=29.0)],
            None,
            2.0,
        )
        is None
    )
    assert director.decisions()[-1]["reason"] == "sector_lap_cap"


def test_slot_bindings_sector_label_and_segment_time() -> None:
    bindings = slot_bindings(_sector_env(segment_time=31.214), "unknown")
    assert bindings["sector"] == "S1"
    assert bindings["segment_time"] == "0:31.214"


def test_sector_best_emitter_fires_on_improvement_only() -> None:
    store = TimingStore()
    best = SectorBestEmitter(store, EventSettings(), EventPrioritySettings())
    state = RaceState(connected=True, overlay_mode="PRACTICE")

    store.append_record(
        TimingRecord(
            car_id="player",
            timing_point_id="S1",
            lap_number=1,
            crossing_timestamp=10.0,
            segment_time=32.0,
            valid_at_crossing=True,
        )
    )
    assert best.tick(state, 10.0) == []

    store.append_record(
        TimingRecord(
            car_id="player",
            timing_point_id="S1",
            lap_number=2,
            crossing_timestamp=42.0,
            segment_time=31.0,
            valid_at_crossing=True,
        )
    )
    out = best.tick(state, 42.0)
    assert [e.name for e in out] == ["sector_best"]
    assert out[0].data["sector"] == "S1"
    assert out[0].data["segmentTime"] == 31.0
    assert out[0].data["isBest"] is True
    assert out[0].data["delta"] == -1.0


def test_sector_split_annotates_notable_on_gain() -> None:
    store = TimingStore()
    tracker = SectorBestTracker()
    split = SectorSplitEmitter(store, EventSettings(), EventPrioritySettings(), tracker=tracker)
    state = RaceState(connected=True, overlay_mode="PRACTICE")

    store.append_record(
        TimingRecord(
            car_id="player",
            timing_point_id="S1",
            lap_number=1,
            crossing_timestamp=10.0,
            segment_time=32.0,
            valid_at_crossing=True,
        )
    )
    first = split.tick(state, 10.0)
    assert first[0].data["notable"] is False

    store.append_record(
        TimingRecord(
            car_id="player",
            timing_point_id="S1",
            lap_number=2,
            crossing_timestamp=42.0,
            segment_time=32.0 - NOTABLE_GAIN_S,
            valid_at_crossing=True,
        )
    )
    second = split.tick(state, 42.0)
    assert second[0].data["notable"] is True
    assert second[0].data["isBest"] is True


def test_timing_adapter_maps_sector_best() -> None:
    event = RaceEvent(
        name="sector_best",
        channel="timing",
        priority=60,
        phase="trigger",
        timestamp=1.0,
        data={"sector": "S2", "timingPointId": "S2", "segmentTime": 30.1, "lap": 3, "delta": -0.2},
        duration=4.0,
        cooldown=5.0,
    )
    env = timing_race_event_to_envelope(event, session_id="s", mode="PRACTICE", now=1.0)
    assert env is not None
    assert env.event_type == "SECTOR_BEST"
    assert env.metrics["segmentTime"] == 30.1
