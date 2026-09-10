# Events — branch delta (#273/#284 runtime status)

> **Větev `cursor/narrative-runtime-284-matrix-cad3`:** tenký delta k master `events.md`. Full v2 narrative moduly: [inflight](../inflight/README.md). Planning cycle + streamEpoch (branch-only): [§ planningCycleId + streamEpoch](../inflight/README.md#284-planningcycleid--streamepoch-slice-2026-09-10). ExposureStore sole-writer (branch-only): [§ ExposureStore sole-writer](../inflight/README.md#284-exposurestore-sole-writer-slice-2026-09-10). Replay closure (branch-only): [§ replay closure](../inflight/README.md#284-replay-closure-slice-2026-09-10). Actor-transition model-tests (branch-only): [§ actor-transition model-tests](../inflight/README.md#284-actor-transition-model-tests-slice-2026-09-10). Health/API reason-code schema (branch-only): [§ health/API reason-code schema](../inflight/README.md#284-healthapi-reason-code-schema-slice-2026-09-10). Identity: [§ golden-health identity](../inflight/README.md#284-273-golden-health-identity-slice-lookup). Timeline session identity (null-or-live): [§ timeline session identity](../inflight/README.md#284-273-timeline-session-identity-slice-lookup). Speech/language/components: [§ golden-health speech](../inflight/README.md#284-273-golden-health-speech-slice-lookup). Components llm/tts (stubs + live residency): [§ components llm/tts](../inflight/README.md#284-273-components-llm-tts-slice-lookup). Components detectors/facts (live projection): [§ components detectors/facts](../inflight/README.md#284-273-components-detectors-facts-slice-lookup). Decisions ring: [§ golden-health decisions](../inflight/README.md#284-273-golden-health-decisions-slice-lookup). Validate/speak: [§ golden-health validate/speak](../inflight/README.md#284-273-golden-health-validatespeak-slice-lookup). Manual admission latch: [§ ManualAdmissionLatch](../inflight/README.md#284-273-manual-admission-latch-slice-lookup). Status_ready catalog/config/episodes: [§ status_ready](../inflight/README.md#284-273-status-ready-slice-lookup).

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

## Session identity (`events/narrative_runtime.py`)

`RuntimeStatus` + reducer state track (all-or-none; null until valid context):

| Field | Default | Update |
| --- | --- | --- |
| `session_plan` | `null` | planning `APPLY_CONTEXT_BATCH` → `_session_identity_from_timeline(timeline)` |
| `session_ref` | `null` | stejně (`subSessionId`, `sessionNum`) |
| `occurrence_id` | `null` | stejně |
| `lineage_id` | `null` | stejně |
| `stage` | `null` | stejně (`practice` \| `qualifying` \| `race`) |

`_session_identity_from_timeline`: neúplný/invalid set → všechny null (maže i dříve live hodnoty). `sessionPlan` z timeline `sessionPlan` když validní, jinak z `sessionPlanRevision` + stages do current stage. Ingress projekce: `_timeline_session_identity(status)` v `project_runtime_status`.

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

## LLM transport/residency (`events/narrative_runtime.py`)

`RuntimeStatus` + `NarrativeRuntime.status()` track optional attached `LlmComponent`:

| Field | Default | Update |
| --- | --- | --- |
| `llm_attached` | `false` | `NarrativeRuntime(llm_component=...)` |
| `llm_generation` | `0` | `component.applied_generation` when attached |
| `llm_model` | `null` | `component.model` (set by `warmup_qwen_component`) |
| `llm_residency_evidence` | `"not_requested"` | public enum only: `warmup_succeeded` \| `not_requested` |
| `llm_reason` | `null` | `component_unavailable` when mapped health is `unavailable` |

`status()` syncs `component_health["llm"]` from component: `idle→ready`, `pending→starting`, `ready→ready`, `failed→unavailable`.

## Facts / detectors status projection (`events/narrative_runtime.py`, `events/detector_bank.py`)

`RuntimeStatus` + reducer state track optional FactView counts and detector disable list:

| Field | Default | Update |
| --- | --- | --- |
| `fact_view_revision` | `null` | planning `APPLY_CONTEXT_BATCH` → `factView.viewRevision` |
| `fact_active_count` | `0` | `_ingest_fact_view_counts` → `len(facts[])` |
| `fact_historical_summary_count` | `0` | `_ingest_fact_view_counts` → `len(compactedSummaryRefs[])` |
| `detector_disabled` | `()` | `_detector_disabled_snapshot()` → `DetectorBank.disabled_for_status()` when bank injected; else empty |

`history_complete` on `RuntimeStatus` also updates from FactView `historyComplete` when present. Optional `NarrativeRuntime(detector_bank=...)`; without bank, ingress keeps `components.detectors.disabled: []`. Live projection feat `d13d6bd`.

## Loop heartbeats (`events/narrative_runtime.py`, `events/narrative_ingress.py`)

`RuntimeStatus` + reducer state track actor loop observability for `GET /api/commentary/runtime` `loop` block:

| Field | Default | Update |
| --- | --- | --- |
| `loop_active` | `false` | `true` while `NarrativeRuntime.run()` owns the actor (`_run_active`; feat `c2e02d4`) |
| `loop_last_reduce_mono_ms` | `null` | monotonic ms after each `reduce_next()` (feat `952cc1d`) |
| `loop_reduce_count` | `0` | monotonic count of completed `reduce_next()` calls (feat `952cc1d`) |
| `loop_supervisors` | `{}` | snapshots from registered providers via `attach_supervisor_heartbeat(name, provider)` (feat `952cc1d`) |

`project_runtime_status` emits `loop.{active, lastReduceMonoMs, reduceCount, supervisors}` (camelCase supervisor keys). Each supervisor payload mirrors `WorkerSupervisor.status_snapshot`: `{running, restarts, lastError}`. Race cutover attaches `narrativeRuntime` + `narrativeShadow` in `race/runtime.py`. Library without attach → `supervisors: {}`. Provider exceptions are skipped fail-soft.

## Ingress projector (`events/narrative_ingress.py`)

- `project_runtime_status(RuntimeStatus)` — `language`: fixní `"en"`; `speech`: plný tvar `{state, sourceKind, utteranceId, beatId, opportunityId, backend, backendGeneration, dispatchedAtMonoMs, acceptedAtMonoMs, lastTerminal}`; `components`: bounded `{llm, tts, tape, detectors, facts}` z `RuntimeStatus.component_health` / `tape_status` (tape default `disabled`, drops `0`); `components.llm` / `components.tts` via `_llm_component_projection` / `_tts_component_projection` — without attached component: stub defaults (feat `3670502`) but `configGeneration` reads CONFIG_UPDATE `desiredGeneration` when ledger present; with attached warmed component (feat `60565ae`): live `generation`/`model`/`residencyEvidence`/`status`/`reason`; tts speech-lane `backend`/`backendGeneration`; both `configGeneration` from ledger; `lastAttempt` `null` until first admitted Qwen completes (warmup/authored ignored; feat `19887aa` — `{requestId, outcome, ttfbMs, ttftMs, totalMs, reducerLagMs, terminalReason}`); `components.facts` — live `viewRevision`/`active`/`historicalSummaries`/`historyComplete` from `RuntimeStatus` fact fields (feat `d13d6bd`; disabled-library zeros feat `03c34b2`); `components.detectors` — `status=ready`, `reason=null`, live sorted `disabled` `{id, reason}` rows from `RuntimeStatus.detector_disabled` when `DetectorBank` injected (feat `d13d6bd`; empty without bank); `loop` — `{active, lastReduceMonoMs, reduceCount, supervisors}` from loop heartbeat fields (active feat `c2e02d4`; reduce/supervisors feat `952cc1d`); plus #273 bloky `catalog`/`config`/`episodes`/`byTapeChannel`: `catalog` — packaged hash (`_packaged_catalog_projection`); `config` — live CONFIG_UPDATE ledger přes `_config_projection` (`RuntimeStatus.config_ledger`; invalid/cleared → `_unloaded_config_projection`); `episodes` — live counts z injected `EpisodeRegistry` přes `_episodes_projection` (`RuntimeStatus.episode_counts`; no registry → `_empty_episodes_projection`); `byTapeChannel` — live counters z injected `OpportunityQueue.tape_channel_status_counts()` přes `_by_tape_channel_projection` (empty when no queue/counters); `queues.opportunities` (depth 0, `OPPORTUNITY_CAPACITY`); plus `timeline` (identity + `sessionPlan`/`sessionRef`/`occurrenceId`/`lineageId`/`stage` all-or-none — null idle/disabled/incomplete context, live after valid `APPLY_CONTEXT_BATCH` via `_timeline_session_identity`; satisfies `session_identity_all_or_none`), `queues.mailbox`, recovery, diagnostics. Live wiring feat `bdb9633`; stub slice feat `03c34b2`; live llm residency feat `60565ae`; live detectors/facts feat `d13d6bd`.
- `project_commentary_health_component(status=None)` → `{status, reason}` pro `GET /health` (jen top-level status/reason, ne speech/components). `reason` je první položka z `RuntimeStatus.reason_codes` (closed enum `HealthCommentarySummary.reason` v `api-contracts.schema.json`); freeze-registry kódy zahrnují `mailbox_recovery`, `mailbox_overloaded`, `mailbox_evicted_update`, `deadline_admission_skipped`, `admission_timeout`, `history_incomplete`, `component_unavailable`, … (feat `cffaab1`). `project_runtime_status` emituje plný `diagnostics.reasonCodes`. Jediný ingress helper, který sahá do `server/api.py`. **Not** exported z `events/__init__.py`.

## Decision ring (`events/narrative_decision_projection.py`, `events/narrative_runtime.py`)

- `build_runtime_decision_entry`, `project_runtime_decisions` — pure projection helpers; **not** exported z `events/__init__.py`.
- `NarrativeRuntime`: bounded deque `DECISION_CAPACITY=128`; každý `_consult_director` append (`selected` / `silence` / `replaced`); `decisions(limit)` newest-first.

## Validate projection (`events/narrative_validate_projection.py`)

- `project_validate_response` — offline `ValidateRequest`→`ValidateResponse` (`commentary-runtime/2`); caller-supplied EN text + `beatId` + `actorBindings` / `factBindings`; nečte live runtime. **Not** exported z `events/__init__.py`.
- HTTP mount: `POST /api/commentary/runtime/validate` + public `POST /api/commentary/validate` v `events/narrative_runtime_http.py` / `commentary/http.py` (200 i když `valid=false`; 400 malformed; cutover feat `f2c1f1b`).

## Manual admission latch (`events/narrative_manual_latch.py`)

- `ManualAdmissionLatch` — one-shot rendezvous `pending | actor_claimed | caller_abandoned`; `ADMISSION_TIMEOUT_S=1.0`. **Not** exported z `events/__init__.py`.
- `NarrativeRuntime.register_manual_latch` / `_pop_manual_latch` — process-local map keyed by `requestId`.

## Manual speak (`events/narrative_runtime.py`)

- `ManualSpeakOutcome`, `NarrativeRuntime.try_manual_speak` — alokuje latch, admitne `MANUAL_SPEAK_REQUEST`, awaitne resolution (default 1s; `timeout_s` / `reduce_inline` kwargs). Když actor loop neběží, sync inline reduce; jinak `_on_manual` claimne latch před lane mutate. Timeout → `admission_timeout`; abandoned latch zůstává registrovaný (`manual_abandoned`).
- HTTP mount: `POST /api/commentary/runtime/speak` (202 / 409 / 422 / 503 incl. `admission_timeout`). Legacy `POST /api/commentary/speak` beze změny.
- Manual speak **nikdy** nezapisuje do `ExposureStore` (`exposure_skipped_manual`).

## ExposureStore sole-writer (`events/exposure_store.py`, `events/narrative_runtime.py`)

- Optional `NarrativeRuntime(exposure_store: ExposureStore | None = None)`; test helper `exposure_store_for_test()`.
- On narrative realization commit: `_arm_pending_exposure` snapshots catalog beat fields (`family`, `pattern`, `tape_channel`, `policy_id`, `beat_role`, semantic identity from episode when present).
- On `PLAYBACK_ACCEPTED` (`committed→speaking`): `_record_exposure` is the **sole writer** into `ExposureStore` (`phase=speaking`, `source_kind=narrative`, weight 1.0); effects `exposure_step:recorded`, `exposure_recorded`.
- Manual speak never records. Default `exposure_store` absent = legacy matrix unchanged (no exposure effects).
- Race shadow path (`race/runtime.py`): constructs `ExposureStore()` and passes into `NarrativeRuntime(..., exposure_store=exposure_store, ...)` (feat `c6ffbe3`).
- Tests: `tests/test_narrative_runtime.py` — `test_exposure_recorded_on_playback_accepted_as_sole_writer`, `test_manual_playback_does_not_record_exposure`, `test_exposure_store_absent_keeps_legacy_playback` (**3** rows). **Docs: `API.md` / `CONFIG.md` unchanged.**

## Goldens

- Identity: `tests/fixtures/commentary_runtime/status_identity_disabled.json` (null session fields), `status_identity_after_context.json` (live session identity after APPLY_CONTEXT; feat `ccd0697`)
- Timeline session identity: `tests/fixtures/commentary_runtime/status_timeline_session_null.json` (idle null subset; feat `f58c992`)
- Status_ready library: `tests/fixtures/commentary_runtime/status_ready_library.json` (`catalog`, `config`, `episodes`, `byTapeChannel`, `queues.opportunities`, `components.detectors`/`facts` disabled-library zeros)
- Speech idle: `tests/fixtures/commentary_runtime/status_speech_idle.json` (`language`, idle `speech`, bounded `components` incl. schema-complete llm/tts)
- Components llm/tts: `tests/fixtures/commentary_runtime/status_components_llm_tts.json`
- Decisions selected: `tests/fixtures/commentary_runtime/decisions_selected.json`
- Validate: `validate_request.json`, `validate_supported.json`, `validate_rejected.json`
- Speak: `speak_request.json`, `speak_accepted.json`, `error_admission_timeout.json`

## Testy

`tests/test_narrative_ingress.py` (**45** = prior **44** + **1** health reason-code row feat `cffaab1`). `tests/test_narrative_runtime.py` (**141** = prior **140** + **1** deadline-skip reason-code row feat `cffaab1`). `tests/test_actor_transition_goldens.py` (**29** = **13** `raceTraces` + **10** `overflowScenarios` + **2** `orderingScenarios` + sync/assert rows + **2** runtime race rows). Runtime+goldens **171**. `tests/test_narrative_runtime_http.py` (**16** incl. disabled-subset loop asserts + **2** public-path cutover rows). `tests/test_commentary_http.py` (**7**). Related **305** (= prior **303** + **2** reason-code rows). Ingress+http **43** (= prior **42** + **1** health reason row).

## Still deferred (#284 OPEN, #273 remainder)

Full #273 schema: master cutover only (human kick). Loop liveness landed feat `c2e02d4` (`loop.active`). Loop supervisor heartbeats landed feat `952cc1d` (`loop.lastReduceMonoMs`, `loop.reduceCount`, `loop.supervisors`). Live llm/tts transport/residency projection landed feat `60565ae`. Live llm `lastAttempt` projection landed feat `19887aa`. Live detectors/facts status projection landed feat `d13d6bd`. ExposureStore sole-writer landed feat `c6ffbe3` (`NarrativeRuntime._record_exposure` on playback accept when composed). Legacy validate/speak public-path cutover landed (feat `f2c1f1b`); thin validate/speak slice landed (feat SHA `65651bc`); thin `ManualAdmissionLatch` slice landed (feat SHA `ca0f2f6`); status_ready stub slice landed (feat SHA `03c34b2`); live catalog/config/episodes/byTapeChannel status projection landed (feat SHA `bdb9633`); thin components llm/tts schema stubs landed (feat SHA `3670502`); timeline session identity null stubs landed (feat SHA `f58c992`); live timeline session identity wiring landed (feat SHA `ccd0697`). EventSubscription full replace landed feat `44dab2f` (`NarrativeShadowConsumer(..., legacy_stream_handler=None)`; no SessionReset/ConfigUpdate/batch mirror into `CommentaryConsumer`; sole ingress shadow admit → `NarrativeMailbox`; `CommentaryConsumer` TTS sink/status/filler with `idle_speech_enabled=False`, `_commentary_subscription=None`; `tests/test_narrative_fanout_cutover.py` **8** cutover rows). Reducer replay closure landed feat `b86a336` (`command_from_dict` rebuilds `REALIZATION_SUCCEEDED`/`FAILED`; optional `runtime_factory` on capture/replay/journal; journal replay reproduces `director_selected` + committed lane when recorded realization supplied; `tests/test_narrative_reducer_replay.py` **5** + `tests/test_narrative_command_journal.py` **9** = **14** passed). Actor-transition model-tests landed test `fe70f2a` (`tests/test_actor_transition_goldens.py` **29** against frozen `docs/v2.0.0/machine/actor-transition-goldens.json` — **13** `raceTraces`, **10** `overflowScenarios`, **2** `orderingScenarios`, `pairCoverage`↔`transitionMatrix` sync (**85**), on-disk↔builder sync, plus **2** `NarrativeRuntime` race evidence rows). Health/API reason-code schema landed feat `cffaab1` (`_reason_codes()` mailbox/admission codes; `/health` `commentary.reason`; `diagnostics.reasonCodes`; `API.md` + `CONFIG.md` + `api-contracts.schema.json` updated in feat commit).

**#284 stays OPEN** (**33/41** AC, **8** remain) — no master PR.

## Related

[server](server.md), [API.md](../../../API.md), [implementation-handover](../../v2.0.0/implementation-handover.md).
