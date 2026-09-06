# Server / HTTP (`src/irswitch/server/`)

Glue: REST, WS `/ws`, dashboards. Handlery čtou stav a spouští override/reload — mód z telemetrie počítá jen `StateMachine`.

## Surfaces

| URL | Role |
| --- | --- |
| `/gr-status` | Operator switcher dashboard |
| `/admin`, `/api/admin/*` | Extensions / health / activity |
| `/health` | Liveness + verze |
| `/status` | JSON stav |
| `/overlay`, `/overlay/golden`, `/ws/overlay` | HUD (implementace v `overlay/http.py`) |
| `/oauth/*` | Volitelný YouTube title (ne scene switch) |
| `/commentary` | TTS test UI |

**Není:** `/vr-status`, TUI.

## Key files

`api.py`, `dashboards.py`, `admin.py`, `admin_health.py`, `metrics.py`, `event_log.py`.

## Tests

`tests/test_api.py` (včetně 404 na `/vr-status`), `tests/test_admin_*.py`.

## Related

[API.md](../../../API.md), [web](web.md).
