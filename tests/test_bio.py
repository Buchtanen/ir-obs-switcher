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


def test_prepare_winrt_ble_noop_off_windows(monkeypatch) -> None:
    import irswitch.bio.provider as bio

    bio.reset_winrt_prepared()
    monkeypatch.setattr(bio.sys, "platform", "linux")
    bio.prepare_winrt_ble()
    assert getattr(bio._tls, "ready", False) is False


def test_prepare_winrt_ble_uninitialize_only_by_default(monkeypatch) -> None:
    import irswitch.bio.provider as bio

    seen: list[str] = []
    bio.reset_winrt_prepared()
    monkeypatch.setattr(bio.sys, "platform", "win32")
    monkeypatch.setattr(
        bio,
        "_winrt_sta_hooks",
        lambda: (lambda: seen.append("uninitialize"), lambda: seen.append("allow")),
    )
    bio.prepare_winrt_ble()
    assert seen == ["uninitialize"]
    bio.prepare_winrt_ble()
    assert seen == ["uninitialize"]


def test_prepare_winrt_ble_allow_sta_opt_in(monkeypatch) -> None:
    import irswitch.bio.provider as bio

    seen: list[str] = []
    bio.reset_winrt_prepared()
    monkeypatch.setattr(bio.sys, "platform", "win32")
    monkeypatch.setattr(
        bio,
        "_winrt_sta_hooks",
        lambda: (lambda: seen.append("uninitialize"), lambda: seen.append("allow")),
    )
    bio.prepare_winrt_ble(allow_sta_fallback=True)
    assert seen == ["uninitialize", "allow"]


def test_prepare_winrt_ble_marks_ready_when_hooks_missing(monkeypatch) -> None:
    import irswitch.bio.provider as bio

    bio.reset_winrt_prepared()
    monkeypatch.setattr(bio.sys, "platform", "win32")
    monkeypatch.setattr(bio, "_winrt_sta_hooks", lambda: None)
    bio.prepare_winrt_ble()
    assert getattr(bio._tls, "ready", False) is True


def test_prepare_winrt_ble_swallows_winrt_errors(monkeypatch) -> None:
    import irswitch.bio.provider as bio

    def _boom() -> None:
        raise RuntimeError("ole32")

    bio.reset_winrt_prepared()
    monkeypatch.setattr(bio.sys, "platform", "win32")
    monkeypatch.setattr(bio, "_winrt_sta_hooks", lambda: (_boom, _boom))
    bio.prepare_winrt_ble(allow_sta_fallback=True)
    assert getattr(bio._tls, "ready", False) is True


@pytest.mark.asyncio
async def test_connect_once_pairs_before_services_and_shows_name(monkeypatch) -> None:
    import sys
    import types

    import irswitch.bio.provider as bio

    device = _Dev("Think 0215360", "D5:19:FD:8F:D8:84", uuids=[bio.HR_SERVICE])
    constructed: list[dict[str, object]] = []
    seen: list[tuple[str, str | None]] = []

    class _Client:
        def __init__(
            self,
            _device: object,
            disconnected_callback: object = None,
            timeout: float = 30,
            pair: bool = False,
            services: object = None,
            winrt: dict[str, object] | None = None,
            **_kwargs: object,
        ) -> None:
            constructed.append(
                {
                    "pair": pair,
                    "timeout": timeout,
                    "services": list(services or ()),
                    "cached": bool((winrt or {}).get("use_cached_services")),
                }
            )
            self._on_disconnect = disconnected_callback

        async def connect(self) -> None:
            return None

        async def disconnect(self) -> None:
            return None

        async def start_notify(self, _char: object, _cb: object) -> None:
            if callable(self._on_disconnect):
                self._on_disconnect(self)

        async def stop_notify(self, _char: object) -> None:
            return None

    class _Scanner:
        @staticmethod
        async def discover(timeout: float = 8.0, return_adv: bool = True) -> list:
            return [device]

    fake = types.ModuleType("bleak")
    fake.BleakClient = _Client
    fake.BleakScanner = _Scanner
    monkeypatch.setitem(sys.modules, "bleak", fake)
    monkeypatch.setattr(bio, "prepare_winrt_ble", lambda **_kwargs: None)

    provider = BleHeartRateProvider(
        HeartRateSettings(),
        SamplingSettings(),
        on_state=lambda state: seen.append((state.status, state.device_name)),
    )
    await provider._connect_once()
    assert constructed[0] == {
        "pair": True,
        "timeout": bio._CONNECT_TIMEOUT_S,
        "services": [bio.HR_SERVICE],
        "cached": True,
    }
    assert ("connecting", "Think 0215360") in seen
    assert ("connected", "Think 0215360") in seen


@pytest.mark.asyncio
async def test_connect_or_timeout_abandons_hung_connect() -> None:
    import asyncio

    from irswitch.bio.provider import connect_or_timeout

    class _Client:
        def __init__(self) -> None:
            self.disconnected = False

        async def connect(self) -> None:
            await asyncio.sleep(60)

        async def disconnect(self) -> None:
            self.disconnected = True

    client = _Client()
    with pytest.raises(RuntimeError, match="BLE connect timeout"):
        await connect_or_timeout(client, 0.05)
    assert client.disconnected is True


@pytest.mark.asyncio
async def test_connect_once_times_out(monkeypatch) -> None:
    import sys
    import types

    import irswitch.bio.provider as bio

    device = _Dev("Think 0215360", "D5:19:FD:8F:D8:84", uuids=[bio.HR_SERVICE])

    class _Client:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def connect(self) -> None:
            await __import__("asyncio").sleep(60)

        async def disconnect(self) -> None:
            return None

    class _Scanner:
        @staticmethod
        async def discover(timeout: float = 8.0, return_adv: bool = True) -> list:
            return [device]

    fake = types.ModuleType("bleak")
    fake.BleakClient = _Client
    fake.BleakScanner = _Scanner
    monkeypatch.setitem(sys.modules, "bleak", fake)
    monkeypatch.setattr(bio, "prepare_winrt_ble", lambda **_kwargs: None)
    monkeypatch.setattr(bio, "_CONNECT_TIMEOUT_S", 0.05)

    provider = BleHeartRateProvider(HeartRateSettings(), SamplingSettings())
    with pytest.raises(RuntimeError, match="BLE connect timeout"):
        await provider._connect_once()


@pytest.mark.asyncio
async def test_connect_once_prepares_winrt_before_scan(monkeypatch) -> None:
    import sys
    import types

    import irswitch.bio.provider as bio

    seen: list[str] = []
    monkeypatch.setattr(bio, "prepare_winrt_ble", lambda **_kwargs: seen.append("prepare"))

    class _Scanner:
        @staticmethod
        async def discover(timeout: float = 8.0, return_adv: bool = True) -> dict:
            seen.append("scan")
            return {}

    fake = types.ModuleType("bleak")
    fake.BleakClient = object
    fake.BleakScanner = _Scanner
    monkeypatch.setitem(sys.modules, "bleak", fake)

    provider = BleHeartRateProvider(HeartRateSettings(), SamplingSettings())
    with pytest.raises(RuntimeError, match="no heart-rate device"):
        await provider._connect_once()
    assert seen == ["prepare", "scan"]
