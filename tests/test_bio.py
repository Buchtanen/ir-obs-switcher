"""BLE HR parser and baseline."""

import pytest

from irswitch.bio.history import HeartRateHistory
from irswitch.bio.parser import classify_hr_state, parse_heart_rate_measurement
from irswitch.bio.provider import BleHeartRateProvider
from irswitch.overlay.settings import HeartRateSettings, SamplingSettings


def test_parse_uint8_bpm_and_rr() -> None:
    # flags: RR present (0x10), UINT8 bpm
    payload = bytes([0x10, 143, 0x00, 0x04, 0x00, 0x04])
    bpm, rr = parse_heart_rate_measurement(payload)
    assert bpm == 143
    assert rr == (1024, 1024)


def test_parse_uint16_bpm() -> None:
    payload = bytes([0x01, 0x2C, 0x01])  # 300
    bpm, rr = parse_heart_rate_measurement(payload)
    assert bpm == 300
    assert rr == ()


def test_classify_and_baseline() -> None:
    assert classify_hr_state(3, calm=5, focused=15, pushing=25) == "calm"
    assert classify_hr_state(20, calm=5, focused=15, pushing=25) == "pushing"
    assert classify_hr_state(40, calm=5, focused=15, pushing=25) == "high"
    hist = HeartRateHistory(window_seconds=10)
    hist.add(0, 100)
    hist.add(5, 120)
    assert hist.baseline() == 110


def test_provider_ingest_updates_state() -> None:
    seen = []
    provider = BleHeartRateProvider(HeartRateSettings(), SamplingSettings(), on_state=seen.append)
    state = provider.ingest_measurement(bytes([0x00, 140]), now=1.0)
    assert state.connected is True
    assert state.bpm == 140
    assert seen
    assert provider.sample_hz() == 0.0


class _Dev:
    def __init__(self, name: str | None, address: str, uuids: list[str] | None = None) -> None:
        self.name = name
        self.address = address
        self.metadata = {"uuids": uuids or []}


class _Adv:
    def __init__(self, uuids: list[str], local_name: str | None = None) -> None:
        self.service_uuids = uuids
        self.local_name = local_name


def test_auto_picks_advertised_hr_uuid_not_metadata() -> None:
    from irswitch.bio.provider import HR_SERVICE, pick_heart_rate_device

    headphones = _Dev("LE_WH-1000XM4", "AA:AA")
    think = _Dev("Think 0215360", "BB:BB")
    rows = [
        (headphones, _Adv(["0000fe03-0000-1000-8000-00805f9b34fb"])),
        (think, _Adv([HR_SERVICE])),
    ]
    picked = pick_heart_rate_device(rows, "auto")
    assert picked is think


def test_auto_ignores_name_without_hr_uuid() -> None:
    from irswitch.bio.provider import pick_heart_rate_device

    cammus = _Dev("CAMMUS C12", "CC:CC")
    rows = [(cammus, _Adv([]))]
    assert pick_heart_rate_device(rows, "auto") is None


def test_wanted_name_substring_wins() -> None:
    from irswitch.bio.provider import HR_SERVICE, pick_heart_rate_device

    think = _Dev("Think 0215360", "BB:BB")
    other = _Dev("Polar H10", "DD:DD")
    rows = [
        (other, _Adv([HR_SERVICE])),
        (think, _Adv([HR_SERVICE])),
    ]
    assert pick_heart_rate_device(rows, "think") is think


@pytest.mark.asyncio
async def test_pair_if_supported_swallows_errors() -> None:
    from irswitch.bio.provider import pair_if_supported

    class _Client:
        async def pair(self) -> None:
            raise RuntimeError("already bonded")

    await pair_if_supported(_Client())
