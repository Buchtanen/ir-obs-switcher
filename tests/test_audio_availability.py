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


def test_native_bootstrap_imports_only_onnx_on_windows(monkeypatch):
    from irswitch.commentary import supertonic_backend as backend

    imported = []
    monkeypatch.setattr(backend.sys, "platform", "win32")
    monkeypatch.setattr(backend, "available", lambda: True)
    monkeypatch.setattr(backend.importlib, "import_module", imported.append)
    backend.prepare_native_runtime()
    assert imported == ["onnxruntime"]


def test_failed_native_bootstrap_disables_only_supertonic(monkeypatch):
    from irswitch.commentary import supertonic_backend as backend

    monkeypatch.setattr(backend, "_native_runtime_error", None)
    monkeypatch.setattr(backend.sys, "platform", "win32")
    monkeypatch.setattr(backend.importlib.util, "find_spec", lambda name: object())

    def fail(name):
        raise ImportError("broken runtime")

    monkeypatch.setattr(backend.importlib, "import_module", fail)
    backend.prepare_native_runtime()
    assert backend.available() is False
