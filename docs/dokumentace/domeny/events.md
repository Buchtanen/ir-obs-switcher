# Events — branch delta (#273/#284 runtime status)

> **Větev `cursor/narrative-runtime-284-matrix-cad3`:** tenký delta k master `events.md`. Full v2 narrative moduly: [inflight](../inflight/README.md). Identity: [§ golden-health identity](../inflight/README.md#284-273-golden-health-identity-slice-lookup). Speech/language/components: [§ golden-health speech](../inflight/README.md#284-273-golden-health-speech-slice-lookup). Decisions ring: [§ golden-health decisions](../inflight/README.md#284-273-golden-health-decisions-slice-lookup). Validate/speak: [§ golden-health validate/speak](../inflight/README.md#284-273-golden-health-validatespeak-slice-lookup).

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

- `project_runtime_status(RuntimeStatus)` — `language`: fixní `"en"`; `speech`: plný tvar `{state, sourceKind, utteranceId, beatId, opportunityId, backend, backendGeneration, dispatchedAtMonoMs, acceptedAtMonoMs, lastTerminal}`; `components`: bounded `{llm, tts, tape}` z `RuntimeStatus.component_health` / `tape_status` (tape default `disabled`, drops `0`); plus `timeline`, queues, recovery, diagnostics.
- `project_commentary_health_component(status=None)` → `{status, reason}` pro `GET /health` (jen top-level status/reason, ne speech/components). Jediný ingress helper, který sahá do `server/api.py`. **Not** exported z `events/__init__.py`.

## Decision ring (`events/narrative_decision_projection.py`, `events/narrative_runtime.py`)

- `build_runtime_decision_entry`, `project_runtime_decisions` — pure projection helpers; **not** exported z `events/__init__.py`.
- `NarrativeRuntime`: bounded deque `DECISION_CAPACITY=128`; každý `_consult_director` append (`selected` / `silence` / `replaced`); `decisions(limit)` newest-first.

## Validate projection (`events/narrative_validate_projection.py`)

- `project_validate_response` — offline `ValidateRequest`→`ValidateResponse` (`commentary-runtime/2`); caller-supplied EN text + `beatId` + `actorBindings` / `factBindings`; nečte live runtime. **Not** exported z `events/__init__.py`.
- HTTP mount: `POST /api/commentary/runtime/validate` v `events/narrative_runtime_http.py` (200 i když `valid=false`; 400 malformed).

## Manual speak (`events/narrative_runtime.py`)

- `ManualSpeakOutcome`, `NarrativeRuntime.try_manual_speak` — sync admit + reduce pro manual speak (bez plného `ManualAdmissionLatch` / 1s await; ten zůstává deferred).
- HTTP mount: `POST /api/commentary/runtime/speak` (202 / 409 / 422 / 503). Legacy `POST /api/commentary/speak` beze změny.

## Goldens

- Identity: `tests/fixtures/commentary_runtime/status_identity_disabled.json`, `status_identity_after_context.json`
- Speech idle: `tests/fixtures/commentary_runtime/status_speech_idle.json` (`language`, idle `speech`, bounded `components`)
- Decisions selected: `tests/fixtures/commentary_runtime/decisions_selected.json`
- Validate: `validate_request.json`, `validate_supported.json`, `validate_rejected.json`
- Speak: `speak_request.json`, `speak_accepted.json`

## Testy

`tests/test_narrative_ingress.py` (**17** = prior **14** + **3** validate rows). Related **215**.

## Still deferred (#284 OPEN, #273 remainder)

Full #273 schema: full components (detectors/facts), catalog/config/episodes/byTapeChannel; full `ManualAdmissionLatch`; final legacy `/api/commentary/validate|speak` cutover; integrated loop liveness; master cutover. Thin validate/speak slice landed (feat SHA `65651bc`).

## Related

[server](server.md), [API.md](../../../API.md), [implementation-handover](../../v2.0.0/implementation-handover.md).
