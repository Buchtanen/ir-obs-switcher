"""Availability checks must not initialize PortAudio/Windows COM on the loop thread."""

import builtins
import importlib.util

import pytest

from irswitch.commentary.supertonic_backend import available


@pytest.mark.parametrize("missing", [None, "sounddevice", "supertonic"])
def test_availability_probes_without_importing_native_libraries(monkeypatch, missing):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"sounddevice", "supertonic"}:
            raise AssertionError("Native audio import on caller thread")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name: None if name == missing else object()
    )
    assert available() is (missing is None)
