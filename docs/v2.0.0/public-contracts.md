# v2.0.0 commentary public contract freeze

**Status:** design-freeze candidate owned by issues #238 and #273

This branch-only artifact freezes the public configuration and HTTP shape before parser or handler implementation. Initial numeric values are estimates permitted by the design; their types, units, ranges and reload boundaries are contract, while later value tuning inside those ranges is not an architecture change.

## Configuration

Unknown keys under `commentary.*` are errors. A commentary configuration error sets automatic commentary health to `disabled_invalid_config`, closes its active narrative run, and installs no new config generation; it does not by itself cancel manual TTS or make a currently ready last-valid effective backend unusable, and it does not fail scene switching, OBS control or the main race loop. All durations use monotonic time at runtime.

INI booleans are exactly `true|false`; integers/floats use finite base-10 notation with `.` and no exponent; enums/IDs are case-sensitive as listed. Set values are comma-separated IDs with whitespace trimmed, stable input order ignored and duplicates rejected. Empty string is allowed only where the table explicitly uses an empty default. A next-stream change made during an active stream is validated and reported in `config.pendingChanges` but is not partly applied. It requires a new narrative stream boundary, not a service restart.

### Root and director

| Key | Type | Default | Allowed | Unit | Apply boundary |
| --- | --- | --- | --- | --- | --- |
| `commentary.enabled` | bool | `false` | bool | — | `command` |
| `commentary.max_utterance_s` | float | `14.0` | 2–30 | seconds | `next_plan_or_manual` |
| `commentary.driver_name` | string | empty | 0–128 UTF-8 chars | — | `next_stream` |
| `commentary.driver_nickname` | string | empty | 0–64 UTF-8 chars | — | `next_stream` |
| `commentary.tone_source` | enum | `none` | `none`, `heart_rate` | — | `next_beat_plan` |
| `commentary.director.selection_threshold` | float | `35.0` | 0–100 | score | `next_director_pass` |
| `commentary.director.switch_margin` | float | `8.0` | 0–50 | score | `next_director_pass` |
| `commentary.director.global_min_interval_s` | float | `4.0` | 0–30 | seconds | `next_director_pass` |
| `commentary.director.long_silence_s` | float | `33.0` | 10–300 | seconds | `next_silence_deadline` |
| `commentary.director.opportunity_capacity` | int | `128` | 16–512 | opportunities | `next_stream` |
| `commentary.director.active_episode_capacity` | int | `64` | 8–256 | episodes | `next_stream` |
| `commentary.director.resolved_episode_capacity` | int | `256` | 32–2048 | summaries | `next_stream` |
| `commentary.director.decision_capacity` | int | `128` | 16–1000 | decisions | `next_stream` |
| `commentary.director.max_consecutive_story_beats` | int | `3` | 1–8 | beats | `next_director_pass` |

Enabling commentary during an already active OBS stream creates a new narrative epoch with `start_reason=enabled_mid_stream` and `history_complete=false`; it does not claim pre-enable history. Disabling cancels unaccepted generation and future automatic planning immediately. Already accepted narrative playback receives a bounded stop request and records its actual terminal state; an explicitly requested manual audio test is independent and continues.

The effective consecutive-beat limit is the minimum of the public director value and the selected StoryDefinition limit. Story cadence uses the maximum of global, policy-profile and StoryDefinition minima. These combinations only tighten catalog safety; config cannot make a story looser than its frozen catalog bound.

NarrativeMailbox capacity is deliberately not public config in v2. Its fixed `64 = 56 ordinary + 7 protected + 1 emergency` admission invariant is part of the actor safety contract; changing it requires an actor-contract/schema review rather than live tuning.

### LLM and TTS

| Key | Type | Default | Allowed | Unit | Apply boundary |
| --- | --- | --- | --- | --- | --- |
| `commentary.llm.enabled` | bool | `false` | bool | — | `next_beat_plan` |
| `commentary.llm.base_url` | URL | `http://127.0.0.1:11434/v1` | local/LAN HTTP(S) policy below | — | `next_beat_plan` |
| `commentary.llm.model` | string | `qwen3:4b-instruct-2507-q4_K_M` | 1–128 chars | — | `next_beat_plan`; starts preflight at acceptance |
| `commentary.llm.timeout_s` | float | `1.5` | 0.2–10 | monotonic seconds | `next_request` |
| `commentary.llm.max_tokens` | int | `96` | 32–256 | tokens | `next_request` |
| `commentary.llm.warmup` | bool | `true` | bool | — | `next_beat_plan`; controls preflight started at acceptance |
| `commentary.llm.max_profile` | enum | `tight` | `tight`, `balanced`, `loose` | — | `next_beat_plan`; family verifier may impose lower cap |
| `commentary.tts.backend` | enum | `auto` | `auto`, `sapi`, `espeak`, `supertonic` | — | `next_utterance` |
| `commentary.tts.voice` | string | empty | 0–128 chars/backend-valid | — | `next_utterance` |
| `commentary.tts.rate` | int | `0` | -10–10 | SAPI-style steps | `next_utterance` |
| `commentary.tts.steps` | int | `6` | 5–12 | inference steps | `next_utterance` |
| `commentary.tts.start_timeout_s` | float | `5.0` | 0.5–30 | monotonic seconds | `next_utterance` |
| `commentary.tts.stop_timeout_s` | float | `1.0` | 0.1–5 | monotonic seconds | `next_cancellation` |
| `commentary.tts.audio_device` | string | empty | 0–256 chars | — | `next_utterance` |
| `commentary.tts.duck_input` | string | empty | 0–256 chars | — | `next_utterance` |
| `commentary.tts.duck_ratio` | float | `0.25` | 0–1 | original-volume fraction | `next_utterance` |
| `commentary.tts.duck_fade_ms` | int | `750` | 0–5000 | milliseconds | `next_utterance` |

`llm.enabled=false` means only beats whose catalog-selected realization mode is authored are eligible. An unavailable or rejected Qwen realization does not switch the same beat to authored mode; the attempt is discarded and the director chooses another eligible beat or silence. Profile ordering is exactly `tight < balanced < loose`; `llm.max_profile` is a ceiling and can never promote a catalog family.

`tts.backend=auto` resolves once per backend generation in the existing compatibility order `sapi` then `espeak`; SuperTonic remains explicit because loading it has material model/device cost. The resolved backend ID is snapshotted into each utterance/tape record. Once an utterance is dispatched, start/failure/timeout never falls through to another TTS backend for that text; recovery requires a new explicit backend generation/preflight, preventing duplicate late audio.

`llm.base_url` is accepted only when all of these conditions hold: scheme is `http` or `https`; userinfo, query and fragment are absent; port is in `1..65535`; path is empty, `/v1` or ends in `/v1` after slash normalization; and host is exactly `localhost` or an IP literal classified as loopback, RFC1918 private, IPv6 unique-local or link-local. Other DNS names and public IP addresses are rejected, so validation never performs DNS resolution and cannot be changed by DNS rebinding. The transport appends exactly `/chat/completions`. This is a new v2 validation requirement; the v1 scheme-only check is not sufficient evidence.

### Detectors and tape

| Key | Type | Default | Allowed | Unit | Apply boundary |
| --- | --- | --- | --- | --- | --- |
| `commentary.detectors.profile` | enum | `production` | `production`, `calibration` | — | `next_stream` |
| `commentary.detector.<id>.enabled` | bool | catalog value | bool; ID must be exported | — | `next_stream` |
| `commentary.detector.<id>.<parameter>` | catalog typed | catalog value | exported min/max and cross-field rules | catalog unit | `next_stream` |
| `commentary.tape.enabled` | bool | `false` | bool | — | `next_record` |
| `commentary.tape.channels` | enum set | `flow` | subset of `flow,llm_eval,detector_tuning` | — | `next_record` |
| `commentary.tape.detail` | enum | `normal` | `minimal`, `normal`, `full` | — | `next_record` |
| `commentary.tape.output_dir` | path | `recordings/commentary` | safe non-root path | — | `next_rotated_file` |
| `commentary.tape.rotate_mb` | int | `64` | 1–1024 | MiB | `next_record` |
| `commentary.tape.keep_files` | int | `8` | 1–100 | files | `next_rotation` |
| `commentary.tape.compress_rotated` | bool | `true` | bool | — | `next_rotation` |
| `commentary.tape.flush_interval_ms` | int | `500` | 50–5000 | milliseconds | `next_writer_deadline` |
| `commentary.tape.writer_capacity` | int | `4096` | 256–32768 | records | `next_stream` |
| `commentary.tape.shutdown_flush_timeout_s` | float | `2.0` | 0.1–10 | seconds | `next_shutdown` |
| `commentary.tape.flow.candidate_detail` | enum | `selected_and_rejected` | `selected`, `selected_and_rejected`, `all` | — | `next_record` |
| `commentary.tape.flow.tape_channel_allowlist` | string set | `*` | known channel IDs or `*` | — | `next_record` |
| `commentary.tape.llm_eval.capture_prompt` | enum | `hash` | `none`, `hash`, `full` | — | `next_request` |
| `commentary.tape.llm_eval.capture_completion` | bool | `true` | bool | — | `next_request` |
| `commentary.tape.detector_tuning.trigger_allowlist` | string set | empty | known detector IDs | — | `next_stream` |
| `commentary.tape.detector_tuning.negative_sample_interval_s` | float | `5.0` | 0.5–60 | seconds | `next_stream` |
| `commentary.tape.detector_tuning.near_threshold_margin` | float | `0.15` | 0–1 | normalized fraction | `next_stream` |
| `commentary.tape.detector_tuning.capture_input_windows` | bool | `true` | bool | — | `next_stream` |

`production` rejects any enabled detector with `tuning.required`. `calibration` may enable `experimental=true, tuning.required` only after writable recorder preflight. Losing required capture emits `CAPTURE_UNAVAILABLE` and disables only affected experimental detectors.

### Cross-field validation

- `active_episode_capacity <= resolved_episode_capacity`;
- `selection_threshold` and `switch_margin` are independent: the former gates eligibility and the latter gates replacement of a preferred equal-urgency successor;
- `switch_margin` is one director value in the v2 baseline; StoryDefinition and BeatDefinition cannot override it;
- detector relationships are validated only when declared by that detector schema, including `window_s >= confirm_s`, `exit_gap > enter_gap` where gap hysteresis applies, and sample interval smaller than its window;
- `llm.max_profile` is only a ceiling; catalog/verifier readiness can lower it;
- `tape.channels` must be nonempty when tape is enabled;
- full prompt capture requires explicit `llm_eval` channel and remains subject to redaction;
- paths resolving to filesystem root, home root or repository root are rejected.

String values are trimmed, reject control characters and are measured after Unicode normalization. A relative tape path resolves against the application working directory; validation uses the canonical parent path, rejects exact filesystem/home/repository roots and requires the destination to be creatable without following an existing symlink outside that parent.

### v1 migration table

| v1 key | v2 result |
| --- | --- |
| `commentary.use_hr_emotion=true|false` | `commentary.tone_source=heart_rate|none` |
| `commentary.cooldown_s` | removed; use director interval plus catalog cadence/fatigue |
| `commentary.decision_log_size` | `commentary.director.decision_capacity` |
| `commentary.sector_speak*` | removed; sector beat/catalog policy |
| `commentary.session_briefs` | removed; session context beats are catalog-driven |
| `commentary.stream_start` | removed; stream lifecycle is deterministic whenever commentary is enabled |
| `commentary.gap_hunt_tts_*` | removed; beat guards and event speech policy |
| `commentary.llm_polish` | `commentary.llm.enabled`; behavior is generation, not polish |
| `commentary.llm_base_url/model/timeout_s/max_tokens` | move to same names under `[commentary.llm]` |
| `commentary.llm_temperature` | removed; PromptOptions/catalog owns profile sampling |
| `commentary.llm_max_attempts` | removed; one transport attempt per beat/revision and a fixed maximum of two distinct beats per planning cycle |
| `[commentary.scheduler]` | removed; director/opportunity/speech contracts replace it |
| `[commentary.graph_runtime]` | removed; final v2 has one runtime |

Migration warnings identify the exact old key and replacement/removal. They never silently reinterpret a value.

The table is an operator migration map, not a compatibility loader. A recognized v1 key emits a `legacy_key` diagnostic naming its replacement/removal and disables commentary for that config generation until the file is changed; it is never applied in memory. An absent `[commentary]` section is valid and equivalent to `commentary.enabled=false`.

## HTTP API

All registered commentary JSON responses use `Content-Type: application/json` and top-level `schemaVersion: "commentary-runtime/2"`. Both write requests require `Content-Type: application/json`, the same schema version in their body, a body no larger than 64 KiB and the exact `X-Requested-With: irswitch` CSRF header. Their peer address must be loopback (`127.0.0.0/8` or `::1`); forwarded headers never grant locality. Unknown request fields are rejected. Limits are applied before serialization.

### Common error

~~~json
{
  "schemaVersion": "commentary-runtime/2",
  "error": {
    "code": "invalid_request",
    "message": "Human-readable bounded detail.",
    "fields": {"fieldName": "reason_code"}
  }
}
~~~

Error codes are stable enums: `invalid_json` (400), `invalid_request` (400), `forbidden` (403), `not_found` (404), `speech_busy` (409), `validation_failed` (422), `component_unavailable` (503), `mailbox_overloaded` (503), `admission_timeout` (503). Internal exception strings and filesystem/model secrets are never returned.

### `GET /api/commentary/status`

Always returns 200 when the HTTP service is alive, including when commentary is disabled or degraded.

~~~json
{
  "schemaVersion": "commentary-runtime/2",
  "status": "ready",
  "reason": null,
  "language": "en",
  "timeline": {
    "broadcastEpoch": 2,
    "streamEpoch": 3,
    "narrativeRunActive": true,
    "streamActive": true,
    "streamState": "active",
    "sessionPlan": {"revision": 4, "valid": true, "reason": null, "stages": ["practice", "qualifying", "race"]},
    "sessionRef": {"subSessionId": "123", "sessionNum": 2},
    "occurrenceId": "3:race:2",
    "lineageId": "3:practice:0>3:qualifying:1>3:race:2",
    "stage": "race",
    "historyComplete": true
  },
  "speech": {
    "state": "idle",
    "sourceKind": null,
    "utteranceId": null,
    "beatId": null,
    "opportunityId": null,
    "backend": null,
    "backendGeneration": null,
    "dispatchedAtMonoMs": null,
    "acceptedAtMonoMs": null,
    "lastTerminal": {
      "utteranceId": "utt:550e8400-e29b-41d4-a716-446655440000:17",
      "sourceKind": "narrative",
      "reason": "completed",
      "atMonoMs": 88710
    }
  },
  "queues": {
    "mailbox": {"depth": 0, "capacity": 64, "overflows": 0},
    "opportunities": {"depth": 2, "capacity": 128, "expired": 4, "evicted": 0}
  },
  "episodes": {
    "active": 1,
    "candidate": 0,
    "suspended": 0,
    "retainedCurrentCapacity": 64,
    "resolved": 12,
    "resolvedCapacity": 256
  },
  "catalog": {
    "schemaVersion": "narrative-catalog/2",
    "hash": "sha256:example",
    "eventIdentifierCount": 60,
    "beatCount": 64
  },
  "config": {
    "schemaVersion": "commentary-config/2",
    "desiredGeneration": 7,
    "desiredHash": "sha256:desired-example",
    "effectiveHash": "sha256:effective-example",
    "applySequence": 12,
    "pendingChanges": [
      {"key": "commentary.detector.battle_ahead_v1.max_closing_slope", "boundary": "next_stream", "desiredGeneration": 7}
    ]
  },
  "components": {
    "llm": {
      "status": "ready",
      "reason": null,
      "generation": 2,
      "configGeneration": 7,
      "model": "qwen3:4b-instruct-2507-q4_K_M",
      "residencyEvidence": "warmup_succeeded",
      "lastAttempt": {
        "requestId": "rr:550e8400-e29b-41d4-a716-446655440000:12",
        "outcome": "succeeded",
        "ttfbMs": 82,
        "ttftMs": 130,
        "totalMs": 530,
        "reducerLagMs": 3,
        "terminalReason": null
      }
    },
    "tts": {"status": "ready", "reason": null, "backend": "supertonic", "backendGeneration": 4, "configGeneration": 7, "quarantinedGeneration": null, "voice": "M1"},
    "tape": {"status": "disabled", "reason": null, "path": null, "drops": 0, "dropsByPriority": {"sample": 0, "normal": 0, "critical": 0}},
    "detectors": {"status": "ready", "reason": null, "disabled": []},
    "facts": {"status": "ready", "reason": null, "viewRevision": 204, "active": 87, "historicalSummaries": 19, "historyComplete": true}
  },
  "byTapeChannel": {
    "race.battle.closing": {"kick": 3, "accepted": 2, "queued": 2, "selected": 1, "started": 1, "expired": 1}
  }
}
~~~

Enums: status is `disabled|starting|ready|degraded|stopping|stopped`; streamState is `inactive|active|unknown`; `streamActive` is its lossless OBS projection `false|true|null`; `narrativeRunActive` is a required boolean. Speech state is `idle|building|committed|speaking|stopping`. Episode `retainedCurrentCapacity` applies to the sum of candidate+active+suspended entries. Before the first observed output, `broadcastEpoch=0`; before the first admitted narrative run, `streamEpoch=0`. After a run closes, `streamEpoch` retains the last allocated value while `narrativeRunActive=false`; the next run increments it. `sessionPlan` is null before first plan publication; otherwise it is the exact bounded status projection `{revision,valid,reason,stages}`. Revision is nonnegative, stages has 0–3 unique values in canonical order, a valid plan has 1–3 stages and null reason, and an invalid plan has no stages plus `session_plan_conflict`. Whenever there is no coherent supported current session, `sessionRef`, `occurrenceId`, `lineageId` and `stage` are `null` and `historyComplete=false`, but the independently published session plan remains visible. Otherwise stage is `practice|qualifying|race`; unsupported/identity-conflict detail belongs in `reason`, not a fabricated stage. `config.applySequence` is nonnegative and names the effective snapshot. `config.pendingChanges` has 0–128 exact `{key,boundary,desiredGeneration}` entries sorted by key and never exposes values; desired/effective hashes may differ until every named boundary occurs. `byTapeChannel` contains known channels with nonzero counters only and is capped at 128 entries sorted by channel ID.

Component status is `disabled|starting|ready|degraded|unavailable`; component `reason` values and all terminal/decision reasons are IDs from the frozen reason registry, never exception messages. LLM/TTS worker/backend generations, their `configGeneration`, and fact view revisions/counts are nonnegative integers. Component `configGeneration` names the desired generation whose effective component values its current preflight proves; while a newer applied component generation is pending/failed, that component cannot be used. TTS quarantined generation is null or no greater than the current backend generation; while equal, TTS must be unavailable and admit no speech. `drops` equals the sum of the three nonnegative `dropsByPriority` counters. `detectors.disabled` is capped at 128 entries of `{id, reason}` sorted by detector ID. Fact health becomes degraded with `fact_capacity_evicted` after lossy compaction for the rest of the narrative run and unavailable with `fact_capacity_exhausted` while no complete bounded view can be published. The next complete coherent bounded view moves unavailable→degraded; only a new complete run with no loss restores ready. Model/voice/path strings are bounded to their config maxima; tape path is relative to the configured recording root and never exposes an absolute host path.

LLM `residencyEvidence` is `warmup_succeeded|not_requested`; it is evidence for latency grouping, not proof that a model remains resident. `lastAttempt` is null before the first admitted Qwen request and thereafter is exactly `{requestId,outcome,ttfbMs,ttftMs,totalMs,reducerLagMs,terminalReason}`. Outcome is `succeeded|failed|cancelled|timed_out|stale`; nullable metrics remain null when their source milestone was not observed. It exposes no prompt, completion, endpoint or exception text. Exact metric equations and terminal meanings are defined by `qwen-transport-contract.md`.

The speech projection is exactly `{state,sourceKind,utteranceId,beatId,opportunityId,backend,backendGeneration,dispatchedAtMonoMs,acceptedAtMonoMs,lastTerminal}`. Source kind is `narrative|manual`; all current fields except state and retained `lastTerminal` are null in idle. Narrative beat/opportunity follow the immutable request, while manual beat/opportunity remain null. Backend is concrete `sapi|espeak|supertonic`; no text, voice, device or dispatch token is exposed. The retained terminal shape is exactly `{utteranceId,sourceKind,reason,atMonoMs}`.

### `GET /api/commentary/decisions?limit=N`

`limit` defaults to 20 and is clamped to 1–100. Records are newest-first and bounded by `decision_capacity`.

~~~json
{
  "schemaVersion": "commentary-runtime/2",
  "runtime": true,
  "decisions": [
    {
      "reducerSequence": 418,
      "atMonoMs": 90231,
      "decision": "selected",
      "reason": "highest_valid_candidate",
      "beatId": "battle.approach",
      "episodeId": "battle-ahead:3:17:22:4",
      "opportunityId": "opp:401",
      "tapeChannel": "race.battle.closing",
      "candidateSource": "event_opportunity",
      "candidateOrder": {"reducerSequence": 417, "sourceOrdinal": 0},
      "relation": "updates_active_episode",
      "urgency": "story",
      "score": 68.5,
      "threshold": 35.0,
      "runnerUp": {"beatId": "battle.pursuit", "score": 56.0},
      "terminalReason": null
    }
  ]
}
~~~

Decision is `selected|silence|discarded|replaced|expired|invalidated`; candidateSource is `event_opportunity|story_successor|episode_beat|filler`; candidateOrder uses the exact actor-assigned pair from the planning contract; relation is a stable ID from the frozen relation registry or `null`. The endpoint does not return prompt/completion content; that belongs to explicitly enabled tape capture.

### `POST /api/commentary/validate`

The endpoint is offline with respect to live state: it validates supplied EN text against one catalog beat and supplied immutable bindings at the caller-supplied monotonic evaluation instant. Times only need to share an origin inside this request; they are never compared with the live process clock.

~~~json
{
  "schemaVersion": "commentary-runtime/2",
  "text": "He is closing on Morgan, the gap at one point four seconds.",
  "beatId": "battle.approach",
  "evaluationAtMonoMs": 90231,
  "actorBindings": [
    {"actorId": "hero", "aliases": ["he", "the driver"]},
    {"actorId": "car:22", "aliases": ["Morgan", "the car ahead"]}
  ],
  "factBindings": [
    {
      "schemaVersion": "atomic-fact/2",
      "factId": "fact:88",
      "predicate": "battle.approaching",
      "subjectId": "hero",
      "objectId": "car:22",
      "attributes": {"materialBand": "material", "gap": 1.4, "targetEpoch": "relation:4"},
      "polarity": "positive",
      "validFromMonoMs": 89000,
      "validUntilMonoMs": 94000,
      "observedAtMonoMs": 90180,
      "broadcastEpoch": 2,
      "streamEpoch": 3,
      "occurrenceId": "3:race:2",
      "lineageId": "3:practice:0>3:qualifying:1>3:race:2",
      "evidenceRefs": ["event:401", "feature:gap-ahead:77"],
      "confidence": 0.94,
      "scope": "occurrence",
      "status": "active",
      "revision": 4
    }
  ]
}
~~~

~~~json
{
  "schemaVersion": "commentary-runtime/2",
  "valid": true,
  "beatId": "battle.approach",
  "issues": [],
  "claims": [
    {"predicate": "battle.approaching", "subjectId": "hero", "objectId": "car:22", "verdict": "supported"}
  ]
}
~~~

Syntactically valid requests return 200 even when `valid=false`. Unknown beat or malformed binding schema is 400. `text` is 1–512 normalized Unicode characters, `beatId` is 1–128 ASCII ID characters, `factBindings` contains 1–32 unique fact IDs, every attributes object has at most 32 registry keys and every evidenceRefs array has 1–16 unique IDs. `actorBindings` contains 0–16 unique actor IDs with 1–8 unique aliases of 1–64 normalized characters each; it must bind every non-null subject/object actor in the facts and may contain no unused actor. Alias comparison uses Unicode casefold after whitespace normalization; collisions across actor IDs are invalid because direction would be ambiguous. Actor-free beats require an empty list. This is the endpoint's complete actor lexicon—it never reads the live roster or driver config. Numeric/unit surfaces are still generated by the shared deterministic SurfaceValueSet functions from the supplied facts.

Every fact binding contains exactly the AtomicFact fields shown; `subjectId`, `objectId` and `validUntilMonoMs` are generally nullable. `occurrenceId` and `lineageId` are nullable only together and only for stream-scope bindings admitted by the selected beat: `stream.started`, or `broadcast.context`/`context.track_identity` in the stream form of `filler.lobby`. All other beat bindings require both. Predicate/attribute IDs, scalar types and implied units come from the frozen fact registry. `polarity` is `positive|negative`, confidence is finite `0..1`, scope is `occurrence|downstream|stream|revalidate|historical_only`, status is `active|expired|superseded|historical|provisional|rejected|unknown`, revisions and millisecond times are nonnegative integers and all strings reject control characters. Only the EN catalog/tokenizer is used. Issues contain stable `code`, `severity` (`error|warning`) and a message capped at 256 characters.

Validation is available while automatic commentary is disabled, provided the v2 catalog/registries loaded successfully. Otherwise it returns `component_unavailable`/503; it never calls Qwen or reads live runtime facts.

### `POST /api/commentary/speak`

This is a manual EN audio-device test, not a narrative injection endpoint. It uses the same single speech lane, never preempts live speech and never creates EventOpportunity, episode transition or ExposureStore entry.

It remains available while automatic commentary is disabled. Admission is decided by NarrativeRuntime, so a 202 response means the request actually owns the lane; the HTTP handler never maintains its own busy flag or speech waiter. It uses only the bounded one-shot admission latch frozen in `actor-transition-contract.md`.

~~~json
{
  "schemaVersion": "commentary-runtime/2",
  "text": "Commentary audio test.",
  "language": "en"
}
~~~

On immediate lane admission it returns 202:

~~~json
{
  "schemaVersion": "commentary-runtime/2",
  "accepted": true,
  "requestId": "manual:7f5b",
  "admittedState": "committed"
}
~~~

Busy returns `speech_busy`/409; invalid text returns `validation_failed`/422; unavailable selected backend returns `component_unavailable`/503; failure to admit the command to the fixed mailbox returns `mailbox_overloaded`/503. If the actor has not claimed the one-shot admission latch within the fixed 1,000 ms bound, the adapter atomically abandons it and returns `admission_timeout`/503; an abandoned request can never later produce audio. `force`, arbitrary locale and live fact/event injection are not supported.

`schemaVersion`, `text` and fixed `language="en"` are the only request fields. `text` is 1–400 normalized Unicode characters with no control characters. Manual speech always snapshots the current effective preflighted TTS backend/voice/rate/generation; per-request backend construction or override is forbidden. `admittedState` is exactly `committed` and records the atomic dispatch transition, not a promise that the worker has not progressed before the HTTP response arrives; the current matching `utteranceId` is visible in status while active. No language classifier is claimed—the explicit EN tag and EN-only operator contract are authoritative.

### Removed endpoint

`GET /api/commentary/assignments` is not registered. It therefore returns the server's generic 404 contract, which is not a commentary-runtime JSON response and is deliberately not a compatibility tombstone. The `/commentary` operator page may remain, but it consumes only the v2 public endpoints.

### Overall health projection

`GET /health` keeps its existing overall service contract and success status. It adds only this bounded component field:

~~~json
{
  "commentary": {
    "status": "ready",
    "reason": null
  }
}
~~~

Commentary `disabled` or `degraded` does not make overall health fail. Full component detail remains in `/api/commentary/status`.
