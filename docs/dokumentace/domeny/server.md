# Server / HTTP — branch delta (#273/#284 runtime status)

> **Větev `cursor/narrative-runtime-284-matrix-cad3`:** tenký delta k master `server.md`. Shipped HTTP kontrakt: [API.md](../../../API.md). Branch lookup: [§ golden-health identity](../inflight/README.md#284-273-golden-health-identity-slice-lookup), [§ golden-health speech](../inflight/README.md#284-273-golden-health-speech-slice-lookup), [§ components llm/tts](../inflight/README.md#284-273-components-llm-tts-slice-lookup), [§ golden-health decisions](../inflight/README.md#284-273-golden-health-decisions-slice-lookup), [§ golden-health validate/speak](../inflight/README.md#284-273-golden-health-validatespeak-slice-lookup), [§ ManualAdmissionLatch](../inflight/README.md#284-273-manual-admission-latch-slice-lookup), [§ status_ready](../inflight/README.md#284-273-status-ready-slice-lookup).

## GET /health — `commentary` pole

`src/irswitch/server/api.py` přidává top-level:

```json
"commentary": { "status": "disabled", "reason": null }
```

- Projekce přes `project_commentary_health_component(get_narrative_runtime().status())` z `events/narrative_ingress.py`.
- Když není attached runtime → disabled library snapshot (`status: disabled`, `reason: null`).
- Disabled/degraded commentary **nespadí celý `/health`** — iRacing/OBS zůstávají autorita pro overall status.
- Detail: `GET /api/commentary/runtime` — timeline identity + fixní `language=en` + plný idle `speech` tvar + bounded `components.{llm,tts,tape,detectors,facts}` (llm/tts schema-complete stubs via `_llm_component_projection` / `_tts_component_projection`; **not** live transport/residency) + tenké stub bloky `catalog`/`config`/`episodes`/`byTapeChannel`/`queues.opportunities` (viz [events](events.md) + `API.md`; **not** full live wiring).
- Decisions ring: additive `GET /api/commentary/runtime/decisions?limit=` — `commentary-runtime/2` newest-first rows; legacy `GET /api/commentary/decisions` beze změny (viz `API.md` + [§ golden-health decisions](../inflight/README.md#284-273-golden-health-decisions-slice-lookup)).
- Validate/speak: additive `POST /api/commentary/runtime/validate` + `POST /api/commentary/runtime/speak` — offline validate + `try_manual_speak` s `ManualAdmissionLatch` (503 `admission_timeout` on latch timeout); legacy `POST /api/commentary/validate|speak` beze změny (viz `API.md` + [§ golden-health validate/speak](../inflight/README.md#284-273-golden-health-validatespeak-slice-lookup) · [§ ManualAdmissionLatch](../inflight/README.md#284-273-manual-admission-latch-slice-lookup)).

## Soubory

| Soubor | Role |
| --- | --- |
| `server/api.py` | `GET /health` + bounded `commentary` |
| `events/narrative_ingress.py` | `project_commentary_health_component` |
| `events/narrative_runtime_http.py` | `get_narrative_runtime()` attach; runtime GET/POST mounts |
| `events/narrative_decision_projection.py` | `build_runtime_decision_entry`, `project_runtime_decisions` |
| `events/narrative_validate_projection.py` | `project_validate_response` (offline validate) |
| `events/narrative_manual_latch.py` | `ManualAdmissionLatch` rendezvous (not exported) |

## Testy

`tests/test_api.py` — `/health` obsahuje `commentary`; `tests/test_narrative_runtime_http.py` — decisions + validate/speak + admission-timeout mounts (**14** rows); related suite **221** s narrative ingress identity + speech + decision + validate + status_ready + llm/tts components + latch rows.

## Related

[API.md](../../../API.md), [inflight](../inflight/README.md), [events](events.md).
