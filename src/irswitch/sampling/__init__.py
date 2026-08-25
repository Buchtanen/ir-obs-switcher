"""Sampling frequency helpers: global default with per-component override."""

from irswitch.sampling.scheduler import SamplingScheduler, clamp_hz, resolve_component_hz

__all__ = ["SamplingScheduler", "clamp_hz", "resolve_component_hz"]
