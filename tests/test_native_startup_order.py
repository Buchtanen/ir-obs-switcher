"""Native TTS bootstrap must precede BLE and other race workers."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from irswitch.race.runtime import RaceRuntime


@pytest.mark.asyncio
async def test_race_workers_wait_for_native_tts_bootstrap(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()
    spawn_calls: list[str] = []

    def prepare() -> None:
        started.set()
        assert release.wait(timeout=3)

    class FirstSpawn(Exception):
        pass

    def spawn(name: str, _worker: object) -> None:
        spawn_calls.append(name)
        raise FirstSpawn

    monkeypatch.setattr("irswitch.commentary.supertonic_backend.prepare_native_runtime", prepare)
    runtime = RaceRuntime.__new__(RaceRuntime)
    runtime.mode = "mock"
    runtime._overlay_settings = lambda: SimpleNamespace(enabled=True)
    runtime._registry = SimpleNamespace(spawn=spawn)
    runtime._overlay_supervisor = SimpleNamespace(run=lambda: None)

    task = asyncio.create_task(runtime.run())
    try:
        assert await asyncio.to_thread(started.wait, 3)
        assert spawn_calls == []
        assert not task.done()
        release.set()
        with pytest.raises(FirstSpawn):
            await task
        assert spawn_calls == ["overlay_consumer"]
    finally:
        release.set()
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
