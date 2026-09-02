"""Optional SuperTonic 3 CPU TTS. Lazy import; never pull ONNX into the race loop."""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Protocol

logger = logging.getLogger(__name__)

CancelProbe = Callable[[], bool]
BUILTIN_VOICES = tuple(f"{gender}{idx}" for gender in ("M", "F") for idx in range(1, 6))
_INTRA_THREADS = 4
_INTER_THREADS = 2
_COINIT_APARTMENTTHREADED = 0x2
_engine_lock = threading.Lock()
_engine: Any = None


class PlaybackInterrupted(Exception):
    """Playback stopped because the sink interrupt generation advanced."""


class _Stream(Protocol):
    active: bool


def available() -> bool:
    try:
        import sounddevice  # type: ignore[import-not-found,unused-ignore]  # noqa: F401
        import supertonic  # type: ignore[import-not-found,unused-ignore]  # noqa: F401
    except ImportError:
        return False
    return True


def list_voices() -> list[str]:
    engine = _engine
    if engine is not None:
        names = [str(name) for name in getattr(engine, "voice_style_names", []) if str(name)]
        if names:
            return names
    return list(BUILTIN_VOICES)


def resolve_voice(name: str) -> str:
    raw = (name or "").strip()
    if raw.upper() in BUILTIN_VOICES:
        return raw.upper()
    return "M1"


def rate_to_speed(rate: int) -> float:
    """Map SAPI-style rate (-10…10) onto SuperTonic speed (0.7…2.0). Rate 0 → 1.05."""
    speed = 1.05 + max(-10, min(10, int(rate))) * 0.035
    return max(0.7, min(2.0, speed))


def clamp_steps(steps: int, default: int = 6) -> int:
    try:
        value = int(steps)
    except (TypeError, ValueError):
        value = default
    return max(5, min(12, value))


def _hostapi_rank(name: str) -> int | None:
    api = (name or "").lower()
    if "wdm-ks" in api or "wdmks" in api:
        return None
    if "wasapi" in api:
        return 0
    if "directsound" in api:
        return 1
    if api == "mme":
        return 2
    return 3


def rank_output_devices(devices: list[dict[str, Any]], want: str) -> list[int]:
    """WASAPI stereo 44.1 kHz first; never WDM-KS (PortAudio -9999 on worker threads)."""
    needle = (want or "").strip().lower()
    if not needle:
        return []
    ranked: list[tuple[int, int, int, int]] = []
    for idx, dev in enumerate(devices):
        name = str(dev.get("name") or "")
        low = name.lower()
        if needle not in low:
            continue
        outs = int(dev.get("max_output_channels") or 0)
        if outs < 1:
            continue
        if "16ch" in low.replace(" ", ""):
            continue
        api_rank = _hostapi_rank(str(dev.get("hostapi_name") or ""))
        if api_rank is None:
            continue
        stereo = 0 if outs == 2 else 1
        sr = float(dev.get("default_samplerate") or 0.0)
        native = 0 if abs(sr - 44100.0) < 1.0 else 1
        ranked.append((api_rank, stereo, native, idx))
    ranked.sort()
    return [item[3] for item in ranked]


def pick_output_device(devices: list[dict[str, Any]], want: str) -> int | None:
    """Prefer WASAPI stereo match; skip 16ch and WDM-KS. Empty want → default device."""
    ranked = rank_output_devices(devices, want)
    return ranked[0] if ranked else None


def _hostapi_name(hostapis: list[Any], hostapi_index: int) -> str:
    try:
        return str(hostapis[int(hostapi_index)]["name"])
    except Exception:
        return ""


def _query_output_devices() -> list[dict[str, Any]]:
    import sounddevice as sd  # type: ignore[import-not-found,unused-ignore]

    hostapis = list(sd.query_hostapis())
    devices: list[dict[str, Any]] = []
    for raw in sd.query_devices():
        item = dict(raw)
        item["hostapi_name"] = _hostapi_name(hostapis, int(item.get("hostapi") or 0))
        devices.append(item)
    return devices


@contextmanager
def _windows_com() -> Iterator[None]:
    """WASAPI/WDM-KS need COM on this thread; aiohttp executors do not initialize it."""
    if sys.platform != "win32":
        yield
        return
    import ctypes

    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole32.CoInitializeEx.restype = ctypes.c_long
    hr = int(ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)) & 0xFFFFFFFF
    owned = hr == 0
    try:
        yield
    finally:
        if owned:
            ole32.CoUninitialize()


def _play_pcm(
    sd: Any, audio: Any, samplerate: int, device_idx: int | None, hostapi_name: str
) -> None:
    kwargs: dict[str, Any] = {"samplerate": samplerate, "device": device_idx}
    if "wasapi" in (hostapi_name or "").lower():
        try:
            kwargs["extra_settings"] = sd.WasapiSettings(exclusive=False, auto_convert=True)
        except TypeError:
            kwargs["extra_settings"] = sd.WasapiSettings(exclusive=False)
        except Exception:
            logger.debug("tts supertonic WasapiSettings unavailable", exc_info=True)
    sd.play(audio, **kwargs)


def _get_engine() -> Any:
    global _engine
    with _engine_lock:
        if _engine is None:
            from supertonic import TTS  # type: ignore[import-not-found,unused-ignore]

            logger.info(
                "tts supertonic loading CPU engine intra=%s inter=%s",
                _INTRA_THREADS,
                _INTER_THREADS,
            )
            _engine = TTS(
                auto_download=True,
                intra_op_num_threads=_INTRA_THREADS,
                inter_op_num_threads=_INTER_THREADS,
            )
            logger.info(
                "tts supertonic ready sr=%s voices=%s",
                getattr(_engine, "sample_rate", None),
                list_voices(),
            )
        return _engine


def reset_engine() -> None:
    """Test helper. Does not unload ONNX from the process."""
    global _engine
    with _engine_lock:
        _engine = None


def speak(
    text: str,
    *,
    voice: str,
    rate: int,
    device: str,
    timeout_s: float,
    steps: int = 6,
    locale: str = "en",
    cancelled: CancelProbe | None = None,
    before_play: Callable[[], None] | None = None,
) -> None:
    """Blocking synth + play. Raises PlaybackInterrupted on hard interrupt."""
    if cancelled is not None and cancelled():
        raise PlaybackInterrupted
    engine = _get_engine()
    if cancelled is not None and cancelled():
        raise PlaybackInterrupted
    style = engine.get_voice_style(resolve_voice(voice))
    lang = "cs" if (locale or "en").lower().startswith("cs") else "en"
    deadline = time.monotonic() + max(1.0, float(timeout_s))
    wav, _duration = engine.synthesize(
        text,
        voice_style=style,
        lang=lang,
        total_steps=clamp_steps(steps),
        speed=rate_to_speed(rate),
    )
    if cancelled is not None and cancelled():
        raise PlaybackInterrupted
    if time.monotonic() >= deadline:
        raise TimeoutError("supertonic timeout after synthesize")
    if before_play is not None:
        before_play()
    if cancelled is not None and cancelled():
        raise PlaybackInterrupted
    import numpy as np  # type: ignore[import-not-found,unused-ignore]
    import sounddevice as sd  # type: ignore[import-not-found,unused-ignore]

    audio = np.asarray(wav).squeeze().astype(np.float32)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1).astype(np.float32)
    src_sr = int(getattr(engine, "sample_rate", 44100) or 44100)
    last_error: Exception | None = None
    with _windows_com():
        devices = _query_output_devices()
        candidates: list[int | None] = list(rank_output_devices(devices, device))
        if not candidates:
            if not (device or "").strip():
                candidates = [None]
            else:
                raise RuntimeError(f"supertonic no output device matching {device!r}")
        started = False
        for device_idx in candidates:
            hostapi_name = ""
            label = "default"
            if device_idx is not None:
                hostapi_name = str(devices[device_idx].get("hostapi_name") or "")
                label = str(devices[device_idx].get("name") or device_idx)
            try:
                logger.info(
                    "tts supertonic play device=%s api=%s sr=%s",
                    label,
                    hostapi_name or "default",
                    src_sr,
                )
                _play_pcm(sd, audio, src_sr, device_idx, hostapi_name)
                started = True
                break
            except Exception as exc:
                last_error = exc
                logger.warning("tts supertonic play failed device=%s: %s", label, exc)
                try:
                    sd.stop()
                except Exception:
                    pass
        if not started:
            if last_error is not None:
                raise last_error
            raise RuntimeError("supertonic playback did not start")
        try:
            while True:
                if cancelled is not None and cancelled():
                    raise PlaybackInterrupted
                if time.monotonic() >= deadline:
                    raise TimeoutError("supertonic playback timeout")
                stream: _Stream | None
                try:
                    stream = sd.get_stream()
                except Exception:
                    stream = None
                if stream is None or not stream.active:
                    break
                time.sleep(0.02)
            sd.wait()
        finally:
            sd.stop()
