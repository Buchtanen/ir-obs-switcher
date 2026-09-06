# Sampling (`src/irswitch/sampling/`)

**Účel:** časové smyčky overlay providerů. Nikdy neblokovat volajícího; tick se `await`.

`SamplingScheduler`: `get_hz()` každý cyklus, `clamp_hz` 0.2–30, `hz<=0` = event-driven / skip poll. Chyba v ticku = log + pokračovat. Cancel = konec.

`resolve_component_hz(default, override, push_when_unset=)` — BLE defaultně push (0 Hz) když override není.

## Kdo to používá

| Komponenta | Hz zdroj | Tick |
| --- | --- | --- |
| Race overlay | `sampling.race.hz` / default | `OverlayRuntime._tick_race` |
| System | `sampling.system.hz` | `_tick_system` |
| Bio | `sampling.bio.hz` (0 = BLE notify) | `_run_bio` |

Hot-reload: klíče v `LIVE_CONFIG_KEYS` (`config_reload.py`).

INI: [CONFIG.md](../../../CONFIG.md) sekce `[sampling]`. Testy: `tests/test_sampling.py`.
