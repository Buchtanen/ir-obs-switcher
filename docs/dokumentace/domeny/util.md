# Util (`src/irswitch/util/`)

Malé sdílené kusy. Žádná doménová logika.

| Soubor | Role |
| --- | --- |
| `clock.py` | `now_ms()` = `time.monotonic()` — **jediný čas pro cooldown/debounce** |
| `logging.py` | setup, connection/scene helper logy, runtime log level |
| `single_instance.py` | bind HTTP adresy před init; druhá instance → chyba |
| `process_restart.py` | detached respawn pro `POST /restart` |
| `task` není tady | `server/task_registry.py` |
| `hotkeys.py` | pynput listener pro RESTART (QUIT + hold) |
| `loading_tracker.py` | odhad loading času pro auto-start % |
| `notifications.py` | Windows toast on/off |

Testy: `tests/test_logging.py`, `tests/test_logging_level.py`, `tests/test_single_instance.py`, `tests/test_process_restart.py`, `tests/test_loading_tracker.py`.
