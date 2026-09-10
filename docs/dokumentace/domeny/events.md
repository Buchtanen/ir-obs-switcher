# Events — branch delta (#273/#284 runtime status)

> **Větev `cursor/narrative-runtime-284-matrix-cad3`:** tenký delta k master `events.md`. Full v2 narrative moduly: [inflight](../inflight/README.md). Identity: [§ golden-health identity](../inflight/README.md#284-273-golden-health-identity-slice-lookup). Speech/language/components: [§ golden-health speech](../inflight/README.md#284-273-golden-health-speech-slice-lookup). Components llm/tts stubs: [§ components llm/tts](../inflight/README.md#284-273-components-llm-tts-slice-lookup). Decisions ring: [§ golden-health decisions](../inflight/README.md#284-273-golden-health-decisions-slice-lookup). Validate/speak: [§ golden-health validate/speak](../inflight/README.md#284-273-golden-health-validatespeak-slice-lookup). Manual admission latch: [§ ManualAdmissionLatch](../inflight/README.md#284-273-manual-admission-latch-slice-lookup). Status_ready catalog/config/episodes: [§ status_ready](../inflight/README.md#284-273-status-ready-slice-lookup).

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

## Speech projection (`events/narrative_runtime.py`)

`RuntimeStatus` + reducer state track speech pole pro `GET /api/commentary/runtime`:

| Field | Default | Update |
| --- | --- | --- |
| `speech_source_kind` | `null` | `_begin_speech_projection` na manual speak / realization commit (`manual` / `narrative`) |
| `speech_utterance_id` | `null` | stejně; `_clear_active_speech_projection` po terminal/deadline |
| `speech_beat_id` | `null` | narrative commit z `_realization.beatId` |
| `speech_opportunity_id` | `null` | bound `_opportunity_id` při commit |
| `speech_backend` | `null` | (reserved; zatím null v projekci) |
| `speech_backend_generation` | `null` | utterance token |
| `speech_dispatched_at_mono_ms` | `null` | enqueue mono při begin |
| `speech_accepted_at_mono_ms` | `null` | `PLAYBACK_ACCEPTED` (`committed`→`speaking`) |
| `speech_last_terminal` | `null` | `_retain_speech_terminal` po `SPEECH_*` terminal nebo `SPEECH_DEADLINE_ELAPSED` ve `stopping` — **zůstává** i když lane vrátí `idle` |

Lane `state` v HTTP projekci mapuje `idle|building|committed|speaking|stopping` z actor lane bookkeepingu.

## Ingress projector (`events/narrative_ingress.py`)

- `project_runtime_status(RuntimeStatus)` — `language`: fixní `"en"`; `speech`: plný tvar `{state, sourceKind, utteranceId, beatId, opportunityId, backend, backendGeneration, dispatchedAtMonoMs, acceptedAtMonoMs, lastTerminal}`; `components`: bounded `{llm, tts, tape}` z `RuntimeStatus.component_health` / `tape_status` (tape default `disabled`, drops `0`); `components.llm` / `components.tts` schema-complete stubs via `_llm_component_projection` / `_tts_component_projection` (llm: `generation=0`, `configGeneration=0`, `model="unconfigured"`, `residencyEvidence="not_requested"`, `lastAttempt=null`; tts: `backend=null` nebo speech backend v `{sapi,espeak,supertonic}`, `backendGeneration` ze speech lane nebo `0`, `configGeneration=0`, `quarantinedGeneration=null`, `voice=null`; **not** live transport/residency); plus tenké #273 stub bloky `catalog` (`narrative-catalog/2`, packaged `hash` přes `load_narrative_catalog().require_catalog().catalog_hash`, `eventIdentifierCount: 60`, `beatCount: 64`), `config` (unloaded zeros), `episodes` (empty counts + `ACTIVE_CAP`/`RESOLVED_CAP`), `byTapeChannel: {}`, `queues.opportunities` (depth 0, `OPPORTUNITY_CAPACITY`), `components.detectors` / `components.facts` (ready stubs; `facts.historyComplete` z `RuntimeStatus`); plus `timeline`, `queues.mailbox`, recovery, diagnostics. **Not** live wiring catalog/config/episodes/tape channels/detectors/facts/llm/tts transport.
- `project_commentary_health_component(status=None)` → `{status, reason}` pro `GET /health` (jen top-level status/reason, ne speech/components). Jediný ingress helper, který sahá do `server/api.py`. **Not** exported z `events/__init__.py`.

## Decision ring (`events/narrative_decision_projection.py`, `events/narrative_runtime.py`)

- `build_runtime_decision_entry`, `project_runtime_decisions` — pure projection helpers; **not** exported z `events/__init__.py`.
- `NarrativeRuntime`: bounded deque `DECISION_CAPACITY=128`; každý `_consult_director` append (`selected` / `silence` / `replaced`); `decisions(limit)` newest-first.

## Validate projection (`events/narrative_validate_projection.py`)

- `project_validate_response` — offline `ValidateRequest`→`ValidateResponse` (`commentary-runtime/2`); caller-supplied EN text + `beatId` + `actorBindings` / `factBindings`; nečte live runtime. **Not** exported z `events/__init__.py`.
- HTTP mount: `POST /api/commentary/runtime/validate` v `events/narrative_runtime_http.py` (200 i když `valid=false`; 400 malformed).

## Manual admission latch (`events/narrative_manual_latch.py`)

- `ManualAdmissionLatch` — one-shot rendezvous `pending | actor_claimed | caller_abandoned`; `ADMISSION_TIMEOUT_S=1.0`. **Not** exported z `events/__init__.py`.
- `NarrativeRuntime.register_manual_latch` / `_pop_manual_latch` — process-local map keyed by `requestId`.

## Manual speak (`events/narrative_runtime.py`)

- `ManualSpeakOutcome`, `NarrativeRuntime.try_manual_speak` — alokuje latch, admitne `MANUAL_SPEAK_REQUEST`, awaitne resolution (default 1s; `timeout_s` / `reduce_inline` kwargs). Když actor loop neběží, sync inline reduce; jinak `_on_manual` claimne latch před lane mutate. Timeout → `admission_timeout`; abandoned latch zůstává registrovaný (`manual_abandoned`).
- HTTP mount: `POST /api/commentary/runtime/speak` (202 / 409 / 422 / 503 incl. `admission_timeout`). Legacy `POST /api/commentary/speak` beze změny.

## Goldens

- Identity: `tests/fixtures/commentary_runtime/status_identity_disabled.json`, `status_identity_after_context.json`
- Status_ready library: `tests/fixtures/commentary_runtime/status_ready_library.json` (`catalog`, `config`, `episodes`, `byTapeChannel`, `queues.opportunities`, `components.detectors`/`facts` stubs)
- Speech idle: `tests/fixtures/commentary_runtime/status_speech_idle.json` (`language`, idle `speech`, bounded `components` incl. schema-complete llm/tts)
- Components llm/tts: `tests/fixtures/commentary_runtime/status_components_llm_tts.json`
- Decisions selected: `tests/fixtures/commentary_runtime/decisions_selected.json`
- Validate: `validate_request.json`, `validate_supported.json`, `validate_rejected.json`
- Speak: `speak_request.json`, `speak_accepted.json`, `error_admission_timeout.json`

## Testy

`tests/test_narrative_ingress.py` (**19** = prior **18** + **1** llm/tts golden row). `tests/test_narrative_runtime.py` latch rows (**3**). Related **221** (= prior **220** + **1** llm/tts row).

## Still deferred (#284 OPEN, #273 remainder)

Full #273 schema: live llm/tts transport/residency wiring; live catalog/config/episodes/byTapeChannel wiring; live detectors/facts (beyond ready stubs); timeline session fields (`sessionPlan`/`sessionRef`/`occurrenceId`/`lineageId`/`stage`); final legacy `/api/commentary/validate|speak` cutover; integrated loop liveness; master cutover. Thin validate/speak slice landed (feat SHA `65651bc`); thin `ManualAdmissionLatch` slice landed (feat SHA `ca0f2f6`); thin status_ready catalog/config/episodes slice landed (feat SHA `03c34b2`); thin components llm/tts schema stubs landed (feat SHA `3670502`).

## Related

[server](server.md), [API.md](../../../API.md), [implementation-handover](../../v2.0.0/implementation-handover.md).
