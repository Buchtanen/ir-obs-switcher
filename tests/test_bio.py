"""BLE HR parser and baseline."""

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
    provider = BleHeartRateProvider(
        HeartRateSettings(), SamplingSettings(), on_state=seen.append
    )
    state = provider.ingest_measurement(bytes([0x00, 140]), now=1.0)
    assert state.connected is True
    assert state.bpm == 140
    assert seen
    assert provider.sample_hz() == 0.0
