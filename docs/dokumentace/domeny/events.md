# Events — branch delta (#273/#284 runtime identity)

> **Větev `cursor/narrative-runtime-284-matrix-cad3`:** tenký delta k master `events.md`. Full v2 narrative moduly: [inflight](../inflight/README.md). Identity slice: [§ golden-health identity](../inflight/README.md#284-273-golden-health-identity-slice-lookup).

## NarrativeRuntime identity (`events/narrative_runtime.py`)

`RuntimeStatus` + reducer state track:

| Field | Default (před prvním context) | Update |
| --- | --- | --- |
| `broadcast_epoch` | `0` | planning `APPLY_CONTEXT_BATCH` → `timeline.broadcastEpoch` |
| `stream_epoch` | `0` | `timeline.streamEpoch` |
| `narrative_run_active` | `false` | `timeline.narrativeRunActive`; `SHUTDOWN` → `false` |
| `stream_active` | `null` | `timeline.streamActive` nebo z `obsState` |
| `stream_state` | `"unknown"` | `obsState` / `streamState` |

`SHUTDOWN` maže `narrative_run_active`, **`stream_epoch` zůstává**.

## Ingress projector (`events/narrative_ingress.py`)

- `project_runtime_status(RuntimeStatus)` — `timeline`: `broadcastEpoch`, `streamEpoch`, `narrativeRunActive`, `streamActive`, `streamState`, `historyComplete` (+ speech/queues/recovery/diagnostics).
- `project_commentary_health_component(status=None)` → `{status, reason}` pro `GET /health`. Jediný ingress helper, který sahá do `server/api.py`. **Not** exported z `events/__init__.py`.

## Goldens

`tests/fixtures/commentary_runtime/status_identity_disabled.json`, `status_identity_after_context.json`.

## Testy

`tests/test_narrative_ingress.py` (**8** = prior **5** + **3** identity/health). Related **198**.

## Still deferred (#284 OPEN)

Full #273 schema: decisions/validate/speak goldens, full components, catalog; integrated loop liveness; master cutover.

## Related

[server](server.md), [API.md](../../../API.md), [implementation-handover](../../v2.0.0/implementation-handover.md).
