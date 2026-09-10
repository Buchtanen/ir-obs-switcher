# Server / HTTP — branch delta (#273/#284 runtime status)

> **Větev `cursor/narrative-runtime-284-matrix-cad3`:** tenký delta k master `server.md`. Shipped HTTP kontrakt: [API.md](../../../API.md). Branch lookup: [§ golden-health identity](../inflight/README.md#284-273-golden-health-identity-slice-lookup), [§ timeline session identity](../inflight/README.md#284-273-timeline-session-identity-slice-lookup), [§ golden-health speech](../inflight/README.md#284-273-golden-health-speech-slice-lookup), [§ components llm/tts](../inflight/README.md#284-273-components-llm-tts-slice-lookup), [§ components detectors/facts](../inflight/README.md#284-273-components-detectors-facts-slice-lookup), [§ golden-health decisions](../inflight/README.md#284-273-golden-health-decisions-slice-lookup), [§ golden-health validate/speak](../inflight/README.md#284-273-golden-health-validatespeak-slice-lookup), [§ ManualAdmissionLatch](../inflight/README.md#284-273-manual-admission-latch-slice-lookup), [§ status_ready](../inflight/README.md#284-273-status-ready-slice-lookup).

## GET /health — `commentary` pole

`src/irswitch/server/api.py` přidává top-level:

```json
"commentary": { "status": "disabled", "reason": null }
```

- Projekce přes `project_commentary_health_component(get_narrative_runtime().status())` z `events/narrative_ingress.py`.
- Když není attached runtime → disabled library snapshot (`status: disabled`, `reason: null`).
- Disabled/degraded commentary **nespadí celý `/health`** — iRacing/OBS zůstávají autorita pro overall status.
- Detail: `GET /api/commentary/runtime` — timeline identity + `sessionPlan`/`sessionRef`/`occurrenceId`/`lineageId`/`stage` all-or-none (null idle/disabled/incomplete context — feat `f58c992`; live after valid `APPLY_CONTEXT_BATCH` — feat `ccd0697`) + fixní `language=en` + plný idle `speech` tvar + bounded `components.{llm,tts,tape,detectors,facts}` (llm/tts via `_llm_component_projection` / `_tts_component_projection` — stubs without attached component feat `3670502`; live llm residency/generation/model + ledger `configGeneration` when `LlmComponent` attached feat `60565ae`; live `lastAttempt` after admitted Qwen requests feat `19887aa`; live facts `viewRevision`/`active`/`historicalSummaries`/`historyComplete` + detectors `disabled` list when `DetectorBank` injected feat `d13d6bd`; disabled-library zeros feat `03c34b2`) + live `catalog`/`config`/`episodes`/`byTapeChannel` projection (packaged catalog hash; CONFIG_UPDATE ledger; `EpisodeRegistry` / `OpportunityQueue` counters when injected — feat `bdb9633`; stub slice feat `03c34b2`) + `queues.opportunities` ready stub (viz [events](events.md) + `API.md`).
- Decisions ring: additive `GET /api/commentary/runtime/decisions?limit=` — `commentary-runtime/2` newest-first rows; legacy `GET /api/commentary/decisions` beze změny (viz `API.md` + [§ golden-health decisions](../inflight/README.md#284-273-golden-health-decisions-slice-lookup)).
- Validate/speak: additive `POST /api/commentary/runtime/validate` + `POST /api/commentary/runtime/speak` — offline validate + `try_manual_speak` s `ManualAdmissionLatch` (503 `admission_timeout` on latch timeout); public `POST /api/commentary/validate|speak` cut over na NarrativeRuntime handlery (feat `f2c1f1b`; `/runtime/*` alias) (viz `API.md` + [§ golden-health validate/speak](../inflight/README.md#284-273-golden-health-validatespeak-slice-lookup) · [§ ManualAdmissionLatch](../inflight/README.md#284-273-manual-admission-latch-slice-lookup)).

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

`tests/test_api.py` — `/health` obsahuje `commentary`; `tests/test_narrative_runtime_http.py` — decisions + validate/speak/cutover + admission-timeout mounts (**16** rows); `tests/test_commentary_http.py` (**7** cutover rows); related suite **237** s narrative ingress identity + timeline session identity (null + live) + speech + decision + validate + status_ready (stub + live config/episodes/byTapeChannel) + llm/tts components + latch + public validate/speak cutover rows; ingress+http **42** (= prior **40** + **2** public-path cutover rows).

## Related

[API.md](../../../API.md), [inflight](../inflight/README.md), [events](events.md).
