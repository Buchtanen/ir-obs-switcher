# Server / HTTP (`src/irswitch/server/`)

**Účel:** aiohttp glue — REST, WebSocket switcheru, HTML dashboardy, admin. Drží process-wide reference na config/state/OBS/reader.

**Nepatří sem:** výpočet `DrivingMode`, tick Event Engine, TTS.

Handlery smí: číst stav, overlay override, reload config, shutdown. Nesmí obcházet `StateMachine` vlastním mapováním mód→scéna.

## Aplikace

`create_app` v `api.py` registruje switcher routes; overlay a commentary se napojí z `overlay/http.py` / `commentary/http.py`; admin z `admin.py`.

Default listen: `127.0.0.1:17321`. Kontrakt payloadů: [API.md](../../../API.md) — **neopisovat sem**.

## Switcher API (výběr)

| Metoda | Cesta | Poznámka |
| --- | --- | --- |
| GET | `/health` | Verze + liveness; viz VERSIONING.md |
| GET | `/status` | `SwitchState` + stream pole |
| GET | `/metrics` | Counters |
| POST | `/override` | Dočasná scéna |
| POST | `/autoswitch/toggle` | |
| POST | `/restart-mode/reset` | |
| POST | `/config/reload` | Live vs restart-required (`config_reload.py`) |
| POST | `/reset` `/shutdown` `/restart` | |
| GET/POST | `/logging/level` | |
| GET | `/api/events` | Event log |
| GET | `/ws` | Switcher WS (ne overlay) |
| GET | `/oauth/*` | YouTube |

## Dashboardy

| URL | Zdroj |
| --- | --- |
| `/admin` (+ extensions/features/activity) | `server/admin.py`, `web/admin/` |
| `/api/admin/status`, `/api/admin/activity` | admin health + activity feed |
| `/gr-status` | `dashboards.py` — ovládání switcheru |
| `/vr-status` | VR widget (RaceLab; bez auto-refresh) |
| `/test` | test widget |

Overlay URL jsou v [overlay](overlay.md), commentary v [commentary](commentary.md).

## Health

`admin_health.py` skládá ready/blocking/warnings (OBS, iRacing, overlay features, LHM, BLE). Admin UI to ukazuje; `/health` je tenčí.

## Tasky a log

- `TaskRegistry` — jediný způsob spawnovat background tasky v serveru i overlay runtime
- `event_log.py` — ring buffer pro GR dashboard
- `metrics.py` — inkrementy z main loop

Globální holdery (`set_obs_client`, …) resetuje `reset_state()` v testech.

## Testy

`tests/test_overlay_api.py` (částečně), admin/health testy, `tests/test_config_reload.py`, `tests/test_health_banner.py`, `tests/test_metrics.py`, `tests/test_task_registry.py`.

## In-flight

#181 N10 (public API watcher) je **odložené**. Do API nic z narrative epic zatím nepřidávej „pro jistotu“.
