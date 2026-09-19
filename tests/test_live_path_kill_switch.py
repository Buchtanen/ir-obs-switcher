"""#349 Slice 1 — commentary.enabled is the live-path kill-switch.

GPT Sol tip audit: RaceRuntime hard-enabled narrative shadow/Qwen and the
shadow adapter forced narrativeRunActive=True even when commentary was off.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from test_n12_consumers import _batch

from irswitch.events.narrative_shadow_adapter import adapt_batch_for_shadow
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.settings import OverlaySettings
from irswitch.race.runtime import RaceRuntime

RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"


def _runtime_with_commentary(*, enabled: bool) -> RaceRuntime:
    settings = OverlaySettings()
    settings = replace(settings, commentary=replace(settings.commentary, enabled=enabled))
    return RaceRuntime(lambda: SimpleNamespace(overlay=settings), None, OverlayBus())


def test_disabled_commentary_does_not_start_shadow_or_qwen_paths() -> None:
    runtime = _runtime_with_commentary(enabled=False)
    assert runtime._narrative_shadow_enabled is False
    assert runtime._narrative_qwen_enabled is False
    assert runtime.narrative_runtime is None
    assert runtime.narrative_shadow_consumer is None
    assert runtime._narrative_shadow_subscription is None


def test_enabled_commentary_starts_shadow_cutover() -> None:
    runtime = _runtime_with_commentary(enabled=True)
    assert runtime._narrative_shadow_enabled is True
    assert runtime.narrative_runtime is not None
    assert runtime.narrative_shadow_consumer is not None


def test_shadow_adapter_narrative_run_active_follows_kill_switch() -> None:
    batch = _batch(stream_sequence=7)
    inactive = adapt_batch_for_shadow(batch, narrative_run_active=False)
    assert inactive is not None
    assert inactive.timeline["narrativeRunActive"] is False

    active = adapt_batch_for_shadow(batch, narrative_run_active=True)
    assert active is not None
    assert active.timeline["narrativeRunActive"] is True


def test_race_runtime_gates_shadow_hard_enable_on_commentary_enabled() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "self._narrative_shadow_enabled = True" not in race
    assert "self._narrative_qwen_enabled = True" not in race
    assert "commentary.enabled" in race
    assert "_narrative_shadow_enabled" in race
