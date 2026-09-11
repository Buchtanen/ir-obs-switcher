"""#284 NarrativeRuntime Qwen enable + warmup preflight."""

from __future__ import annotations

from pathlib import Path

from irswitch.events import __all__ as events_exports
from irswitch.events.narrative_realization_bridge import warmup_qwen_component
from irswitch.events.qwen_transport import FakeTransport, LlmComponent

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "narrative_realization_bridge.py"
)
RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"


def test_warmup_helper_not_exported() -> None:
    assert "warmup_qwen_component" not in events_exports
    assert "warmup_qwen_component" in SOURCE.read_text(encoding="utf-8")


def test_warmup_qwen_component_marks_ready_on_fake_transport() -> None:
    component = LlmComponent()
    transport = FakeTransport()
    assert component.qwen_ready is False
    assert warmup_qwen_component(component, transport, generation=3) is True
    assert component.qwen_ready is True
    assert component.residency == "warmup_succeeded"
    assert component.applied_generation == 3


def test_warmup_qwen_component_fails_closed_on_transport_error() -> None:
    component = LlmComponent()
    transport = FakeTransport(fail=True)
    assert warmup_qwen_component(component, transport, generation=2) is False
    assert component.qwen_ready is False
    assert component.status == "failed"
    assert component.residency == "warmup_failed"


def test_race_enables_qwen_and_calls_warmup() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "self._narrative_qwen_enabled = commentary_enabled" in race
    assert "warmup_qwen_component" in race
    assert "StdlibTransport" in race
    # Soft-fail path must remain so missing Ollama does not crash startup.
    assert "warmup_qwen_component(" in race
