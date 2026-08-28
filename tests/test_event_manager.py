"""EventManager channels, priority, cooldown, inject."""

from irswitch.events.manager import EventManager
from irswitch.overlay.display import ActiveSlot, AssetManifest, can_place, place
from irswitch.overlay.protocol import CandidateEvent


def test_battle_channel_holds_both() -> None:
    mgr = EventManager()
    a = mgr.submit(
        CandidateEvent(
            name="battle", channel="battle", priority=20, phase="enter", data={"state": "hunting"}
        ),
        1.0,
    )
    b = mgr.submit(
        CandidateEvent(
            name="battle", channel="battle", priority=20, phase="enter", data={"state": "hunted"}
        ),
        1.0,
    )
    assert a is not None and b is not None
    assert len(mgr.active_events()) == 2


def test_lap_channel_higher_priority_replaces() -> None:
    mgr = EventManager()
    mgr.submit(
        CandidateEvent(
            name="lap_complete", channel="lap", priority=40, phase="trigger", duration=4
        ),
        1.0,
    )
    pb = mgr.submit(
        CandidateEvent(
            name="personal_best", channel="lap", priority=60, phase="trigger", duration=4
        ),
        1.1,
    )
    assert pb is not None
    names = {e["name"] for e in mgr.active_events()}
    assert names == {"personal_best"}


def test_cooldown_blocks_retrigger() -> None:
    mgr = EventManager()
    first = mgr.submit(
        CandidateEvent(
            name="incident", channel="alert", priority=90, phase="trigger", duration=2, cooldown=5
        ),
        1.0,
    )
    second = mgr.submit(
        CandidateEvent(
            name="incident", channel="alert", priority=90, phase="trigger", duration=2, cooldown=5
        ),
        2.0,
    )
    assert first is not None
    assert second is None


def test_tick_expires_and_inject() -> None:
    mgr = EventManager()
    mgr.submit(
        CandidateEvent(
            name="lap_complete", channel="lap", priority=40, phase="trigger", duration=1.0
        ),
        10.0,
    )
    expired = mgr.tick(11.1)
    assert expired and expired[0].phase == "exit"
    injected = mgr.inject("hunting", 12.0)
    assert injected is not None
    assert injected.data["state"] == "hunting"


def test_display_occupancy_and_missing_asset(tmp_path) -> None:
    active = [ActiveSlot("lap", "lap_complete", 40)]
    assert can_place(active, "lap", 60) is True
    assert can_place(active, "lap", 10) is False
    placed = place(active, ActiveSlot("lap", "personal_best", 60))
    assert any(s.name == "personal_best" for s in placed)
    both = place([], ActiveSlot("battle", "battle:hunting", 20))
    both = place(both, ActiveSlot("battle", "battle:hunted", 20))
    assert len([s for s in both if s.channel == "battle"]) == 2
    manifest = AssetManifest("cyber_racing", tmp_path)
    assert manifest.resolve("heart_icon") is None
    (tmp_path / "themes" / "cyber_racing" / "assets").mkdir(parents=True)
    (tmp_path / "themes" / "cyber_racing" / "assets" / "heart_icon.svg").write_text("<svg/>")
    assert manifest.resolve("heart_icon") == "themes/cyber_racing/assets/heart_icon.svg"
