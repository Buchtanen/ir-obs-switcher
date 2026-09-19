# Server / HTTP — branch delta (#273/#284 runtime status)

> **Větev `cursor/narrative-runtime-284-matrix-cad3`:** tenký delta k master `server.md`. Shipped HTTP kontrakt: [API.md](../../../API.md). Branch lookup: [§ golden-health identity](../inflight/README.md#284-273-golden-health-identity-slice-lookup), [§ timeline session identity](../inflight/README.md#284-273-timeline-session-identity-slice-lookup), [§ golden-health speech](../inflight/README.md#284-273-golden-health-speech-slice-lookup), [§ components llm/tts](../inflight/README.md#284-273-components-llm-tts-slice-lookup), [§ components detectors/facts](../inflight/README.md#284-273-components-detectors-facts-slice-lookup), [§ golden-health decisions](../inflight/README.md#284-273-golden-health-decisions-slice-lookup), [§ golden-health validate/speak](../inflight/README.md#284-273-golden-health-validatespeak-slice-lookup), [§ assignments route removal](../inflight/README.md#273-assignments-route-removal-slice-lookup), [§ dashboard versioned-contracts](../inflight/README.md#273-dashboard-versioned-contracts-slice-lookup), [§ ManualAdmissionLatch](../inflight/README.md#284-273-manual-admission-latch-slice-lookup), [§ manual speak body](../inflight/README.md#273-manual-speak-body-slice-lookup), [§ status_ready](../inflight/README.md#284-273-status-ready-slice-lookup), [§ loop liveness / supervisor heartbeats](../inflight/README.md#284-loop-liveness-slice-lookup), [§ health/API reason-code schema](../inflight/README.md#284-healthapi-reason-code-schema-slice-2026-09-10).

## GET /health — `commentary` pole

`src/irswitch/server/api.py` přidává top-level:

```json
"commentary": { "status": "disabled", "reason": null }
```

- Projekce přes `project_commentary_health_component(get_narrative_runtime().status())` z `events/narrative_ingress.py`.
- Když není attached runtime → disabled library snapshot (`status: disabled`, `reason: null`).
- `reason` je `null` when healthy/idle; otherwise first freeze-registry actor/recovery code from `RuntimeStatus.reason_codes` (closed enum `HealthCommentarySummary.reason` in `docs/v2.0.0/machine/api-contracts.schema.json`). Includes mailbox/admission codes (`mailbox_recovery`, `mailbox_overloaded`, `mailbox_evicted_update`, `deadline_admission_skipped`, `admission_timeout`, …) plus config/runtime codes (`component_unavailable`, `history_incomplete`, …) — feat `cffaab1`. Full list on `GET /api/commentary/runtime` → `diagnostics.reasonCodes`. Capacity fixed at **64** (56+7+1); no public mailbox capacity INI — see `CONFIG.md` + `API.md`.
- Disabled/degraded commentary **nespadí celý `/health`** — iRacing/OBS zůstávají autorita pro overall status.
- Detail: `GET /api/commentary/runtime` — timeline identity + `sessionPlan`/`sessionRef`/`occurrenceId`/`lineageId`/`stage` all-or-none (null idle/disabled/incomplete context — feat `f58c992`; live after valid `APPLY_CONTEXT_BATCH` — feat `ccd0697`) + fixní `language=en` + plný idle `speech` tvar + bounded `components.{llm,tts,tape,detectors,facts}` (llm/tts via `_llm_component_projection` / `_tts_component_projection` — stubs without attached component feat `3670502`; live llm residency/generation/model + ledger `configGeneration` when `LlmComponent` attached feat `60565ae`; live `lastAttempt` after admitted Qwen requests feat `19887aa`; live facts `viewRevision`/`active`/`historicalSummaries`/`historyComplete` + capacity health `status`/`reason` (`ready`/`null` | `degraded`/`fact_capacity_evicted` | `unavailable`/`fact_capacity_exhausted`; recovery on new lossless run — feat branch `cursor/fact-health-273-cad3`) + detectors `disabled` list when `DetectorBank` injected feat `d13d6bd`; disabled-library zeros feat `03c34b2`) + live `catalog`/`config`/`episodes`/`byTapeChannel` projection (packaged catalog hash; CONFIG_UPDATE ledger; `EpisodeRegistry` / `OpportunityQueue` counters when injected — feat `bdb9633`; stub slice feat `03c34b2`) + `queues.opportunities` ready stub + `loop.{active,lastReduceMonoMs,reduceCount,supervisors}` (active feat `c2e02d4`; reduce/supervisors feat `952cc1d`; race attaches `narrativeRuntime`/`narrativeShadow` supervisor snapshots; library without attach → `supervisors: {}`) (viz [events](events.md) + `API.md` + [§ loop liveness](../inflight/README.md#284-loop-liveness-slice-lookup)).
- Decisions ring: additive `GET /api/commentary/runtime/decisions?limit=` — `commentary-runtime/2` newest-first rows; legacy `GET /api/commentary/decisions` beze změny (viz `API.md` + [§ golden-health decisions](../inflight/README.md#284-273-golden-health-decisions-slice-lookup)).
- `GET /api/commentary/assignments` is **unregistered** (#273) — generic server 404, not a commentary tombstone; offline `render_assignments` stays for CLI (viz [§ assignments route removal](../inflight/README.md#273-assignments-route-removal-slice-lookup) · [public-contracts § Removed endpoint](../../v2.0.0/public-contracts.md)).
- Validate/speak: additive `POST /api/commentary/runtime/validate` + `POST /api/commentary/runtime/speak` — offline validate + `try_manual_speak` s `ManualAdmissionLatch` (503 `admission_timeout` on latch timeout); public `POST /api/commentary/validate|speak` cut over na NarrativeRuntime handlery (feat `f2c1f1b`; `/runtime/*` alias). Validate request exact keys + `factBindings` via `AtomicFact.from_dict`/FactRegistry ([§ validate AtomicFact/registry](../inflight/README.md#273-validate-atomicfact-registry-slice-lookup)). Transport error HTTP goldens: `invalid_json`/`invalid_request`/`validation_failed` exact bodies ([§ transport error HTTP goldens](../inflight/README.md#273-transport-error-http-goldens-slice-lookup)). Manual speak body frozen to exact keys `schemaVersion`/`text`/`language` only; unknown fields → **400** `invalid_request`; normalized `text` 1–400 no controls → else **422**; **202** `admittedState` exactly `committed` (branch `cursor/manual-speak-body-273-cad3` — [§ manual speak body](../inflight/README.md#273-manual-speak-body-slice-lookup)) (viz `API.md` + [§ golden-health validate/speak](../inflight/README.md#284-273-golden-health-validatespeak-slice-lookup) · [§ ManualAdmissionLatch](../inflight/README.md#284-273-manual-admission-latch-slice-lookup)).

## GET /commentary — operator page (#273 slice 2)

`src/irswitch/web/commentary/index.html` — TTS test / operator dashboard at `GET /commentary` (`commentary/http.py` static mount). **Branch-only #273 slice 2:** page JavaScript fetches **only** versioned `commentary-runtime/2` contracts; legacy v1 page paths removed from HTML/JS.

| Consumer | Path | Notes |
| --- | --- | --- |
| Runtime status panel | `GET /api/commentary/runtime` | Not legacy `GET /api/commentary/status` |
| Channel cadence (`byTapeChannel`) | same runtime status payload | kick/accepted/queued/selected/started/expired per catalog channel rendered on page (#273); no event-name parsing / no global DEBUG |
| Decision ring (“Proč ticho”) | `GET /api/commentary/runtime/decisions?limit=20` | Not legacy `GET /api/commentary/decisions` |
| Offline validate button | `POST /api/commentary/validate` | `commentary-runtime/2` body + `X-Requested-With: irswitch` |
| Server speak button | `POST /api/commentary/speak` | EN-only manual admit; body `{schemaVersion, text, language}` only; **202** `admittedState: committed` |

- Browser Web Speech (`speechSynthesis`) remains local-only; CS Czech option does not call server speak.
- `#273` observability close-out: page shows `byTapeChannel` cadence from runtime status; NarrativeTape volume is independent of `app.log_level` (full tape stays usable at INFO/WARN — see `CONFIG.md` `[commentary.tape]`).
- Legacy `GET /api/commentary/status` and `GET /api/commentary/decisions` **remain registered** for other consumers/tests; the operator page no longer references them (viz [§ dashboard versioned-contracts](../inflight/README.md#273-dashboard-versioned-contracts-slice-lookup) · [public-contracts § Removed endpoint](../../v2.0.0/public-contracts.md)).
- Config/TTS device edits stay on `config.ini` + `POST /config/reload` — not on this page.

## Soubory

| Soubor | Role |
| --- | --- |
| `server/api.py` | `GET /health` + bounded `commentary` |
| `events/narrative_ingress.py` | `project_commentary_health_component` |
| `events/narrative_runtime_http.py` | `get_narrative_runtime()` attach; runtime GET/POST mounts |
| `events/narrative_decision_projection.py` | `build_runtime_decision_entry`, `project_runtime_decisions` |
| `events/narrative_validate_projection.py` | `project_validate_response` (offline validate) |
| `events/narrative_manual_latch.py` | `ManualAdmissionLatch` rendezvous (not exported) |
| `commentary/http.py` | commentary test page + public routes; `#273` assignments route **not** registered |
| `web/commentary/index.html` | operator page UI; `#273` slice 2 — runtime/decisions/validate/speak fetch only |
| `commentary/assignments.py` | offline `render_assignments()` (CLI/docs; no HTTP mount) |

## Testy

`tests/test_api.py` — `/health` obsahuje `commentary`; `tests/test_narrative_runtime_http.py` — decisions + validate/speak/cutover + admission-timeout + manual-speak body/admittedState + disabled-subset loop asserts (**18** rows); `tests/test_commentary_http.py` (**9** = **7** cutover + **1** assignments-unregistered + **2** page contract rows incl. `test_commentary_page_uses_versioned_contracts_only`); `tests/test_narrative_ingress.py` — `test_project_commentary_health_reason_uses_actor_recovery_code` validates `/health` reason vs schema enum (feat `cffaab1`); related suite **306** s narrative ingress identity + timeline session identity (null + live) + speech + decision + validate + status_ready (stub + live config/episodes/byTapeChannel) + llm/tts components + loop heartbeats + latch + health reason codes + public validate/speak cutover + assignments generic-404 + operator-page contract rows; ingress+http **43** (= prior **42** + **1** health reason row).

## Related

[API.md](../../../API.md), [inflight](../inflight/README.md), [events](events.md).

- #273 golden freeze: `tests/test_commentary_runtime_goldens.py` locks `tests/fixtures/commentary_runtime/error_*.json` to `docs/v2.0.0/machine/api-goldens.json` and HTTP speak 409/503 bodies.

- #273 `/health` commentary freeze: goldens `health_commentary_*.json`; degraded/disabled commentary never flips overall `/health` alone (`tests/test_api.py`).

- #273 component health freeze: tape `capture_unavailable` + detectors `disabled[]` goldens (`status_component_*`, `status_health_projections_library.json`).
