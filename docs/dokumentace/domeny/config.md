# Config

`config.py` parse INI → `AppConfig`. `config_reload.py` live vs restart keys.

## Autorita

[CONFIG.md](../../../CONFIG.md) + `config/config.example.ini`. Sem nekopíruj celé INI.

Shipped pointers: `[diagnostics] voice` → `util/diagnostic_voice.py`; `[race_scenarios] mode` → `events/scenarios/`; `[overlay] session_tape_llm` (default true); `[commentary.graph_runtime] mode=active`.
Na této větvi `active` publikuje `TRACK_EXCURSION` jen přes `ScenarioEngine`.

## Zrušené klíče

`dashboards.dashboard_vr_icons_path` — VR widget pryč. Zůstane-li v uživatelském INI, ignoruje se.

## Tests

`tests/test_config.py`, `tests/test_config_reload.py`.
