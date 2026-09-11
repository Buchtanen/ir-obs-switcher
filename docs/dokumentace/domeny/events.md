# Events — branch delta (#272 **CLOSED**; #273 **CLOSED**; #274 closeout evidence; #275 CLOSED; #276 slice 7 shadow; #277 slice 1 open; #284 **CLOSED** merged @ `77452a9`)

> **Větev `cursor/timing-family-map-275-cad3` (#275, slice 1):** timing lap/SF + sector inventory — [§ #275 map](../inflight/README.md#275-timing-family-map-slice-1-lookup) · [timing-family-migration.md](../../v2.0.0/timing-family-migration.md).

## Timing family migration map (`contracts/timing_family_map.py`)

Slice 1–2 inventory for Wave G #275 (all `migration_status=shadow`):

| Helper | Role |
| --- | --- |
| `timing_family_rows()` | Closed rows for timing wires + `SESSION_INTRO_*` / `QUALI_RECAP` |
| `migration_status_by_wire_id()` | Coverage-matrix companion |
| `lap_complete_is_not_race_finish()` | AC: lap completion ≠ race finish |
| `gain_and_loss_polarities_are_distinct()` | Slice 2: pace gain ≠ time lost |
| `invalid_lap_scope_is_explicit()` | Slice 3 AC: PRACTICE\|QUALIFYING only |
| `inherited_facts_use_active_lineage_only()` | Slice 4 AC: session intros/recaps require active lineage |
| `ops_family_activation_evidence_is_complete()` | Slice 7: observational shadow evidence + fail-soft |
| `en_patterns_and_tts_slots_are_curated()` | Slice 5: ≥4 EN patterns + TTS slots per wire |
| `timing_family_replay_cases()` / `restart_rewind_replay_cases_are_complete()` | Slice 6: restart/rewind replay inventory |
| `timing_family_closeout_evidence()` / `timing_family_closeout_evidence_is_complete()` | Slice 7: coverage/latency/fail-soft closeout |
| `FAMILY_ROUTE["timing"]=shadow` + inventory `migration_status=shadow` | Slice 8: observational shadow activation (no live v2 speech) |
| Scope / polarity | `lap_sf` vs `sector`; `lap_complete` / `sector_split` / `sector_best` |

Detail: [timing-family-migration.md](../../v2.0.0/timing-family-migration.md). `FAMILY_ROUTE` pit/incident → shadow (observational). **Docs: `CONFIG.md` / `API.md` unchanged.**


## Ops family migration map (`contracts/ops_family_map.py`)

Slices 1–6 inventory for Wave G #276 (all `migration_status=shadow`; `OPS_WIRE_IDS` **13** = 6 pit + 3 incident + 1 flag + 3 closeout; Slice 5 adds taxonomy only; Slice 6 adds EN pattern/TTS curation — no new freeze wires):

| Helper | Role |
| --- | --- |
| `ops_family_rows()` | Closed rows for pit + incident/aftermath/recovery + `SESSION_FLAG` + closeout wires |
| `migration_status_by_wire_id()` | Coverage-matrix companion |
| `pit_cycle_phase_order_is_monotonic()` | Slice 1 AC: entry→service→exit→outcome |
| `pit_cycle_stories_have_explicit_terminals()` | Slice 1 AC: exit/outcome terminals + invalidate reasons |
| `incident_cycle_phase_order_is_monotonic()` | Slice 2 AC: event→aftermath→recovery |
| `incident_stories_have_explicit_terminals()` | Slice 2 AC: only `BACK_UNDER_WAY` terminal + invalidate reasons |
| `incident_branch_beats_are_documented()` | Slice 2 AC: `INCIDENT` primary `incident.off_track` + branch `incident.unclassified` |
| `session_flag_branch_beats_are_documented()` | Slice 3 AC: `SESSION_FLAG` primary `session.flag.yellow` + branches green/checkered; checkered ≠ hero finish / session wrap |
| `session_wrap_branch_beats_are_documented()` | Slice 4 AC: `SESSION_WRAP` primary `session.wrap.practice` + qualifying/race branches |
| `closeout_stories_are_separated()` | Slice 4 AC: checkered clock ≠ hero finish ≠ session wrap (scopes/families/tapes/notes) |
| `unknown_tow_teleport_outcomes_are_defined()` | Slice 5 AC: unknown/tow/teleport taxonomy + `hero_teleport` invalidate + terminal `unknown_*_explicit` + tow/teleport on aftermath/recovery |

**Slice 2 wires:** `INCIDENT` (`IncidentEmitter` + `incident_race_event_to_envelope`); `INCIDENT_AFTERMATH` / `BACK_UNDER_WAY` (`IncidentAftermathFsm`, FSM direct).

**Slice 3 wire:** `SESSION_FLAG` (`SessionFlagFsm` emitter+adapter; scope `flag_control`; policy `critical` / 45s; tape `race.control.flag`; family `session.flag`).

**Slice 4 wires:** `SESSION_CHECKERED` (`LifecycleTriggerBank`; scope `session_checkered`; family `session.flag`; tape `race.control.flag`; critical/45s); `FINISH` (`LifecycleTriggerBank`; scope `hero_finish`; family `session.finish`; tape `race.session.finish`; critical/45s); `SESSION_WRAP` (`StreamNarrativeFsm`; scope `session_wrap`; family `session.wrap`; tape `session.lifecycle`; result/30s; branch beats practice|qualifying|race). Flag checkered *branch* stays on `SESSION_FLAG`.

**Slice 5 taxonomy:** `OPS_UNKNOWN_OUTCOME_REASON_IDS` (incl. `unknown_exit_explicit` + prior `unknown_*_explicit`); `OPS_TOW_OUTCOME_REASON_IDS` (`hero_towing`, `tow_keeps_stalled`, `tow_blocks_recovery`); `OPS_TELEPORT_OUTCOME_REASON_IDS` (`hero_teleport`, `esc_teleport`, `teleport_invalidates_motion`). Every ops wire invalidates on `hero_teleport`; terminals include an `unknown_*_explicit` reason (`PIT_EXIT` → `unknown_exit_explicit`); `INCIDENT_AFTERMATH` / `BACK_UNDER_WAY` encode tow (+ recovery teleport) invalidation with notes that forbid invention.

Detail: [ops-family-migration.md](../../v2.0.0/ops-family-migration.md). `FAMILY_ROUTE` pit/incident → shadow (observational). **Docs: CONFIG.md / API.md unchanged.**



## Context family migration map (`contracts/context_family_map.py`)

Slices 1–2 inventory for Wave G #277 (all `migration_status=legacy`; `CONTEXT_WIRE_IDS` **5** = session leftovers **4** + filler **1** `PARADE_PAD`):

| Helper | Role |
| --- | --- |
| `context_family_rows()` | Closed rows for session leftovers + `PARADE_PAD` |
| `context_session_phase_order_is_monotonic()` | Slice 1: stream_start → preview → enter_car → final_lap |
| `enter_car_branch_beats_are_documented()` | Stage-routed enter-car beats |
| `context_session_stories_have_explicit_invalidation()` | Invalidate (+ FINAL_LAP terminal) |
| `owned_elsewhere_session_wires_are_documented()` | Intros/wrap/finish stay on timing/ops maps |
| `filler_beats_are_documented()` | Slice 2: parade wire + beat-only filler set |
| `filler_may_resolve_to_silence()` | Slice 2 AC: filler may yield silence |

Beat-only fillers (no freeze wire): `filler.out_lap`, `filler.in_lap`, `filler.garage`, `filler.lobby`, `filler.quiet_track`.

Detail: [context-family-migration.md](../../v2.0.0/context-family-migration.md). No `FAMILY_ROUTE` flip. **Docs: CONFIG.md / API.md / COMMENTARY_ENGINE.md unchanged.**

## Race-outcome migration map (`contracts/race_outcome_family_map.py`)

Slice 3 inventory + story/TTL + EN pattern curation for Wave G #274 (creatable rows `shadow`; alias `OVERTAKEN` `legacy`):

| Helper | Role |
| --- | --- |
| `race_outcome_family_rows()` | Closed rows for pass/gain/loss/leader/finish + `OVERTAKEN` alias |
| `migration_status_by_wire_id()` | Coverage-matrix companion (migrated/legacy recording) |
| Polarity tests | gain≠loss; passer→passed; alias not creatable |
| Story/TTL fields | `correlation_kind` / bindings / closing routes / fallback / adapter prefix; beat role + policy TTL |
| EN pattern fields | `en_pattern_ids` / `en_claim_surfaces` / `en_forbidden_tokens` (catalog-backed; no machine hash rewrite) |

Detail: [race-outcome-migration.md](../../v2.0.0/race-outcome-migration.md). `FAMILY_ROUTE` position/session → shadow observation only. **Docs: `CONFIG.md` / `API.md` unchanged.**

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
| `fact_capacity_evicted` | `false` | latched when FactView `historyComplete=false` or `note_fact_capacity("fact_capacity_evicted")`; cleared on `narrative_run_opened` only |
| `fact_capacity_exhausted` | `false` | latched via `note_fact_capacity("fact_capacity_exhausted")`; cleared when publishable FactView admitted or on `narrative_run_opened` |
| `detector_disabled` | `()` | `_detector_disabled_snapshot()` → `DetectorBank.disabled_for_status()` when bank injected; else empty |

`history_complete` on `RuntimeStatus` updates from FactView `historyComplete` when present; once eviction is latched, prior loss cannot be reconstructed within the run (`history_complete` stays `false` even if a later view reports `true`). **`note_fact_capacity(*diagnostics)`** — library hook for upstream FactLedger wiring when FactView cannot carry diagnostics; `"fact_capacity_exhausted"` also sets eviction. **`narrative_run_opened`** clears both capacity latches and resets `history_complete=true` before ingesting that batch's FactView. Optional `NarrativeRuntime(detector_bank=...)`; without bank, ingress keeps `components.detectors.disabled: []`. Live counts feat `d13d6bd`; capacity health feat — branch `cursor/fact-health-273-cad3` ([§ fact-health](../inflight/README.md#273-fact-health-continuation-slice-lookup)).

## Loop heartbeats (`events/narrative_runtime.py`, `events/narrative_ingress.py`)

`RuntimeStatus` + reducer state track actor loop observability for `GET /api/commentary/runtime` `loop` block:

| Field | Default | Update |
| --- | --- | --- |
| `loop_active` | `false` | `true` while `NarrativeRuntime.run()` owns the actor (`_run_active`; feat `c2e02d4`) |
| `loop_last_reduce_mono_ms` | `null` | monotonic ms after each `reduce_next()` (feat `952cc1d`) |
| `loop_reduce_count` | `0` | monotonic count of completed `reduce_next()` calls (feat `952cc1d`) |
| `loop_supervisors` | `{}` | snapshots from registered providers via `attach_supervisor_heartbeat(name, provider)` (feat `952cc1d`) |

`project_runtime_status` emits `loop.{active, lastReduceMonoMs, reduceCount, supervisors}` (camelCase supervisor keys). Each supervisor payload mirrors `WorkerSupervisor.status_snapshot`: `{running, restarts, lastError}`. Race cutover attaches `narrativeRuntime` + `narrativeShadow` in `race/runtime.py`. Library without attach → `supervisors: {}`. Provider exceptions are skipped fail-soft.

## OpportunityQueue `byTapeChannel` projection (`events/opportunity_queue.py`, `events/narrative_ingress.py`)

- **`OpportunityQueue.tape_channel_status_counts()`** — maps internal `ChannelCounters` per `tape_channel` to HTTP six-counter rows (`spoken→accepted`, `consumed→started`), then **`project_by_tape_channel_status`**: omit all-zero channels, sort channel id lexicographically, cap at **128** (`BY_TAPE_CHANNEL_STATUS_CAP`). Invalid/non-int counter values fail-soft (row dropped).
- **`_by_tape_channel_projection`** in `events/narrative_ingress.py` — reads `RuntimeStatus.by_tape_channel` and delegates to the same shared projector (feat `466c2f3`; live wiring feat `bdb9633`).
- **`cohort_funnel_rates(counters)`** — pure helper for offline/tuning ratios; **not** emitted on `GET /api/commentary/runtime`. Returns `{kickToAccepted, acceptedToQueued, selectedToStarted}` with `null` when the stage is N/A (`kickToAccepted` when `kick==0`; `acceptedToQueued` only for speakable accepted cohorts — visual-only ends after `accepted`; `selectedToStarted` when `selected==0`).
- **Operator visibility (#273):** `GET /api/commentary/runtime` → `/commentary` renders `byTapeChannel` cadence without parsing event names or enabling global DEBUG. NarrativeTape NDJSON (`[commentary.tape]`) must not flood INFO/WARN — volume is INI-gated only.
- **Golden:** `tests/fixtures/commentary_runtime/status_by_tape_channel.json` (feat `466c2f3`; in `tests/test_commentary_runtime_goldens.py` `REQUIRED_FIXTURES`).
- **Tests:** `tests/test_narrative_ingress.py` — `test_project_runtime_status_by_tape_channel_follows_opportunity_counters`, `test_by_tape_channel_projection_filters_zeros_sorts_and_caps`, `test_cohort_funnel_rates_omit_non_applicable_stages` (**3** rows). PR [#291](https://github.com/Buchtanen/ir-obs-switcher/pull/291) → base `codex/commentary-story-flow-spec`.

## Ingress projector (`events/narrative_ingress.py`)

- `project_runtime_status(RuntimeStatus)` — `language`: fixní `"en"`; `speech`: plný tvar `{state, sourceKind, utteranceId, beatId, opportunityId, backend, backendGeneration, dispatchedAtMonoMs, acceptedAtMonoMs, lastTerminal}`; `components`: bounded `{llm, tts, tape, detectors, facts}` z `RuntimeStatus.component_health` / `tape_status` (tape default `disabled`, drops `0`); `components.llm` / `components.tts` via `_llm_component_projection` / `_tts_component_projection` — without attached component: stub defaults (feat `3670502`) but `configGeneration` reads CONFIG_UPDATE `desiredGeneration` when ledger present; with attached warmed component (feat `60565ae`): live `generation`/`model`/`residencyEvidence`/`status`/`reason`; tts speech-lane `backend`/`backendGeneration`; both `configGeneration` from ledger; `lastAttempt` `null` until first admitted Qwen completes (warmup/authored ignored; feat `19887aa` — `{requestId, outcome, ttfbMs, ttftMs, totalMs, reducerLagMs, terminalReason}`); `components.facts` — live `viewRevision`/`active`/`historicalSummaries`/`historyComplete` from `RuntimeStatus` fact fields (feat `d13d6bd`; disabled-library zeros feat `03c34b2`); capacity health projects `status`/`reason` (`ready`/`null` | `degraded`/`fact_capacity_evicted` | `unavailable`/`fact_capacity_exhausted`); projected `historyComplete` is `history_complete and not fact_capacity_evicted` (feat — branch `cursor/fact-health-273-cad3`); `components.detectors` — `status=ready`, `reason=null`, live sorted `disabled` `{id, reason}` rows from `RuntimeStatus.detector_disabled` when `DetectorBank` injected (feat `d13d6bd`; empty without bank); `loop` — `{active, lastReduceMonoMs, reduceCount, supervisors}` from loop heartbeat fields (active feat `c2e02d4`; reduce/supervisors feat `952cc1d`); plus #273 bloky `catalog`/`config`/`episodes`/`byTapeChannel`: `catalog` — packaged hash (`_packaged_catalog_projection`); `config` — live CONFIG_UPDATE ledger přes `_config_projection` (`RuntimeStatus.config_ledger`; invalid/cleared → `_unloaded_config_projection`); `episodes` — live counts z injected `EpisodeRegistry` přes `_episodes_projection` (`RuntimeStatus.episode_counts`; no registry → `_empty_episodes_projection`); `byTapeChannel` — live counters z injected `OpportunityQueue.tape_channel_status_counts()` přes `_by_tape_channel_projection` (empty when no queue/counters); `queues.opportunities` (depth 0, `OPPORTUNITY_CAPACITY`); plus `timeline` (identity + `sessionPlan`/`sessionRef`/`occurrenceId`/`lineageId`/`stage` all-or-none — null idle/disabled/incomplete context, live after valid `APPLY_CONTEXT_BATCH` via `_timeline_session_identity`; satisfies `session_identity_all_or_none`), `queues.mailbox`, recovery, diagnostics. Live wiring feat `bdb9633`; stub slice feat `03c34b2`; live llm residency feat `60565ae`; live detectors/facts feat `d13d6bd`.
- `project_commentary_health_component(status=None)` → `{status, reason}` pro `GET /health` (jen top-level status/reason, ne speech/components). `reason` je první položka z `RuntimeStatus.reason_codes` (closed enum `HealthCommentarySummary.reason` v `api-contracts.schema.json`); freeze-registry kódy zahrnují `mailbox_recovery`, `mailbox_overloaded`, `mailbox_evicted_update`, `deadline_admission_skipped`, `admission_timeout`, `history_incomplete`, `component_unavailable`, … (feat `cffaab1`). `project_runtime_status` emituje plný `diagnostics.reasonCodes`. Jediný ingress helper, který sahá do `server/api.py`. **Not** exported z `events/__init__.py`.

## Decision ring (`events/narrative_decision_projection.py`, `events/narrative_runtime.py`)

- `build_runtime_decision_entry`, `project_runtime_decisions` — pure projection helpers; **not** exported z `events/__init__.py`.
- `NarrativeRuntime`: bounded deque `DECISION_CAPACITY=128`; každý `_consult_director` append (`selected` / `silence` / `replaced`); `decisions(limit)` newest-first.

## Validate projection (`events/narrative_validate_projection.py`)

- `project_validate_response` — offline `ValidateRequest`→`ValidateResponse` (`commentary-runtime/2`); exact top-level keys only (`schemaVersion`/`text`/`beatId`/`evaluationAtMonoMs`/`actorBindings`/`factBindings`); `factBindings` via `AtomicFact.from_dict` + FactRegistry (incomplete/unknown/unregistered → `ContractViolation`/400); caller-supplied EN text + beat + bindings; nečte live runtime. **Not** exported z `events/__init__.py`.
- HTTP mount: `POST /api/commentary/runtime/validate` + public `POST /api/commentary/validate` v `events/narrative_runtime_http.py` / `commentary/http.py` (200 i když `valid=false`; 400 malformed; cutover feat `f2c1f1b`).

## Manual admission latch (`events/narrative_manual_latch.py`)

- `ManualAdmissionLatch` — one-shot rendezvous `pending | actor_claimed | caller_abandoned`; `ADMISSION_TIMEOUT_S=1.0`. **Not** exported z `events/__init__.py`.
- `NarrativeRuntime.register_manual_latch` / `_pop_manual_latch` — process-local map keyed by `requestId`.

## Legacy↔v2 shadow compare (`events/legacy_v2_shadow_compare.py`) — #272 branch-only (**CLOSED**)

Observation-only event / episode / director decision compare behind a private in-module route table. Adapts `RaceState` and `EventEnvelope` into v2 fingerprint projections. **Not** exported from `events/__init__.py`. Temporary branch harness — must not survive the final v2 cutover PR (`docs/v2.0.0/final-pr-exclusion-manifest.md`).

| Symbol | Role |
| --- | --- |
| `FAMILY_ROUTE` | Private dev map (`lap` → `shadow`; unmigrated families → `legacy`) — **not** CONFIG/API |
| `route_for_family(family)` | Lookup with `legacy` default |
| `adapt_race_state_to_v2` / `adapt_event_envelope_to_v2` | Immutable RaceState/EventEnvelope projections |
| `DivergenceRecord` | Frozen row: `family`, `aspect` (`event`\|`episode`\|`director`), `reason`, legacy/v2 fingerprints |
| `ShadowCompareResult` | `matched`, `divergences`, `route`, always-empty `speech_effects`; optional `latency_ms`, `evidence` |
| `compare_event_decisions` / `compare_episode_decisions` / `compare_director_decisions` | Per-aspect legacy↔v2 fingerprint compare |
| `observe_family_safely` | Fail-soft wrapper — v2 failure/timeout/cancel never crashes callers |
| `REMOVAL_MANIFEST_ENTRIES` | Paths/symbols that must be absent from final master cutover diff |

Never admits speech, never mutates mailbox/TTS, never owns upstream timeline/fact truth. Race/commentary **not** wired.

**Tests:** `tests/test_legacy_v2_shadow_compare.py` (**16** feat `6cfce0c`; prior first slice **5** feat `f72eb8c`). **Docs: `API.md` / `CONFIG.md` unchanged (not public); harness listed in `final-pr-exclusion-manifest.md`.**

## Coalesce policy (`contracts/coalesce_policy.py`)

- `COALESCE_FIELD_PATHS` — closed allowlist health + deadline kinds (`LONG_SILENCE_ELAPSED`, `VALIDITY_DEADLINE_ELAPSED`, `REALIZATION_DEADLINE_ELAPSED`, `TAPE_HEALTH_CHANGED`, `COMPONENT_HEALTH_CHANGED`); `APPLY_CONTEXT_BATCH` intentionally absent.
- `coalesce_key_for(kind, token=, payload=)` — shared resolver for mailbox admission, `NarrativeCommand.coalesce_key`, and `docs/v2.0.0/machine/build_actor_transition_model.py` (feat `dd64047`).
- Tests: `tests/test_coalesce_policy.py` (**3**). **Docs: `API.md` / `CONFIG.md` unchanged.**

## Fact-only wait + playback callbacks (`events/narrative_runtime.py`)

- **Pure FactView:** `APPLY_CONTEXT_BATCH` without `planning_impulse` → `director_skipped_pure_fact` + `fact_only_wait`; cancels building (`building_invalidated`) but does not open a planning cycle or dispatch a plan (feat `dd64047`).
- **Terminal director policy:** `_begin_speech_projection` sets `_terminal_director_policy` — narrative `replan_if_enabled`, manual `never`; truth/lifecycle cancel forces `never`.
- **Playback accept:** pauses audience silence (`silence_deadline_paused`); narrative vs manual diverge (`narrative_playback_accepted` / `manual_playback_accepted`).
- **Terminal idle:** `_rearm_silence_deadline`; narrative `SPEECH_*` terminals → `director_reentry_eligible` + `narrative_callback_branch`; manual → `manual_callback_branch`; other → `callback_no_director` (feat `dd64047`).
- Tests: `tests/test_narrative_runtime.py` — `test_fact_only_wait_cancels_building_without_replan`, `test_narrative_callback_branch_rearms_silence_and_allows_director`, `test_manual_callback_branch_rearms_silence_without_director` (**144** total; was **141**). **Docs: `API.md` / `CONFIG.md` unchanged.**

## Cancel-on-disable / transition / config-boundary (`events/narrative_runtime.py`)

- **Occurrence/stream transition:** while `narrativeRunActive` stays true, timeline transition on `APPLY_CONTEXT_BATCH` cancels building → `idle`; effects `building_cancelled`, `effect:cancel_realization`, `effect:cancel_realization_deadline`, `effect:cancel_silence_deadline`, `effect:cancel_validity_deadline`, `effect:arm_silence_deadline`, `effect:arm_validity_deadline`; bumps `_silence_generation` / `_validity_generation` so stale `LONG_SILENCE_ELAPSED` / `VALIDITY_DEADLINE_ELAPSED` → `ignored_stale_or_inapplicable` with `stale_silence_generation` / `stale_validity_generation`. No `narrative_run_closed` on non-disable transitions.
- **Explicit disable:** `narrative_run_closed`, `building_cancelled_on_disable`, `effect:cancel_realization`, `effect:cancel_silence_deadline`, `effect:cancel_validity_deadline`; when `tape_effect` set → `effect:flush_tape`.
- **`CONFIG_UPDATE` boundary:** rearms silence/validity deadlines without lane mutate; following timeline transition cancels building (`building_cancelled` + `effect:cancel_realization`).
- Tests: `tests/test_narrative_runtime.py` — `test_timeline_transition_cancels_building_and_stale_deadline_generations`, `test_disable_with_tape_effect_flushes_tape`, `test_config_then_timeline_transition_cancels_building` (**149** total; was **146**). `tests/test_narrative_tape_bridge.py` — `test_open_writer_flush_effect_closes_on_disable` (**4** total; was **3**). **Docs: `API.md` / `CONFIG.md` / `README.md` unchanged** (internal reducer effects; test `d9089a1`).

## Ordering+races verification (`events/narrative_runtime.py`)

Library pytest evidence mapped to frozen `actor-transition-goldens.json` ordering scenarios and completion race traces (test `5f4eb61`):

- **Ordering:** `same_time_external_before_callback` — external callback wins ordering when co-timed with internal playback callback; `same_time_callback_before_reset` — internal playback callback wins over stream reset at same step.
- **Completion races:** frozen `deadline_before_result`/`reset_before_result`; library-only `config_generation_then_completion`/`validity_expiry_before_completion` — stale completions ignored; one terminal attempt per race.
- **Matrix:** `test_actor_transition_matrix_row` still covers all **85** lane×command disposition rows separately.
- Tests: six rows in `tests/test_narrative_runtime.py` (**155** total; was **149**). **Docs: `API.md` / `CONFIG.md` / `README.md` unchanged** (tests-only).

## Actor command + transition matrices (`actor-transition-contract.md`)

Docs `9b0c860` embeds the frozen **17**-command inventory and all **85** lane×command disposition rows into [`docs/v2.0.0/actor-transition-contract.md`](../../v2.0.0/actor-transition-contract.md) (human-readable mirror of `machine/actor-transition-model.json`; pytest sync unchanged via `test_actor_transition_matrix_row`). **Docs: `API.md` / `CONFIG.md` / `README.md` unchanged** (branch contract only).

## Upstream snapshot immutability (`events/narrative_runtime.py`, `logic/partition_context_batches.py`)

Library pytest evidence that `NarrativeRuntime` projects frozen upstream truth without back-mutation or owning upstream engines (test `78a1aeb`):

- **Context batches:** `partition_context_batches` + `APPLY_CONTEXT_BATCH` preserve immutable `StreamTimeline`/`FactView` snapshots; caller mutation after partition cannot rewrite the admitted batch; property accessors return fresh dicts (mutating them does not rewrite actor pointers).
- **DetectorBank:** optional `NarrativeRuntime(detector_bank=...)` reads `DetectorBank.disabled_for_status()` for status projection only — never calls `DetectorBank.step`.
- **No upstream ownership:** `NarrativeRuntime` does not accept or own `StreamTimeline` / `FeatureEngine`; `FeatureFrame` remains frozen upstream output.
- Tests: `tests/test_narrative_runtime.py` — `test_runtime_does_not_back_mutate_upstream_timeline_or_fact_snapshots`, `test_runtime_reads_detector_bank_status_without_stepping_or_owning_engines` (**157** total; was **155**). **Docs: `API.md` / `CONFIG.md` / `README.md` unchanged** (tests-only).

## Manual speak (`events/narrative_runtime.py`, `events/narrative_runtime_http.py`)

- `ManualSpeakOutcome`, `NarrativeRuntime.try_manual_speak` — alokuje latch, admitne `MANUAL_SPEAK_REQUEST`, awaitne resolution (default 1s; `timeout_s` / `reduce_inline` kwargs). Když actor loop neběží, sync inline reduce; jinak `_on_manual` claimne latch před lane mutate. Timeout → `admission_timeout`; abandoned latch zůstává registrovaný (`manual_abandoned`).
- HTTP body freeze (#273 continuation, branch `cursor/manual-speak-body-273-cad3`): `_parse_manual_speak_body` in `events/narrative_runtime_http.py` accepts **exact keys** `schemaVersion`, `text`, `language` only (`language` must be `en`). Unknown fields (e.g. `force`, backend/voice overrides) → **400** `invalid_request`. `text` must be normalized Unicode length 1–400 with no control characters → otherwise **422** `validation_failed`. **202** response keys: `schemaVersion`, `accepted`, `requestId`, `admittedState` — `admittedState` is exactly `committed` after atomic dispatch. Public `POST /api/commentary/speak` shares the same handler (feat `f2c1f1b` cutover); `/api/commentary/runtime/speak` remains an alias. Detail: [§ manual speak body](../inflight/README.md#273-manual-speak-body-slice-lookup) · `API.md`.
- HTTP mount: `POST /api/commentary/runtime/speak` + public `POST /api/commentary/speak` (202 / 409 / 422 / 503 incl. `admission_timeout`).
- Manual speak **nikdy** nezapisuje do `ExposureStore` (`exposure_skipped_manual`); manual playback uses `manual_callback_branch` (no director re-entry — feat `dd64047`).

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
- Status_ready library: `tests/fixtures/commentary_runtime/status_ready_library.json, exact machine `status_ready.json` / `status_unknown_invalid_plan.json`, `status_component_facts_evicted.json`` (`catalog`, `config`, `episodes`, `byTapeChannel`, `queues.opportunities`, `components.detectors`/`facts` disabled-library zeros)
- ByTapeChannel live counters: `tests/fixtures/commentary_runtime/status_by_tape_channel.json` (feat `466c2f3`)
- Speech idle: `tests/fixtures/commentary_runtime/status_speech_idle.json` (`language`, idle `speech`, bounded `components` incl. schema-complete llm/tts)
- Components llm/tts: `tests/fixtures/commentary_runtime/status_components_llm_tts.json`
- Decisions selected: `tests/fixtures/commentary_runtime/decisions_selected.json`
- Validate: `validate_request.json`, `validate_supported.json`, `validate_rejected.json`
- Speak: `speak_request.json`, `speak_accepted.json`, `error_admission_timeout.json`

## Testy

`tests/test_narrative_ingress.py` (**52** = prior **49** + **3** byTapeChannel funnel bounds rows feat `466c2f3`). `tests/test_narrative_runtime.py` (**157** = prior **155** + **2** upstream immutability rows test `78a1aeb`). `tests/test_narrative_tape_bridge.py` (**4** = prior **3** + **1** disable flush row test `d9089a1`). `tests/test_coalesce_policy.py` (**3** feat `dd64047`). `tests/test_actor_transition_goldens.py` (**32** = **13** `raceTraces` + **10** `overflowScenarios` + **2** `orderingScenarios` + sync/assert rows + **2** runtime race rows + **3** overflow library evidence rows test `f465bfd`). Runtime+goldens **189** (= **157** + **32**). Core subset **244** (= **157** + **52** + **32** + **3**). `tests/test_narrative_runtime_http.py` (**18** incl. disabled-subset loop asserts + **2** public-path cutover rows + **2** manual-speak body/admittedState rows — branch `cursor/manual-speak-body-273-cad3`). `tests/test_commentary_http.py` (**9** incl. **2** operator-page contract rows). Ingress+http **70** (= **52** ingress + **18** http).

## Closed (#284) / still deferred (#273 remainder)

Full #273 schema: master cutover only (human kick). Loop liveness landed feat `c2e02d4` (`loop.active`). Loop supervisor heartbeats landed feat `952cc1d` (`loop.lastReduceMonoMs`, `loop.reduceCount`, `loop.supervisors`). Live llm/tts transport/residency projection landed feat `60565ae`. Live llm `lastAttempt` projection landed feat `19887aa`. Live detectors/facts status projection landed feat `d13d6bd`. ExposureStore sole-writer landed feat `c6ffbe3` (`NarrativeRuntime._record_exposure` on playback accept when composed). Legacy validate/speak public-path cutover landed (feat `f2c1f1b`); thin validate/speak slice landed (feat SHA `65651bc`); thin `ManualAdmissionLatch` slice landed (feat SHA `ca0f2f6`); status_ready stub slice landed (feat SHA `03c34b2`); live catalog/config/episodes/byTapeChannel status projection landed (feat SHA `bdb9633`); bounded byTapeChannel projection + cohort funnel rates helper landed (feat SHA `466c2f3`; PR [#291](https://github.com/Buchtanen/ir-obs-switcher/pull/291)); thin components llm/tts schema stubs landed (feat SHA `3670502`); timeline session identity null stubs landed (feat SHA `f58c992`); live timeline session identity wiring landed (feat SHA `ccd0697`). EventSubscription full replace landed feat `44dab2f` (`NarrativeShadowConsumer(..., legacy_stream_handler=None)`; no SessionReset/ConfigUpdate/batch mirror into `CommentaryConsumer`; sole ingress shadow admit → `NarrativeMailbox`; `CommentaryConsumer` TTS sink/status/filler with `idle_speech_enabled=False`, `_commentary_subscription=None`; `tests/test_narrative_fanout_cutover.py` **8** cutover rows). Reducer replay closure landed feat `b86a336` (`command_from_dict` rebuilds `REALIZATION_SUCCEEDED`/`FAILED`; optional `runtime_factory` on capture/replay/journal; journal replay reproduces `director_selected` + committed lane when recorded realization supplied; `tests/test_narrative_reducer_replay.py` **5** + `tests/test_narrative_command_journal.py` **9** = **14** passed). Actor-transition model-tests landed test `fe70f2a` (`tests/test_actor_transition_goldens.py` **32** against frozen `docs/v2.0.0/machine/actor-transition-goldens.json` — **13** `raceTraces`, **10** `overflowScenarios`, **2** `orderingScenarios`, `pairCoverage`↔`transitionMatrix` sync (**85**), on-disk↔builder sync, plus **2** `NarrativeRuntime` race evidence rows + **3** overflow library evidence rows test `f465bfd`). Health/API reason-code schema landed feat `cffaab1` (`_reason_codes()` mailbox/admission codes; `/health` `commentary.reason`; `diagnostics.reasonCodes`; `API.md` + `CONFIG.md` + `api-contracts.schema.json` updated in feat commit).

Fact-only wait / coalesce / callback branches landed feat `dd64047` (`contracts/coalesce_policy.py`; pure FactView `fact_only_wait`; narrative/manual playback+terminal callback branches; silence pause/rearm).

Live #270 verify-frame attachment on authored/template realization paths landed feat `a1ba998` (`events/narrative_verify_frame.py` side-stash; `realize_authored_speech` / `template_speech`; `SpeechDraft.verify_frame`; effect `verify_frame_attached_live`; skip-no-frame mainly for Qwen/unframed; `tests/test_narrative_realization_bridge.py` **5**).

Overflow linearization / deadline-skip / quarantine model-tests landed test `f465bfd` (`tests/test_actor_transition_goldens.py` — `test_narrative_runtime_manual_full_partition_linearization`, `test_narrative_runtime_deadline_admission_skipped_under_overflow`, `test_narrative_runtime_quarantined_cannot_admit_under_overflow`; goldens **32**).

Cancel-on-disable / transition / config-boundary landed test `d9089a1` (`tests/test_narrative_runtime.py` — `test_timeline_transition_cancels_building_and_stale_deadline_generations`, `test_disable_with_tape_effect_flushes_tape`, `test_config_then_timeline_transition_cancels_building`; `tests/test_narrative_tape_bridge.py` — `test_open_writer_flush_effect_closes_on_disable`; runtime **149**, tape bridge **4**, core subset **229**).

Ordering+races verification landed test `5f4eb61` (`tests/test_narrative_runtime.py` — six library race rows: `test_narrative_runtime_same_time_external_before_callback_order`, `test_narrative_runtime_same_time_callback_before_reset_order`, `test_narrative_runtime_deadline_before_result_race`, `test_narrative_runtime_reset_before_result_race`, `test_narrative_runtime_config_generation_then_completion_race`, `test_narrative_runtime_validity_expiry_before_completion_race`; runtime **155**, core subset **235**, related **331**).

AC5 actor command + transition matrices embed landed docs `9b0c860` (`docs/v2.0.0/actor-transition-contract.md` — complete **17**-command inventory + **85** lane×command disposition rows; library-only completion races clarified).

Upstream snapshot immutability landed test `78a1aeb` (`tests/test_narrative_runtime.py` — `test_runtime_does_not_back_mutate_upstream_timeline_or_fact_snapshots`, `test_runtime_reads_detector_bank_status_without_stepping_or_owning_engines`; runtime **157**, core subset **237**, related **333**).

**#284 CLOSED** (**41/41** AC — process TDD AC via human-accepted TDD-exception; human close gate satisfied). PR [#289](https://github.com/Buchtanen/ir-obs-switcher/pull/289) **merged** @ `77452a9` → `codex/commentary-story-flow-spec`; **no master merge**.

**#272 CLOSED** (AC **4/4**) — complete harness feat `6cfce0c` (prior first slice `f72eb8c`): observational legacy↔v2 shadow compare with event/episode/director aspects, RaceState/EventEnvelope adapters, fail-soft `observe_family_safely`, removal manifest (`events/legacy_v2_shadow_compare.py`; `tests/test_legacy_v2_shadow_compare.py` **16**). Stack PR [#290](https://github.com/Buchtanen/ir-obs-switcher/pull/290) → base `codex/commentary-story-flow-spec`. **Docs: `CONFIG.md` none; `API.md` none.**

Next work: v2 integration only (#273 master cutover, `planningCycleId` race tape wire, deeper tape-run wiring — **not** #272).

**TDD-exception (process AC only, historical):** Add focused pytest/pytest-asyncio tests before behavior code. **Reason:** behavior already landed in prior slices; cannot honestly claim tests-first retrospectively. **Alternative verification:** existing `NarrativeRuntime` + actor-transition matrix/ordering/races/immutability pytest evidence. **Risk:** process dilution — scoped to this historical checkbox only.

## Related

[server](server.md), [API.md](../../../API.md), [implementation-handover](../../v2.0.0/implementation-handover.md).

- #273: `project_runtime_status` sets `components.tape.reason=capture_unavailable` when `tape_status=unavailable`; `components.tape` exposes live `{size, drops, dropsByPriority, purposeCounts, path}` from `RuntimeStatus` tape counter fields (injected `NarrativeTapeWriter.runtime_status_snapshot()` when composed; zero/empty stubs otherwise); `components.detectors.disabled` sorted by id.
