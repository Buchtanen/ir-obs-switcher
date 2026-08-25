"""System history aggregation and null-safe merge."""

from irswitch.overlay.settings import SystemInfoSettings
from irswitch.system.history import MetricHistory
from irswitch.system.provider import collect_system_state


def test_metric_history_avg_and_max() -> None:
    hist = MetricHistory(keep_seconds=60)
    hist.add(0, 10)
    hist.add(5, 30)
    hist.add(9, 20)
    assert hist.average(10, 9) == 20
    assert hist.maximum(60, 9) == 30


def test_collect_without_optional_backends() -> None:
    state = collect_system_state(SystemInfoSettings(enabled=True))
    assert state.cpu is not None
    assert state.gpu is not None
    assert state.memory is not None
    # Missing backends leave nullable fields, never crash.
    _ = state.to_dict()
