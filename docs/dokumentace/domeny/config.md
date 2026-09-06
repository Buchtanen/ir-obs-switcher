# Config

**Autorita klíčů a defaultů:** [CONFIG.md](../../../CONFIG.md) + [`config/config.example.ini`](../../../config/config.example.ini). Sem jen **jak se to načte a reloaduje**.

## Load

`config.py`: INI → frozen `AppConfig` (app, iracing, obs, switching, scenes, dashboards, overlay settings, OAuth, stream chapters, …). Validace (port 1–65535, povinné scény). Chybějící volitelné sekce → defaulty.

Overlay vnořené dataclassy žijí v `overlay/settings.py`, do INI je mapuje `config.py`.

## Hot-reload

`POST /config/reload` → `config_reload.py`:

- `LIVE_CONFIG_KEYS` — platí bez restartu (switching debounce, sampling Hz, overlay theme, spousta event_engine flagů, …)
- Zbytek v odpovědi jako restart-required
- Canonical seznam **musí** sedět s CONFIG.md § Hot-reload

`StateMachine.apply_runtime_config` a overlay settings se berou z nového `AppConfig` v main loop / runtime tick (`get_app_config()`).

## Pravidlo změny klíče

Nový/přejmenovaný klíč = CONFIG.md + example.ini + AC + test (`tests/test_config.py`, `tests/test_config_reload.py`) + migrace. Viz `.cursor/rules/config-contract.mdc`.

## In-flight klíče (nejsou na master)

#179: `[commentary.scheduler]` (defer, hard_interrupt, TTL, silence fill) — default **off**.

#181:

- `commentary.stream_start` default false
- `commentary.gap_hunt_tts_in_practice` / `gap_hunt_tts_in_qualifying` default false
- `[race_observer] leader_pace_cooldown_s` default 300
- `race_observer.incident_classify` default false
- `race_observer.flags` default false

Nepiš je do CONFIG.md na master, dokud PR nemergne (PR větve už CONFIG.md mění).
