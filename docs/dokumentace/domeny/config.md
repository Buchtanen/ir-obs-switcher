# Config

`config.py` parse INI → `AppConfig`. `config_reload.py` live vs restart keys.

## Autorita

[CONFIG.md](../../../CONFIG.md) + `config/config.example.ini`. Sem nekopíruj celé INI.

## Zrušené klíče

`dashboards.dashboard_vr_icons_path` — VR widget pryč. Zůstane-li v uživatelském INI, ignoruje se.

## Tests

`tests/test_config.py`, `tests/test_config_reload.py`.
