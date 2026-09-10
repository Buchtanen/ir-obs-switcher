# Server / HTTP — branch delta (#273/#284 identity)

> **Větev `cursor/narrative-runtime-284-matrix-cad3`:** tenký delta k master `server.md`. Shipped HTTP kontrakt: [API.md](../../../API.md). Branch lookup: [inflight § golden-health identity](../inflight/README.md#284-273-golden-health-identity-slice-lookup).

## GET /health — `commentary` pole

`src/irswitch/server/api.py` přidává top-level:

```json
"commentary": { "status": "disabled", "reason": null }
```

- Projekce přes `project_commentary_health_component(get_narrative_runtime().status())` z `events/narrative_ingress.py`.
- Když není attached runtime → disabled library snapshot (`status: disabled`, `reason: null`).
- Disabled/degraded commentary **nespadí celý `/health`** — iRacing/OBS zůstávají autorita pro overall status.
- Detail timeline identity: `GET /api/commentary/runtime` (viz [events](events.md) + `API.md`).

## Soubory

| Soubor | Role |
| --- | --- |
| `server/api.py` | `GET /health` + bounded `commentary` |
| `events/narrative_ingress.py` | `project_commentary_health_component` |
| `events/narrative_runtime_http.py` | `get_narrative_runtime()` attach |

## Testy

`tests/test_api.py` — `/health` obsahuje `commentary`; related suite **198** s narrative ingress identity rows.

## Related

[API.md](../../../API.md), [inflight](../inflight/README.md), [events](events.md).
