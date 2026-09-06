# Runtime (`main.py`)

Vstup služby. CLI, single-instance bind, `run_service`, `main_loop` (scene switcher). Overlay/commentary startuje přes `race/runtime.py` + `TaskRegistry`, ne uvnitř ticku state machine.

## Boundaries

- Loop nesmí spadnout na iRacing/OBS/OAuth chybě.
- Žádný blocking call v async ticku.
- Druhá instance: exit 2 (`util/single_instance.py`).

## Key files

`main.py`, `models.py`, `server/task_registry.py`.

## Tests

`tests/test_main_*.py`, `tests/test_single_instance.py` (názvy podle prefixu `test_*main*` / process).

## Related

[architektura](../architektura.md), [logic](logic.md), [server](server.md).
