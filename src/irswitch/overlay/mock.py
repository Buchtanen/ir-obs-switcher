"""Synthetic overlay feed for --mock (no iRacing required)."""

from __future__ import annotations

import math
import time

from irswitch.overlay.models import (
    BioState,
    CPUState,
    GPUState,
    MemoryState,
    OpponentInfo,
    PerformanceState,
    RaceState,
    SystemState,
)


def mock_race_state(elapsed: float) -> RaceState:
    """Gap ahead shrinks 5.0 → 1.4 over ~8s so hunting can fire."""
    gap = max(1.4, 5.0 - elapsed * 0.45)
    closing = 0.45 if gap > 1.4 else 0.05
    return RaceState(
        connected=True,
        player_car_idx=4,
        position=7,
        class_position=5,
        lap=12,
        lap_completed=11,
        current_lap_time=40.0 + elapsed,
        last_lap_time=94.372,
        best_lap_time=94.690,
        incidents=2,
        on_pit_road=False,
        is_final_lap=False,
        session_finished=False,
        opponent_ahead=OpponentInfo(
            car_idx=17,
            position=6,
            class_position=4,
            gap=gap,
            closing_rate=closing,
            display_name="Rossi",
        ),
        opponent_behind=OpponentInfo(
            car_idx=23,
            position=8,
            class_position=6,
            gap=2.14,
            closing_rate=-0.05,
            display_name="Kovalainen",
        ),
        gap_ahead=gap,
        gap_behind=2.14,
        closing_rate_ahead=closing,
        closing_rate_behind=-0.05,
        fps=90.0,
        frametime_ms=11.1,
        session_time=elapsed,
        session_state=4,
        overlay_mode="RACE",
        subsession_id="mock",
        session_num=0,
    )


def mock_bio_state(elapsed: float) -> BioState:
    bpm = int(118 + 25 * (0.5 + 0.5 * math.sin(elapsed / 8.0)))
    baseline = 118.0
    delta = bpm - baseline
    state = (
        "high" if delta >= 25 else "pushing" if delta >= 15 else "focused" if delta >= 5 else "calm"
    )
    return BioState(
        connected=True,
        status="connected",
        device_name="mock-hr",
        bpm=bpm,
        baseline_bpm=baseline,
        delta_bpm=delta,
        state=state,
        rr_intervals=(),
    )


def mock_system_state(elapsed: float) -> SystemState:
    load = 40.0 + 10.0 * math.sin(elapsed / 5.0)
    return SystemState(
        cpu=CPUState(load=load, temperature=62.0, power=90.0, frequency=5.1),
        gpu=GPUState(
            load=70.0,
            temperature=64.0,
            power=250.0,
            clock=2100.0,
            vram_used=10.0,
            vram_total=24.0,
        ),
        memory=MemoryState(used=18.0, total=32.0, percent=56.0),
        performance=PerformanceState(fps=90.0, frametime=11.1),
    )


def mock_now_origin() -> float:
    return time.monotonic()
