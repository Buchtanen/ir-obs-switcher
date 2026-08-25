"""System info provider. Optional extras; blocking I/O stays in a worker thread."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable

from irswitch.overlay.models import (
    CPUState,
    GPUState,
    MemoryState,
    PerformanceState,
    SystemHistory,
    SystemState,
)
from irswitch.overlay.settings import SamplingSettings, SystemInfoSettings
from irswitch.sampling.scheduler import resolve_component_hz
from irswitch.system.cpu_sensors import read_cpu_package_sensors
from irswitch.system.history import MetricHistory

logger = logging.getLogger(__name__)

_NVML_UNAVAILABLE_LOGGED = False
_PSUTIL_UNAVAILABLE_LOGGED = False


def _read_psutil() -> tuple[CPUState, MemoryState]:
    global _PSUTIL_UNAVAILABLE_LOGGED
    cpu = CPUState()
    memory = MemoryState()
    try:
        import psutil
    except ImportError:
        if not _PSUTIL_UNAVAILABLE_LOGGED:
            logger.warning(
                "System info: psutil not installed for %s; CPU/RAM empty. "
                'Install with that interpreter: "%s" -m pip install -e .',
                sys.executable,
                sys.executable,
            )
            _PSUTIL_UNAVAILABLE_LOGGED = True
        return cpu, memory
    try:
        load = psutil.cpu_percent(interval=None)
        per_core = tuple(float(x) for x in psutil.cpu_percent(interval=None, percpu=True))
        freq = None
        freq_info = psutil.cpu_freq()
        if freq_info is not None:
            freq = float(freq_info.current) / 1000.0  # MHz → GHz
        cpu = CPUState(load=float(load), frequency=freq, per_core_load=per_core)
        vm = psutil.virtual_memory()
        memory = MemoryState(
            used=float(vm.used) / (1024**3),
            total=float(vm.total) / (1024**3),
            percent=float(vm.percent),
        )
    except Exception:
        logger.debug("psutil sample failed", exc_info=True)
    return cpu, memory


def _read_nvml() -> GPUState:
    global _NVML_UNAVAILABLE_LOGGED
    try:
        import pynvml
    except ImportError:
        if not _NVML_UNAVAILABLE_LOGGED:
            logger.info("System info: nvidia-ml-py/pynvml not installed; GPU skipped")
            _NVML_UNAVAILABLE_LOGGED = True
        return GPUState()
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        try:
            power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
        except Exception:
            power = None
        try:
            power_limit = pynvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000.0
        except Exception:
            power_limit = None
        try:
            clock = float(pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS))
        except Exception:
            clock = None
        try:
            mem_clock = float(pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM))
        except Exception:
            mem_clock = None
        try:
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            vram_used = float(mem.used) / (1024**3)
            vram_total = float(mem.total) / (1024**3)
        except Exception:
            vram_used = None
            vram_total = None
        throttle = None
        try:
            reasons = pynvml.nvmlDeviceGetCurrentClocksThrottleReasons(handle)
            if reasons:
                throttle = str(reasons)
        except Exception:
            throttle = None
        return GPUState(
            load=float(util.gpu),
            temperature=float(temp),
            power=power,
            power_limit=power_limit,
            clock=clock,
            memory_clock=mem_clock,
            vram_used=vram_used,
            vram_total=vram_total,
            throttle_reason=throttle,
        )
    except Exception:
        logger.debug("NVML sample failed", exc_info=True)
        return GPUState()


def collect_system_state(
    settings: SystemInfoSettings,
    *,
    fps: float | None = None,
    frametime_ms: float | None = None,
    cpu_hist: MetricHistory | None = None,
    cpu_temp_hist: MetricHistory | None = None,
    gpu_hist: MetricHistory | None = None,
    gpu_temp_hist: MetricHistory | None = None,
    now: float | None = None,
) -> SystemState:
    now = time.monotonic() if now is None else now
    cpu = CPUState()
    memory = MemoryState()
    gpu = GPUState()
    if settings.enabled:
        if settings.cpu_enabled or settings.memory_enabled:
            cpu_s, mem_s = _read_psutil()
            if settings.cpu_enabled:
                cpu = cpu_s
            if settings.memory_enabled:
                memory = mem_s
        if settings.gpu_enabled:
            gpu = _read_nvml()
        package = read_cpu_package_sensors(settings.lhm_dll_path)
        if package.get("temperature") is not None or package.get("power") is not None:
            cpu = CPUState(
                load=cpu.load,
                temperature=(
                    package["temperature"]
                    if package.get("temperature") is not None
                    else cpu.temperature
                ),
                power=package["power"] if package.get("power") is not None else cpu.power,
                frequency=cpu.frequency,
                per_core_load=cpu.per_core_load,
            )
    if cpu_hist is not None:
        cpu_hist.add(now, cpu.load)
    if cpu_temp_hist is not None:
        cpu_temp_hist.add(now, cpu.temperature)
    if gpu_hist is not None:
        gpu_hist.add(now, gpu.load)
    if gpu_temp_hist is not None:
        gpu_temp_hist.add(now, gpu.temperature)
    history = SystemHistory(
        gpu_load_avg_10s=gpu_hist.average(10, now) if gpu_hist else None,
        gpu_temp_max_60s=gpu_temp_hist.maximum(60, now) if gpu_temp_hist else None,
        cpu_load_avg_10s=cpu_hist.average(10, now) if cpu_hist else None,
        cpu_temp_max_60s=cpu_temp_hist.maximum(60, now) if cpu_temp_hist else None,
    )
    return SystemState(
        cpu=cpu,
        gpu=gpu,
        memory=memory,
        performance=PerformanceState(fps=fps, frametime=frametime_ms),
        history=history,
    )


class SystemInfoProvider:
    def __init__(
        self,
        settings: SystemInfoSettings,
        sampling: SamplingSettings,
        on_state: Callable[[SystemState], None] | None = None,
    ) -> None:
        self._settings = settings
        self._sampling = sampling
        self._on_state = on_state
        self._cpu_hist = MetricHistory()
        self._cpu_temp_hist = MetricHistory()
        self._gpu_hist = MetricHistory()
        self._gpu_temp_hist = MetricHistory()
        self._state = SystemState()

    @property
    def name(self) -> str:
        return "system"

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    def sample_hz(self) -> float:
        return resolve_component_hz(self._sampling.default_hz, self._sampling.system_hz)

    def current(self) -> SystemState:
        return self._state

    def apply_settings(self, settings: SystemInfoSettings, sampling: SamplingSettings) -> None:
        self._settings = settings
        self._sampling = sampling

    def sample(self, *, fps: float | None = None, frametime_ms: float | None = None) -> SystemState:
        self._state = collect_system_state(
            self._settings,
            fps=fps,
            frametime_ms=frametime_ms,
            cpu_hist=self._cpu_hist,
            cpu_temp_hist=self._cpu_temp_hist,
            gpu_hist=self._gpu_hist,
            gpu_temp_hist=self._gpu_temp_hist,
        )
        if self._on_state:
            self._on_state(self._state)
        return self._state
