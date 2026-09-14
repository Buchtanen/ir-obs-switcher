# Config

`config.py` parse INI → `AppConfig`. `config_reload.py` live vs restart keys.

## Autorita

[CONFIG.md](../../../CONFIG.md) + `config/config.example.ini`. Sem nekopíruj celé INI.

Shipped pointers: `[diagnostics] voice` → `util/diagnostic_voice.py`; `[race_scenarios] mode` → `events/scenarios/`; `[overlay] session_tape_llm` (default true); `[commentary.graph_runtime] mode=active`.
Na `master` `active` publikuje `TRACK_EXCURSION` jen přes `ScenarioEngine`.

T13–T16 defaults (missing INI key = these): `commentary.polish_skeleton_fallback=true`; `commentary.llm_timeout_s=4.0`; `[commentary.scheduler] dynamic_ttl_s=4.0`; `[overlay] battle_card_lease_s=4.0`. Explicit `llm_timeout_s=12` in a local INI keeps the old budget.

## Zrušené klíče

`dashboards.dashboard_vr_icons_path` — VR widget pryč. Zůstane-li v uživatelském INI, ignoruje se.

## Tests

`tests/test_config.py`, `tests/test_config_reload.py`.
