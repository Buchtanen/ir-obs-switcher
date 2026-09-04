# Commentary content DB + fill plan

**Status:** implemented authored-content baseline plus prepared buffered-microstory runtime;
audible private-stream validation remains pending (§11–§24)
**Depends on:** [COMMENTARY_ENGINE.md](../COMMENTARY_ENGINE.md), PR #120 (`cursor/commentary-engine-2dc4`)  
**Out of scope:** Neo4j or any new runtime DB dependency; overlay HUD / Event Engine math; OBS media sink

## 1. Intent check (keep re-reading)

| Claim | Truth in this repo |
| --- | --- |
| “Grafová DB” | **Graph-shaped content store**: nodes + edges + variant cells. Today that is `src/irswitch/commentary/data/sequence_graph.json` loaded by `graph.py`. **Not** Neo4j / SQLite / network graph DB. |
| Who decides *what happened* | Event Engine (emit → arbitrate → `EventEnvelope`). |
| Who decides *whether / what to speak* | `CommentaryDirector` after accepted envelopes. |
| Who writes *spoken text* | Another **text model** (or human), via assignment briefs → validated JSON patch. |
| Historical W0 mock | EN `neutral` started on four nodes: `in_car`, `lap_complete`, `pit_entry`, `back_on_track`. W1–W6 are now complete. |
| Current authored graph | EN+CS parity is complete and the graph contains the denser reviewed variant matrix recorded in §9. `emotion → neutral` and `locale → en` remain compatibility lookup rules. |

If a future proposal needs a real graph DB server, it is a **separate approved track** (new dep + hosting). This plan stays on the JSON graph as the content DB until that is explicitly requested.

## 2. Architecture the plan must respect

```text
iRacing / BLE HR
  → emitters → CandidateEvent
  → EventManager / V2
  → accepted EventEnvelope
  → CommentaryDirector + SequenceGraph
  → validate_utterance
  → TtsSink
```

Stable contracts for the historical authored-content waves (do **not** change when filling texts):

- node `id`, `family`, `event_types`, `phases`
- `speak_priority`, `cooldown_s`, `slots`, `hr_states`, `tts.*`
- `edges` (sequence preferences)
- graph v3 `editorial` policy metadata and parent-scoped story semantics on nodes and edges
- validator rules in `validator.py`
- existing config keys under `[commentary]` (the new runtime contract is specified separately in
  §19.1)

Mutable content surface (this plan fills only this):

- `nodes.*.variants.{locale}.{emotion}` → `list[str]` (1–3 lines per cell)
- optional: `nodes.*.notes` (author hints only)

Playback fallbacks that make gradual fill safe:

1. Empty cell → silence for that emotion (or mock EN if present).
2. Missing emotion bucket → use `neutral` if present (mock stays audible with BLE HR).
3. Missing `cs` → fall back to `en` (`GraphNode.variant_bucket`).
4. `commentary.enabled=false` by default → fill work never forces speech on existing installs.

## 3. Authored content-store definition (historical v1)

### 3.1 Physical store (Phase A — now)

| Item | Path / owner |
| --- | --- |
| Document | `src/irswitch/commentary/data/sequence_graph.json` |
| Schema version | top-level `"version": 4` (`GRAPH_VERSION` in `graph.py`); v1–v3 compatibility is owned by the loader and rollout contract |
| Loader | `load_sequence_graph()` / `parse_sequence_graph()` |
| Integrity | `validate_graph_document()` + catalog event ids |
| Inventory | `SequenceGraph.unfilled_cells()` → `(node_id, locale, emotion)` |
| Briefs | `render_assignments(only_unfilled=True)` |

**Inventory at plan time (graph v1):**

- 26 nodes, 12 edges, locales `en` + `cs`
- Mock-filled EN `neutral`: 4 nodes
- Unfilled cells: **184** (~90 en, ~94 cs) — every emotion × locale without authored lines

### 3.2 Logical cell key

```text
cell_id = "{node_id}/{locale}/{emotion}"
example: "overtake/cs/pushing"
```

Emotion buckets: `neutral` | `calm` | `focused` | `pushing` | `high`  
(`unknown` HR maps to `neutral` for authoring and playback.)

### 3.3 Optional later store (Phase D — not scheduled)

Only if JSON in-repo becomes painful (size, multi-author, A/B):

- Keep the **same logical schema** (nodes/edges/variants).
- Export/import still round-trips to `sequence_graph.json` (or a split `variants/*.json` merged at load).
- No runtime Neo4j unless separately approved. Director must keep loading a local document.

## 4. Historical fill waves (mock → authored)

Each wave is a PR (or PR slice) that only patches `variants` (+ tests). Mock lines remain until replaced or demoted.

| Wave | Scope | Goal | Mock behaviour |
| --- | --- | --- | --- |
| **W0** | Structure + EN mock (PR #120) | Live path tryable | EN `neutral` on 4 nodes |
| **W1** | EN emotions on mock-4 | Prove emotion matrix without new events | Replace/extend mock with calm/focused/pushing/high; keep ≥1 neutral |
| **W2** | EN high-priority race beats | Speak real race story | Fill: `overtake`, `side_by_side`, `hunting`, `hunted`, `battle_won`, `position_gained`, `position_lost`, `incident`, `final_lap`, `finish` |
| **W3** | EN pit + session sidecar | Close pit story; keep in-car | `pit_outcome`; deepen `pit_entry` / `back_on_track` / `in_car` |
| **W4** | EN timing / quali / practice | Non-race chatter | `personal_best`, `gain_found`, `time_lost`, `target_locked`, `projected_lap`, `hot_lap`, `position_attack`, `clean_streak`, `rival_threat` |
| **W5** | EN bio | Rare HR line | `hr_pressure` (only pushing/high) |
| **W6** | CS parity | Czech speech | Same cell keys as EN waves; director locale `cs` |
| **W7** | Sequence polish | Edge-aware wording | Composer now consumes actual edge history; optional copy re-brief follows live listening |

**Recommended order inside a wave:** highest `speak_priority` first (finish → … → hr_pressure), so silence gaps hurt less.

**Definition of done for a wave:**

- [ ] All target cells have 1–3 lines
- [ ] Every line passes `validate_utterance` with that node’s slots + TTS limits
- [ ] Unit test: sample lines bind with example slots; director speaks non-empty for wave events
- [ ] `unfilled_cells()` count drops by the expected number
- [ ] Docs: this plan’s wave checkbox updated; `COMMENTARY_ENGINE.md` mock section if mock nodes change
- [ ] No new dependencies; no Event Engine / overlay behaviour change

## 5. Text-model handoff protocol

### 5.1 Roles

| Role | Responsibility |
| --- | --- |
| **Repo / engineer agent** | Owns graph structure, validator, director, tests. Emits briefs. Merges validated patches. |
| **Text model (author)** | Writes only spoken lines. Does not invent nodes, slots, events, or overlay tokens. |
| **Human reviewer** | Voice taste, CS idiom, merge approval. |

### 5.2 Recommended text model

Default for generation batches:

- **Primary:** Cursor / cloud agent with a strong writing model (prefer Claude Opus-class or GPT-5-class when available in the agent picker).
- **Constraint:** same model for one wave (consistent voice). Do not mix styles mid-wave.
- **Human fallback:** paste the same brief into ChatGPT / Claude web if offline; return JSON in the schema below.

Do **not** use a code-only / “fast” model for authoring — tone drift and ALL-CAPS / stacked punctuation failures waste cycles.

### 5.3 Brief generation (input to the text model)

From a checkout of the commentary branch:

```bash
# Markdown briefs for unfilled cells only (default)
.venv/bin/python -c "from irswitch.commentary import render_assignments; print(render_assignments())" \
  > /tmp/commentary_assignments.md

# One locale / include already-filled (for rewrite waves)
.venv/bin/python -c "from irswitch.commentary import render_assignments; print(render_assignments(locale='cs', only_unfilled=True))"
```

Optional wave filter (engineer): slice the markdown to the node ids of the active wave before sending.

Each brief already includes: event types, phases, slots + examples, emotion hints, previous/next nodes, overlay tokens (do not copy), TTS limits, author notes, deliver rules.

### 5.4 System prompt (paste with every batch)

```text
You fill spoken race-commentary variants for irswitch.
Input: markdown assignment briefs generated by render_assignments().
Output: ONLY a JSON object matching the delivery schema (see plan §5.5).
Rules:
- Fill spoken variants only. Never change node ids, slots, edges, or TTS limits.
- Locales: en and/or cs as requested in the batch header.
- 3–6 lines per emotion cell (target ~4; roughly **2×** the early W1–W6 density). **Viewer-facing broadcast** (third person about the driver). Never second-person to the driver. One breath per line.
- Use slot tokens verbatim, e.g. {position}, {gap}, {target_name}.
- Terminal punctuation required: . ! or ?
- Forbidden: ALL-CAPS words, stacked !!/??/..., emoji, URLs, digit runs of 4+.
- SSML only if needed: <break time="…ms"/> (≤500ms) and <emphasis>…</emphasis>.
- Overlay HUD tokens are visual only — do not speak them as labels.
- Intensity comes from word choice per emotion, not shouting.
- Czech (cs): natural spoken Czech commentary for viewers, not a driver-coach radio and not a literal EN translation.
```

### 5.5 Delivery schema (output from the text model)

```json
{
  "graph_version": 3,
  "wave": "W2",
  "author_model": "claude-opus-… / gpt-5-… / human",
  "patches": [
    {
      "node_id": "overtake",
      "locale": "en",
      "emotion": "pushing",
      "lines": [
        "You take {position} from {target_name}.",
        "Past {target_name} — that's {position}."
      ]
    }
  ]
}
```

Rules:

- `graph_version` must match the loaded graph.
- Unknown `node_id` / `locale` / `emotion` → reject whole batch.
- Empty `lines` → reject cell.
- Engineer merges into `sequence_graph.json` under `nodes[node_id].variants[locale][emotion]`.

### 5.6 Merge + verify loop

```text
1. Engineer selects wave + generates briefs
2. Text model returns JSON patches
3. Script/check (manual OK for first waves):
   - schema validate
   - for each line: validate_utterance(line, slots=node.slots, limits=node.tts)
   - optional: fill_slots with examples and speak once on /commentary
4. Patch sequence_graph.json
5. pytest: tests/test_commentary_graph.py + wave-specific asserts in test_commentary_mock.py (or new test_commentary_content_wN.py)
6. Update unfilled count in this doc’s checklist
7. Commit: docs/content only — message like "feat: commentary EN W2 race-beat variants"
```

Suggested one-liner check (after a small helper exists; until then use pytest + `/commentary`):

```bash
.venv/bin/python -c "from irswitch.commentary.graph import load_sequence_graph; print(len(load_sequence_graph().unfilled_cells()))"
```

### 5.7 Batch sizing

| Batch size | Guidance |
| --- | --- |
| Small (preferred) | 1 family or ≤5 nodes × one locale × all emotions |
| Medium | One full wave × one locale |
| Avoid | Entire 184 cells in one shot (voice drift + hard review) |

Pass previous/next node sample lines and the `commentary-facts/1` clause trace when the node sits on an `edges` path (W7 / edge-aware batches). The runtime composer is already shipped; W7 changes wording only.

## 6. Historical gradual mock → data connection map

| Runtime path | Today (W0) | After authored cell |
| --- | --- | --- |
| `in_car` / lap / pit / exit | EN mock `neutral` matrix, `rng.choice` | Same picker; authored emotions used when HR matches; mock `neutral` remains fallback |
| Other graph nodes | Empty → silence | Speak when cell filled |
| Locale `cs` | Falls back to EN mock where EN exists | Speaks CS when CS cell filled |
| Assignments | `only_unfilled=True` lists empty cells (mock EN counts as filled for that bucket) | Shrinks as waves land |
| Overlay / Event Engine | Unchanged | Unchanged |

**Do not** delete mock EN until W1+ has reviewed replacements and a test asserts non-empty `neutral` for those four nodes.

## 7. Non-goals

- Unbounded/free-form LLM ownership of race truth. The proposed §11 buffer permits bounded
  pre-generation from a deterministic fact plan; all output remains grounded and validated.
- Changing Event Engine arbitration to “sound better”
- Storing secrets / API keys for external LLM APIs in the repo
- Neo4j / hosted graph DB in Phase A–C
- Reading overlay i18n tokens aloud

## 8. Docs / config impact

| Doc | Action |
| --- | --- |
| This file | Source of truth for fill plan + handoff |
| `COMMENTARY_ENGINE.md` | Link here; keep runtime truth |
| `README.md` | Link under documentation |
| `CONFIG.md` / example ini | No change for authored fill waves; prepared runtime changes are in §24 |
| `API.md` | No change unless a content-admin endpoint is later approved |

## 9. Checklist (progress)

- [x] W0 — structure + EN mock (PR #120)
- [x] W1 — EN emotions on mock-4 (gpt-5 patches; unfilled 184 → 172)
- [x] W2 — EN high-priority race beats (gpt-5; unfilled 172 → 132)
- [x] W3 — EN pit_outcome (gpt-5; unfilled 132 → 129)
- [x] W4 — EN timing / quali / practice (gpt-5; unfilled 129 → 99)
- [x] W5 — EN bio + invalid_lap (gpt-5; unfilled 99 → 94; **EN complete**)
- [x] W6 — CS parity all-at-once (claude-opus parallel W6a/b/c; unfilled 94 → **0**)
- [x] VOICE — stream-viewer broadcast + denser matrix (~4 lines/cell; **426 → 752** lines)
- [x] N11 A — `stream_start` (long node TTS cap, slot-free EN+CS) + mode `in_car_*` (generic `in_car` kept)
- [x] N11 B/C/D — sparse `incident_*` branches, flag one-liners, `quali_recap` / `parade_pad`
- [ ] W7 — optional wording polish after live composer listening (composer runtime shipped)
- [ ] (optional) Phase D store split / export — only if approved

## 10. Historical authored-content decisions

The decisions that once blocked W1–W6 are closed: EN was completed before the all-at-once CS
parity wave, the original neutral mock cells were retained as authored fallback buckets, patching
continued through reviewed JSON edits without a required patch script, and `stream_start` landed as
a slot-free N11 node. W7 wording polish and an optional future store split remain optional backlog;
neither blocks the prepared runtime specified below.

---

**Return point:** update §9 checkboxes and inventory counts when a wave merges. Do not fork a second plan file — extend this one.

## 11. Buffered editorial microstories — runtime redesign

**Status:** implementation-ready target contract. The current runtime does not yet contain this
pipeline; adding it is the intended behavior change, not a gap to be hidden by legacy copy.

This section records the next requested commentary layer: several-sentence filler stories prepared
asynchronously from a frozen factual context, polished before they are needed, and offered to the
stateful commentary graph only while they remain true and useful. It extends the existing content
plan instead of creating a second competing plan.

### 11.1 Terminology

The product term **commented microstory** is retained here, but the runtime type should be named
`PreparedFiller` or `PreparedEditorialBeat`. The code already uses `MiniStory` for a different
contract: the revisioned truth/lease lifecycle immediately before TTS. Reusing that type name would
mix pre-generation with factual commit and interruption semantics.

A prepared filler is:

- one coherent two-to-five-sentence unit intended to be spoken without an internal cut;
- built from a typed immutable `FactBundle`, never directly from live mutable telemetry;
- represented by one concrete microstory situation: graph node + branch + scope + material fact
  revision + locale;
- available only when that individual situation owns three to five polished variants which passed
  deterministic validation;
- invalidated or regenerated after a material source revision;
- selected by the existing graph, not by a second FIFO or round-robin playlist.

It is not free-form live commentary. Detection, classification, numbers, actors and result bands
remain deterministic. The LLM may join and phrase already selected propositions while the buffer is
being prepared; it may not add a proposition, causal claim, adjective of performance, or certainty
which is absent from the plan.

### 11.2 Product decision

Add one `PreparedFillerCoordinator` owned on the commentary-consumer side. It receives immutable
context revisions from the race producer, continuously reconciles the required current/next-stage
microstory situations with the buffer, schedules bounded background generation or regeneration,
and publishes complete situation-specific sets into a bounded buffer. A candidate becomes audible
only through the normal path:

```text
iRSDK / stream / optional external APIs / sysinfo
  -> source-specific extractors and caches
  -> immutable EditorialContextRevision
  -> deterministic FillerPlanBuilder
       required propositions + optional propositions + validity + semantic key
  -> PreparedFillerCoordinator
       bounded owned async generation; no synchronous playback-time generation
  -> PreparedFillerBuffer
       three-to-five variants per plan; freshness and local variant exposure
  -> SequenceGraphRuntime candidate
       strict tier + graph score + semantic/path fatigue + silence pressure
  -> MiniStory commit/revalidation
  -> TTS
```

The coordinator must not run in the telemetry loop, block fan-out, own race truth, or enqueue text
directly into TTS. Playback normally takes only an already validated variant from the buffer.
External API failure removes only the propositions that depend on that source.

There is exactly one exception to the no-fallback rule: after the LLM attempt budget is exhausted
and there is no valid ready plan for the current eligible stage, the graph may speak the fixed
operational node `prepared_filler_fatal_notice` once for that fatal episode. Its Czech text is
`LLM fatal error, nemám texty.`; its English localization is `LLM fatal error, I have no text.` The
notice is authored, bypasses LLM polishing, contains no race fact and is not a substitute filler.
After it starts speaking, further filler remains silent until recovery. This subsystem-fatal state
must not crash the race loop, block fan-out, preempt a live race event or silence unrelated
live-event commentary.

### 11.3 One repetition owner

Do not create a second global penalty system inside the buffer. Responsibilities are:

| Concern | Owner |
| --- | --- |
| topic, semantic fact, edge and short-path fatigue | `SequenceGraphRuntime` |
| whether a prepared fact is still current | source snapshot + commit revalidation |
| which textual variant of the same plan was least recently exposed | `PreparedFillerBuffer` |
| wording/tail similarity | existing lexical anti-repeat |

Each variant may keep `spoken_count` and `last_spoken_at`, but those values only choose among
variants after the graph has selected the semantic candidate. They must not let a low-tier filler
beat a live race event.

### 11.4 Closed product decisions

| Decision | Closed contract |
| --- | --- |
| runtime scope | this change delivers the runtime redesign, not only documentation or graph copy |
| unresolved review points | this specification closes stage, failure, source, rollout, diagnostics and test ownership before coding |
| YouTube identity | one existing authenticated channel; its public completed-stream history is enough; no multi-account feature |
| timing/interruption | use §§15–16 values first and change them only from retained test evidence |
| LLM ownership | asynchronous producer fills the bounded buffer; playback only selects a ready variant |
| empty buffer failure | after exhausted attempts, announce the fixed fatal notice once, then filler silence until recovery |
| iRSDK validation | implement nullable active extraction now and validate with synthetic plus retained live tests; no guessed value |
| story migration | new prepared story path is part of this change; legacy remains a selectable rollback |
| shadow purpose | execute the full prepared pipeline silently and collect reconstructable comparison data while legacy is audible |

These are not implementation options. Only numeric calibration and wording may change after §23
evidence without reopening the product contract.

## 12. Buffer and generation contract

### 12.1 Required immutable types

```python
@dataclass(frozen=True, slots=True)
class FactProposition:
    predicate: str
    subject_id: str
    object_id: str | None
    value: str | int | float | None
    unit: str | None
    source: str
    source_revision: str
    observed_monotonic_ms: int
    occurred_at_utc: str | None
    fetched_at_utc: str | None
    expires_at_utc: str | None

@dataclass(frozen=True, slots=True)
class EditorialContextRevision:
    context_revision: str
    stream_epoch: int
    session_key: str | None
    run_epoch: int
    hero_car_idx: int | None
    stage: str
    stage_epoch: int
    propositions: tuple[FactProposition, ...]

@dataclass(frozen=True, slots=True)
class PreparedFillerPlan:
    plan_id: str
    situation_id: str
    node_id: str
    semantic_key: str
    scope: Literal["stream", "session", "run", "stint"]
    context_revision: str
    material_revision: str
    source_revisions: tuple[str, ...]
    stage_epoch: int
    valid_from_ms: int
    valid_until_ms: int | None
    allowed_stages: tuple[str, ...]
    required: tuple[FactProposition, ...]
    optional: tuple[FactProposition, ...]

@dataclass(frozen=True, slots=True)
class PreparedVariant:
    variant_id: str
    plan_id: str
    locale: str
    text: str
    text_hash: str
    estimated_seconds: float
    covered_proposition_ids: tuple[str, ...]
    source_revisions: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class VariantExposure:
    variant_id: str
    spoken_count: int
    last_spoken_monotonic_ms: int | None
```

The rendered buffer entry additionally stores locale, three-to-five validated variants,
generation status, attempt count, generation latency, last validation error and per-variant
exposure. It never stores secrets or a live provider object. UTC timestamps carry the time of an
external fact such as a completed YouTube stream; monotonic timestamps own in-process ordering,
holds and expiry. A plan over several sources carries every source revision and is current only
while all required propositions still match the latest context.

IDs use SHA-256 over canonical JSON, never process-random hashes:

- `situation_id` = node + branch + locale + stream/session/run/stint scope identity;
- `material_revision` = normalized propositions whose change requires different wording;
- `plan_id` = schema + situation id + material revision;
- `variant_id` = plan id + normalized generated text.

Thus one situation keeps its exposure history while its facts remain material-equivalent, but a
fact change creates a distinct plan whose old variants cannot leak into the new situation.

### 12.2 Bounds and regeneration

Version-one bounds are normative until replay evidence justifies a reviewed change:

- at most 24 ready plans across all families, with reserved capacity for the current and next
  stage so optional external colour cannot evict an intro/start/result plan;
- each concrete situation targets five validated variants and becomes selectable at the low-water
  mark of three; it may therefore contain three, four or five ready variants;
- at most two in-flight LLM generations, with one latest replacement per `situation_id`;
- no more than one regeneration for the same material revision;
- session/stream plans expire on their scope reset even if their wall-clock TTL has not elapsed;
- generation retries use bounded monotonic backoff and never run once per telemetry tick.

Queue order is deterministic: current-stage required family, next-stage required family, then
optional contextual and external families; ties use plan creation sequence and `plan_id`. A newer
revision cancels or supersedes queued older work. An in-flight call may finish, but its result is
dropped unless that exact `plan_id` is still desired for the current/next stage and its scope,
material revision and required source revisions still match. `context_revision` and creation
`stage_epoch` are provenance, not blanket invalidators: an unrelated telemetry change must not
discard or regenerate an otherwise current situation.

On every distinct `EditorialContextRevision` and after every generation completion, the coordinator
runs one reconciliation pass:

1. derive the finite desired set of concrete situations for the current and next stage;
2. remove plans/variants whose scope, stage or material/source revision is no longer valid;
3. preserve still-valid variants and their exposure counters;
4. if a desired situation has fewer than three valid variants, mark it non-selectable and enqueue a
   top-up ahead of optional work;
5. if it has three or four, keep it selectable and refill toward five in the background;
6. if a material situation fact changed, create a new `material_revision`, invalidate the old set
   atomically and generate a new 3–5 set;
7. cancel queued work for situations which are no longer desired and discard stale in-flight
   results on return.

Playback does not consume/delete a variant. It increments that variant's exposure penalty, so the
same valid set can be reused without an unbounded generation loop. Refill is triggered by missing,
rejected, expired or invalidated variants; regeneration is triggered by a material situation/source
revision or explicit operator retry. Exposure alone never changes race truth and never forces an
LLM request.

Regenerate only after a **material** revision: new session, changed wetness band, changed rubber
state, roster/class membership change, new qualifying result, start-mode discovery, session result,
or external-cache refresh. Do not regenerate because air temperature moved by 0.1 °C, a position
array flickered for one tick, or the commentary merely selected another variant.

Version-one material bands:

| Fact | Material revision |
| --- | --- |
| air or track temperature | at least 2 °C or named band change |
| wetness | iRSDK `TrackWetness` enum band change |
| rain | dry/wet declaration or precipitation intensity band change |
| rubber | normalized `SessionTrackRubberState` label change |
| field | roster digest or class count change before the session is locked |
| traffic | on-track population band change held for 10 s |
| HR tension | emotion band change held for 3 s; never regenerate on every BPM |
| result | newly confirmed classification or comparison band |

### 12.3 Variant validation

Generated text must pass the existing grounded validator plus a prepared-text contract:

- every required proposition is covered;
- every number, actor, place and relation binds to the plan;
- optional propositions may be omitted but not mutated;
- no unsupported superlative, causality, prediction, diagnosis or nationality;
- two-to-five sentences, one TTS unit, bounded by a dedicated long-filler duration cap;
- EN/CS language and viewer-facing third person follow the existing voice contract;
- three-to-five variants must differ materially in structure, not only punctuation or synonyms.

Generation may make a bounded number of attempts to obtain the complete three-to-five-variant set.
If the attempt budget is exhausted, publish no candidate, set `generation_exhausted` for that plan,
and enter prepared-filler `fatal` when no other valid ready plan exists for the current eligible
stage. On entry to `fatal`, offer the fixed `prepared_filler_fatal_notice` once through normal
Director arbitration. `fatal` is recoverable on a newer material/context revision or explicit
operator retry; it never substitutes another generated, templated or factual text source.

### 12.4 Health and failure state machine

`PreparedFillerCoordinator.health` is one of:

| State | Exact meaning | Exit |
| --- | --- | --- |
| `disabled` | rollout mode is `legacy`, or commentary is disabled | config enables shadow/active |
| `waiting_context` | no eligible plan can be built from the current immutable context | material context revision |
| `generating` | at least one eligible plan owns a bounded LLM task | valid result, exhaustion, reset |
| `ready` | at least one current plan has 3–5 validated variants | plan expiry/reset, or selection continues |
| `degraded` | some plans/sources failed, but another current plan is ready | successful refresh or all ready plans expire |
| `fatal` | every eligible current-stage plan is exhausted and the ready buffer is empty | newer material revision or explicit retry |

Transport error, timeout, malformed JSON, wrong variant count and validator rejection consume a
bounded attempt and retain a machine-readable reason. The transition to `fatal` increments
`fatal_episode`; only the first eligible selection in that episode may emit the notice. Generation
of any valid current plan changes health to `ready` and rearms the notice for a future episode.
Changing stage with no eligible facts yields `waiting_context`, not `fatal`; an optional external
source failing while core plans remain ready yields `degraded`, not `fatal`.

### 12.5 Generation wire contract

One request asks for the missing variants of exactly one immutable situation plan. The initial call
normally requests five; a top-up requests only the number needed to return the valid set to five.
The adapter sends the hashes of retained variants so the LLM must produce structurally different
wording, but sends no raw telemetry dump, recent transcript, OAuth value or optional fact outside
that plan. Its logical payload is:

```json
{
  "schema": "prepared-filler/1",
  "planId": "sha256:...",
  "nodeId": "stream_intro_conditions",
  "locale": "cs",
  "requestedVariants": 5,
  "existingVariantHashes": [],
  "required": [{"id": "air_temp", "value": 21.0, "unit": "degC"}],
  "optional": [{"id": "sky", "value": "partly_cloudy", "unit": null}],
  "constraints": {
    "sentencesMin": 2,
    "sentencesMax": 5,
    "maxSeconds": 28.0,
    "thirdPerson": true,
    "noNewFacts": true
  }
}
```

The response must be one JSON object, with no markdown or prose:

```json
{"schema":"prepared-filler/1","planId":"sha256:...","variants":["...","...","..."]}
```

The response `planId` must match and may not contain more items than `requestedVariants`. New valid
items are merged with retained variants by text hash and structural-similarity validation; the
situation becomes selectable only when the merged set reaches three and is capped at five. Error
codes are closed strings: `timeout`, `transport`, `http_status`, `invalid_json`,
`schema_mismatch`, `plan_mismatch`, `variant_count`, `empty_variant`, `duration`, `language`,
`grounding`, `unsupported_claim`, `duplicate_variant` and `stale_result`. Only validation errors may
receive the next stricter repair prompt; transport/timeout waits for the configured monotonic
backoff and consumes its attempt without an immediate retry burst.

### 12.6 Commit bridge and revalidation

A ready plan is adapted inside the commentary consumer to a private `PREPARED_FILLER` envelope and
normal `GraphCandidate`. It is not republished into N12 and never reaches the overlay audience. The
envelope carries `planId`, `variantId`, `nodeId`, `semanticKey`, scope ids, context/stage/source
revisions and `preparedText`; none of these fields becomes race truth.

Immediately before TTS enqueue, commit compares stream/session/run/stint identity, current allowed
stage, plan/material identity, monotonic validity and every required source revision with the latest
immutable context. The plan's creation `stage_epoch` remains diagnostic; the authoritative test is
that the producer has not superseded the plan and the current stage is allowed. Any mismatch records
`stale_dropped` and produces silence for that candidate. A committed
unit gets the existing narrative lease: later context change does not rewrite it, and only the
existing hard-interrupt policy may stop it. `CommentaryUtterance.prepared=True` is the sole signal
that `ProcessTtsSink` must use `text` directly and skip live `polish_skeleton()`; all number/name and
TTS safety processing still runs. The TTS lifecycle callback marks semantic and variant exposure
on `speaking`, never at commit or enqueue.

## 13. Data-source audit

Confidence labels below mean:

- **live-proven** — already extracted and covered in this repository;
- **available-not-wired** — present in iRSDK/session data but not in the current normalized model;
- **derived** — deterministic aggregation we must own and test;
- **external** — authenticated cached API data; never required for core commentary.

Upstream references: [pyirsdk variable list](https://github.com/kutu/pyirsdk/blob/master/vars.txt),
[pyirsdk session-data access](https://github.com/kutu/pyirsdk), and a representative
[session-string capture](https://github.com/MartijnStraatman/iracing-exporter/blob/main/examples.txt).
The capture is evidence of shape, not a promise that every key exists in every car/session; Phase 0
must retain raw fixtures from the actual stream PC.

| Product fact | Source and interpretation | Status / required delta |
| --- | --- | --- |
| circuit name/layout | `WeekendInfo.TrackDisplayName` + optional `TrackConfigName` | live-proven in `SessionContext`; reuse |
| city/country | `WeekendInfo.TrackCity`, `TrackCountry` | available-not-wired; add nullable strings |
| circuit shape | `TrackLength`, `TrackNumTurns`, `TrackType`, `TrackDirection` | available-not-wired; parse units, never infer difficulty from length alone |
| local light | live `SolarAltitude` is sun angle above horizon; `SessionTimeOfDay` is seconds since local midnight | available-not-wired; derive `day/dusk/night` from sun angle, with time-of-day only as supporting context |
| sky/air/track temperature/wind/rain | live `Skies`, `AirTemp`, `TrackTempCrew`, `WindVel`, `Precipitation`, `TrackWetness`, `WeatherDeclaredWet`; current-condition SessionInfo fallback | live-proven by `iracing.weather`; reuse its source tags |
| wet surface | `TrackWetness` enum and rain declaration | live-proven; this is not rubber state |
| rubber/usage state | current `SessionInfo.Sessions[SessionNum].SessionTrackRubberState` | available-not-wired; normalize exact observed labels, fail soft on missing/unknown |
| field size | eligible `DriverInfo.Drivers[]` after pace/spectator filtering | live-proven; roster size is not cars currently circulating |
| class sizes/multiclass | group eligible roster by `CarClassID`; corroborate with `WeekendInfo.NumCarClasses` | derived; reuse roster and `car_idx_class`, do not duplicate driver parsing |
| SoF | current arithmetic mean of positive `IRating`, overall and hero class | live-proven but explicitly **unofficial**; keep sample counts and never call it official iRacing SoF |
| AI field | `DriverInfo.Drivers[].CarIsAI`; iRating may be zero/missing | available-not-wired; use `ai_count/field_size`, not merely `sof is None` |
| provisional favorite | highest valid iRating in hero class, ties stable by car index; licence is context only | derived editorial heuristic; label “highest-rated entrant”, never “predicted winner” |
| licence/safety | `LicString` or `LicLevel`/`LicSubLevel` from `DriverInfo` | partially live-proven in `DriverFactLedger`; do not combine it into a fake performance score |
| cars circulating in Practice | eligible non-spectators with `CarIdxTrackSurface == OnTrack` and not `CarIdxOnPitRoad` | derived; hold population band before saying “quiet track” |
| lobby / in car / on track | existing `DrivingMode`, `ENTER_CAR`, `IsOnTrack`, surface and pit state | live-proven; reuse, do not add a second seat detector |
| engine start | `EngineWarnings.engineStalled` transition corroborated by `RPM` | available-not-wired and optional; movement start is safer than claiming an engine start when unsupported |
| rolling vs standing | `WeekendInfo.WeekendOptions.StandingStart` is primary; `SessionState == ParadeLaps` and `PaceMode` corroborate rolling formation | available-not-wired; `StartingGrid` alone is not sufficient evidence of start type |
| start lights | `SessionFlags` start-ready/set/go bits | raw bitfield already present, bits not currently exposed as start-light semantics |
| distance to start line | `LapDistPct`; optionally multiply remaining fraction by parsed track length | live-proven base + derived distance; only valid on the current lap and with sane motion |
| out lap | pit-road falling edge in Practice/Qualifying until next start/finish wrap | derived FSM; iRSDK does not supply the product `OutLap` state directly |
| qualifying result | existing cross-session `QualiBag` from live hero class position + official `LapBestLapTime` | live-proven; prefer it over late YAML result tables for immediate Race intro |
| posted results | `SessionInfo.Sessions[].ResultsPositions` after the YAML revision changes | available-not-wired; useful as delayed corroboration, never assumed ready at checkered |
| finish | existing `player_finished`/`mute_field` semantics | live-proven; `SessionState == Checkered` alone is not a hero finish |
| HR tension | existing BLE `bpm`, rolling baseline, `delta_bpm`, emotion band | live-proven; add a short held trend only if replay proves value |
| machine load | existing `SystemState` CPU/GPU/RAM/FPS plus 10/60 s history | live-proven; suited to rare system-health colour, not hardware identity |
| machine model/spec | not currently exposed; would require explicit static inventory | optional derived/external OS source; privacy-reviewed opt-in only |

### 13.1 Corrections to ambiguous product names

1. **Track condition** must be split into `surface_wetness` and `rubber_state`. A wet track can be
   well rubbered; one must not overwrite or paraphrase the other.
2. **SoF null** does not prove an AI race. Use `CarIsAI` and report AI participation directly.
3. **Favorite** is not supplied by iRacing. The safe factual phrase is “the highest-rated entrant
   in this class”; licence may be mentioned separately but must not be used as a hidden weight.
4. **Nationality** is not currently available in `DriverFactLedger` (`nationality=None`).
   `DriverInfo.ClubName` is an iRacing club/region and must not be relabelled as nationality.
5. **ResultsPositions** is a mutable YAML result table. It may arrive later than the live position
   arrays, so end-of-session speech must use the existing confirmed finish path and treat YAML as
   corroboration/enrichment.

## 14. Required graph-node inventory

Existing nodes such as `stream_start`, `session_intro_*`, `sof_brief`, `weather_brief`,
`in_car_*`, `quali_recap`, `parade_pad`, `session_wrap`, `session_preview`, `field_fact` and
`weather_change` remain compatibility nodes. The buffered feature should add specific semantic
nodes rather than overload one generic node with unrelated fatigue.

### 14.1 Stream and venue opening

| Proposed node | Required truth | Scope / normal stage |
| --- | --- | --- |
| `stream_intro_venue` | track; optional layout/city/country | stream+venue / lobby opening |
| `stream_intro_circuit_character` | length/turns/type/direction subset | stream+venue / after venue |
| `stream_intro_conditions` | at least two current-condition facts | weather signature / lobby opening |
| `stream_intro_surface_state` | wetness or rubber state with source | condition revision / after weather |
| `stream_intro_field_overall` | eligible field size; optional unofficial overall SoF | session / lobby opening |
| `stream_intro_field_class` | hero class size; optional class SoF | session+class / after overall field |
| `stream_intro_ai_field` | positive `ai_count` and ratio | session / replaces missing-SoF speculation |
| `practice_quiet_track` | held low circulating-car band | stint / Practice only |

Initial required edge chain:

```text
stream_start
  -> stream_intro_venue
  -> stream_intro_circuit_character
  -> stream_intro_conditions
  -> stream_intro_surface_state
  -> stream_intro_field_overall
  -> stream_intro_field_class
```

Every edge is optional. Missing data shortens the sequence; it never delays the next usable fact.
Wet or dark conditions may select a “greater challenge” style card only when the exact supporting
facts are in the plan. “Hard race” must not be inferred from cloud cover alone.

### 14.2 Session event intro and leaving the pits

| Proposed node | Meaning |
| --- | --- |
| `event_intro_practice` | Practice-specific purpose and available context |
| `event_intro_qualifying` | timed-lap stakes and available context |
| `event_intro_race` | race-stage handoff after stream intro |
| `hero_prepares_to_drive` | all major intro topics already exposed; hero entered car |
| `engine_started` | optional, only with stalled→running + RPM evidence |
| `rollout_started` | motion begins in pit lane or from grid; safer fallback than engine claim |
| `out_lap_preparation` | Practice/Qualifying pit exit starts an out-lap FSM |
| `out_lap_field_context` | strength/traffic fact not already exposed in this stint |
| `returned_to_car` | lobby/garage→car after a completed Practice or setup break |

The semantic keys include the exposed topic, not just the node. Re-entering the car must not replay
location, weather and SoF unless their material revisions changed.

### 14.3 Race grid and start

| Proposed node | Meaning / evidence |
| --- | --- |
| `race_quali_recap_result` | hero qualifying position/time from same-stream `QualiBag` |
| `race_grid_field` | class/overall grid size and hero start position |
| `race_grid_highest_rated` | named highest-iRating entrant, explicitly heuristic context |
| `rolling_start_setup` | `StandingStart == 0` plus parade/pacing corroboration |
| `formation_lap_preparation` | car/field preparation while `SessionState == ParadeLaps` |
| `formation_lap_tension` | approach to S/F; optional held HR band/trend |
| `standing_start_setup` | `StandingStart != 0`, before start-ready |
| `start_lights_ready` | start-ready bit edge |
| `start_lights_set` | start-set bit edge; short line or deliberate silence |
| `race_green` | existing green semantics; critical event, never filler |

Long filler is forbidden once `startReady` or `startSet` is active. At that point the Director
reserves the channel for start-light/green commentary. For a rolling start, tension increases only
after a held near-line condition, for example `SessionState == ParadeLaps`, valid `LapDistPct`,
moving car, and estimated distance/ETA below a replay-calibrated threshold.

### 14.4 Session conclusions

| Proposed node | Result branch |
| --- | --- |
| `practice_checkered_summary` | elapsed/checkered plus laps or best time when valid |
| `practice_value_debrief` | neutral value-of-practice story; no unsupported setup improvement |
| `practice_lobby_break` | quick return to lobby: setup/sim adjustment stated as possibility, not fact |
| `quali_result_pole` | class P1 |
| `quali_result_podium` | class P2–P3 |
| `quali_result_top_third` | top third excluding podium |
| `quali_result_middle_third` | middle third |
| `quali_result_rear_third` | final third |
| `quali_to_race_bridge` | result-aware preview of the race, no prediction |
| `race_result_win` | confirmed class P1 |
| `race_result_podium` | confirmed class P2–P3 |
| `race_result_gain_vs_quali` | confirmed finish better than same-stream qualifying result |
| `race_result_loss_vs_quali` | confirmed finish worse than qualifying result |
| `race_result_hold_vs_quali` | equal result |
| `race_result_unclassified` | no confirmed classification; never force a third-band story |
| `stream_chapter_bridge` | next-session/closing handoff while OBS stream remains active |

Result emotion changes style, not truth. “Disappointment” is an editorial tone for a confirmed
worse result; it must not assign blame. A win/podium branch takes precedence over relative gain or
loss. If the same-stream qualifying bag is missing or belongs to another class/run, compare against
the captured race start grid only under a separately named `*_vs_grid` branch.

### 14.5 Optional external and system filler families

These are lower-tier, opt-in and never required for a complete intro:

| Proposed node | Candidate fact |
| --- | --- |
| `channel_last_public_stream` | elapsed time since latest completed public stream |
| `channel_stream_cadence` | factual count of completed public streams in a fixed recent window |
| `channel_returning_venue` | last public stream at the same venue, if title/metadata mapping is reliable |
| `hero_recent_iracing_result` | last authorized iRacing result, category and finish |
| `hero_recent_form` | bounded factual sample such as top-five count in last N results; no prediction |
| `rival_rematch` | both `UserID`s occurred in an authorized previous result |
| `field_geography` | count by verified profile/flag region; never infer nationality from name/club |
| `series_context` | series, season and race-week metadata from iRacing Data API |
| `track_history_context` | authorized prior hero starts/results at this track |
| `system_rig_profile` | explicitly configured CPU/GPU/device names, once per stream |
| `system_load_context` | sustained measured load/FPS band, rare and Practice-biased |
| `prepared_filler_fatal_notice` | fixed operational notice; no factual slots; once per fatal episode |

External copy must say what the data proves. “The last public stream ended eight days ago” is
valid; “streams every week” requires an explicit cadence rule and sufficient history. “A Czech
driver” requires a verified country/profile field, not `ClubName` or name inference.

`prepared_filler_fatal_notice` belongs to the `system` family, is allowed in every active editorial
stage and has a semantic key containing `fatal_episode`. It sits below all live occurrence/story
tiers and above ordinary silence. It bypasses both the prepared-text validator and LLM polish, but
still passes the normal authored-node structural/TTS validator. Speaking starts the episode's one
notice lease; selection or queueing alone does not consume it.

## 15. Stage orchestration and interruption

### 15.1 Required stage model

```text
INACTIVE
  -> WAIT_CONTEXT
  -> STREAM_LOBBY_INTRO
  -> SESSION_EVENT_INTRO
  -> IN_CAR_PREP
  -> OUT_LAP                    (Practice / Qualifying)
  -> GRID_PREP                  (Race)
  -> FORMATION_OR_LIGHTS        (Race)
  -> LIVE_SESSION
  -> SESSION_CONCLUSION
  -> BETWEEN_SESSIONS
```

Stage is a deterministic eligibility dimension, not a new editorial score. A node outside its
allowed stage is unavailable regardless of its fatigue or silence bonus.

One producer-side `EditorialStageController` under `race/` owns this state. It consumes normalized
OBS stream epoch, session identity/type/state, hero seat/on-track/pit state, flags, lap wrap,
`player_finished`, disconnect quality and run resets. It publishes an immutable
`EditorialContextRevision`; neither `PreparedFillerCoordinator`, the graph nor the TTS worker may
infer or mutate the stage. Every transition increments `stage_epoch`, and all queued/generated
plans retain the epoch under which they were made.

Normative transitions and side effects:

| Current | Guard / accepted edge | Next | Required invalidation or carry |
| --- | --- | --- | --- |
| `INACTIVE` | OBS streaming rising edge | `WAIT_CONTEXT` | start new `stream_epoch`; clear all old scopes |
| `WAIT_CONTEXT` | stable session key/type/venue and usable data quality | `STREAM_LOBBY_INTRO` | build stream/session plans |
| any active stage | OBS stop confirmed | `INACTIVE` | cancel tasks; clear buffer and exposure |
| any active stage | disconnect/stale beyond existing grace | `WAIT_CONTEXT` | expire session/run/stint plans; retain only valid stream/external cache |
| `STREAM_LOBBY_INTRO` | hero enters Practice | `STREAM_LOBBY_INTRO` draining | finish the assembled intro chain; remember latest physical state |
| `STREAM_LOBBY_INTRO` | hero enters Qualifying/Race | `SESSION_EVENT_INTRO` | cancel uncommitted stream-intro plans; retain the currently speaking lease |
| `STREAM_LOBBY_INTRO` draining | chain completes | physical-state-derived stage | go to `IN_CAR_PREP`, `OUT_LAP` or `LIVE_SESSION` without replaying skipped edges |
| `SESSION_EVENT_INTRO` | session-specific chain completes or rollout begins | `IN_CAR_PREP` / `OUT_LAP` / `GRID_PREP` | expire remaining event-intro plans |
| `IN_CAR_PREP` | confirmed P/Q pit-road falling edge | `OUT_LAP` | increment `stint_epoch`; create one out-lap episode |
| `OUT_LAP` | valid S/F wrap | `LIVE_SESSION` | expire unused out-lap plans |
| `OUT_LAP` | pit return/tow/reset/run/session change | matching safe stage | expire the out-lap scope without claiming a lap |
| `GRID_PREP` | ParadeLaps/rolling formation or standing-start preparation | `FORMATION_OR_LIGHTS` | keep only start-compatible plans |
| `FORMATION_OR_LIGHTS` | green/Racing accepted | `LIVE_SESSION` | expire every unused pre-start plan |
| P/Q active stage | checkered/end accepted | `SESSION_CONCLUSION` | result-specific plan waits for confirmed result; generic debrief may generate immediately |
| Race active stage | `player_finished` accepted | `SESSION_CONCLUSION` | freeze confirmed finish and comparison inputs |
| `SESSION_CONCLUSION` | conclusion exhausted plus lobby/new session | `BETWEEN_SESSIONS` | retain exposed topics and same-stream `QualiBag` only |
| `BETWEEN_SESSIONS` | stable next session | `SESSION_EVENT_INTRO` | new session/stage epoch; preserve stream scope |

“Stable” means the existing session/reconnect debounce has accepted the value; this controller does
not invent a second raw-iRSDK debounce. If several guards become true on one tick, terminal stream
stop/reset wins, then confirmed finish/checkered, then green/start, then seat/pit/lap movement. The
ordered result is deterministic and covered by table tests.

Completion known only by the commentary lane returns through one bounded typed feedback queue, not
through a callback into producer state:

```python
@dataclass(frozen=True, slots=True)
class EditorialStageFeedback:
    stream_epoch: int
    stage_epoch: int
    action: Literal["intro_chain_completed", "conclusion_exhausted"]
    observed_monotonic_ms: int
```

`RaceRuntime` drains this queue once before the next context capture. Feedback with a different
stream/stage epoch is stale and ignored. The queue is replace-latest per action and bounded to four
items. This keeps the stage producer-owned while allowing real TTS/graph completion to close a
stage. OBS integration must supply both `notify_obs_stream_started()` and the matching
`notify_obs_stream_stopped()`; neither the commentary consumer nor YouTube cache may infer stream
state.

### 15.2 Stream intro rules

1. The OBS streaming rising edge opens `STREAM_LOBBY_INTRO` only after iRSDK provides a stable
   session/venue context. A slot-free welcome may speak immediately; fact-rich plans wait in the
   background buffer.
2. Venue, conditions and field plans are marked exposed by semantic key when speech starts.
3. Entering the car in **Practice** lets the currently assembled Stream Intro chain finish.
4. Entering the car in **Qualifying or Race** lets only the currently speaking prepared filler
   finish. Remaining Stream Intro plans are cancelled or demoted and the stage moves to the
   session event intro.
5. “Current sequence” means one committed two-to-five-sentence TTS unit. There is no clause-level
   preemption.
6. A hero-order change, safety-critical interruption or explicit TTS stop keeps the existing hard
   preemption rules; the Practice exception does not override them.
7. There is no predicted-finish/deadline admission rule in the first implementation. Eligibility is
   checked at commit; an already speaking unit keeps its normal narrative lease. Start/green and the
   existing hard-interrupt classes remain authoritative. Session tape records any stage boundary
   crossed while the unit was audible so the policy can be calibrated from tests rather than guessed.

For Practice, “assembled chain” is frozen on the accepted enter-car edge: it contains the eligible
stream-intro plan ids already ready, queued or in flight for that `stage_epoch`. No later context
revision appends another intro topic. The drain completes after every frozen plan was spoken,
expired, invalidated or exhausted; bounded generation attempts therefore prevent an infinite wait.
The fatal notice rule still applies if all remaining eligible plans exhaust and the buffer is empty.

### 15.3 Session event intro after interruption

The event intro receives an exposure mask for venue, conditions, overall field, hero class and
external colour:

- unexposed still-valid topics may be assembled from their ready buffers;
- exposed topics are not regenerated merely to produce a different sentence;
- if all useful topics were already spoken, select `hero_prepares_to_drive` or `rollout_started`;
- if the engine/motion transition arrives while a prepared filler is speaking, finish that unit
  and do not start another pre-drive unit;
- once the car leaves the pit lane/grid, all remaining pre-drive fillers expire.

This replaces the current 120-second one-winner `OpenerMutex` for buffered mode. Compatibility
`legacy` behavior can retain the mutex; active buffered mode needs an explicit sequence owner rather
than several sidecars suppressing each other.

### 15.4 Practice and Qualifying out laps

Every confirmed pit-road falling edge opens a new stint-scoped out-lap episode. It ends on the
first valid start/finish wrap, return to pit road, tow/reset, disconnect, session end or run reset.
The graph may select one prepared out-lap unit, normally preparation first and contextual field or
quiet-track colour second. A live battle/timing fact always outranks it.

### 15.5 Race start

- Generate the qualifying recap immediately after a stable Qualifying result and retain it in
  stream memory for the following Race session.
- Build grid/field/start-mode plans while in lobby, before the hero enters the car.
- Rolling starts allow bounded formation filler until the near-line tension window.
- Standing starts allow setup copy only before the start-ready edge; after ready/set, prefer a
  short beat or silence so `GREEN` is not delayed.
- Green invalidates every unused grid/formation filler except a fact explicitly designed as a
  post-start result.

The version-one rolling near-line guard requires `SessionState == ParadeLaps`, valid forward speed
for two continuous monotonic seconds, parsed track length and a computed ETA to the next S/F wrap of
at most 12 seconds. Missing or implausible inputs disable `formation_lap_tension`; they do not select
a percentage-only substitute. These values are initial testable policy and may be changed only from
retained replay/live evidence.

### 15.6 Session conclusions

Practice/Qualifying conclusion begins at the session checkered/end state because there is no
race-finish lease to preserve. That edge may immediately prepare a generic closing plan, but a
position/result branch remains ineligible until its own confirmed-result snapshot arrives. After
eight monotonic seconds it stays generic; it never reuses the last live position as a final result. Race
conclusion begins only when `player_finished` confirms hero finish. A quick return to lobby is a
state transition, not evidence that setup was changed; copy may say there is time to adjust
settings, never that an adjustment occurred.

## 16. Selection policy by stage

The existing strict editorial tiers remain authoritative. Suggested filler priorities are relative
only within the prepared/context tier:

| Stage | First choice | Second choice | Expire/suppress |
| --- | --- | --- | --- |
| initial lobby | venue | conditions, field | old session/result copy |
| late lobby | field/class | external channel/series colour | venue already exposed |
| hero enters Practice | finish current intro | out-lap preparation | do not cancel current unit |
| hero enters Qualifying | finish current unit | qualifying event intro | cancel remaining stream-intro chain |
| hero enters Race | finish current unit | quali recap/grid/start mode | cancel remaining stream-intro chain |
| out lap | preparation | quiet-track/field context | after S/F wrap |
| formation | grid/start | HR-coloured near-line tension | long copy near lights/line |
| live race | real event/story | truthful silence filler | all pre-start plans |
| session ending | confirmed result | debrief/next-session bridge | generic weather/field filler |

The graph score still considers semantic fatigue, path fatigue, material change and silence. Stage
eligibility and strict event tier are hard gates before that score.

### 16.1 Rollout modes and authoritative behavior

The feature has one rollout switch, independent of `commentary.graph_runtime.mode`:

| `prepared_filler.mode` | Audible owner | Generation and validation | Exposure/diagnostics |
| --- | --- | --- | --- |
| `legacy` | existing session briefs/filler path | off; tasks and buffer absent | compact disabled status only |
| `shadow` | existing legacy path | full plan build, LLM generation, validation, expiry and virtual selection | records both legacy exposure and the shadow winner; never enqueues prepared text or fatal notice |
| `active` | prepared path for the families in §14; legacy filler nodes disabled | full | actual speaking lifecycle owns exposure; fatal notice enabled |

Live occurrence and story commentary remain on the existing accepted-event/Director/TTS path in all
three modes. `active` replaces only overlapping intro/context/out-lap/start/conclusion filler
ownership; it does not disable or duplicate race-event speech. A config reload may move
`legacy -> shadow -> active` or back. Every change cancels old generation tasks, increments a
coordinator epoch and clears incompatible buffer entries before the new mode is observed.

The implementation now starts in `active` whenever master commentary is enabled. The private test
broadcast therefore exercises prepared selection and TTS directly. `shadow` remains available for
targeted diagnostics and `legacy` remains a tested immediate rollback for at least one
compatibility release.

### 16.2 Deterministic arbitration order

Candidates are filtered and ranked in this order:

1. reject wrong stream/session/run/stint scope, stale revision or wrong stage;
2. preserve the currently speaking narrative lease unless an existing hard-interrupt class wins;
3. rank accepted live occurrence/story candidates above all prepared and operational candidates;
4. rank current-stage required prepared families above optional/external families;
5. let `SequenceGraphRuntime` choose within a tier using transition, closure, material-change,
   silence and fatigue terms;
6. after the semantic plan wins, let `PreparedFillerBuffer` choose its least-exposed valid wording;
7. commit-revalidate the plan, then enqueue one TTS unit and mark exposure only on `speaking`;
8. if no valid prepared plan exists and health is newly `fatal`, offer the one operational notice;
   otherwise remain silent.

This order is normative. The coordinator may precompute candidates but may not create a second
priority queue that bypasses graph selection.

## 17. Deterministic result bands

Use class position and eligible class size whenever the event is multiclass. Let
`third = ceil(class_size / 3)`:

1. pole/win: position 1;
2. podium: positions 2–3, bounded by field size;
3. top third: position 4 through `third`;
4. middle third: `third + 1` through `2 * third`, clipped to field size;
5. rear third: remaining classified positions.

For fields smaller than six, skip generic thirds and use only win/podium/classified. The exact
boundary must be covered by table tests for sizes 1–12.

Race comparison order:

1. win/podium branch;
2. same-stream, same-class `QualiBag` comparison;
3. captured race start-grid comparison under explicitly named `vs_grid` branch;
4. classified absolute band;
5. unclassified/unknown fallback.

No branch may treat checkered as a classification or use a stale qualifying bag from another
subsession/class.

## 18. External-source design

### 18.1 Broader use of the existing YouTube login

The requested feature does **not** require multiple YouTube accounts or OAuth identities. It should
reuse the one account already authenticated by the dashboard and extend that integration from the
currently selected broadcast to read-only public stream history for the same channel. No profile
registry, additional token path or account selector belongs in this scope.

Proposed read-only flow for the existing authenticated channel:

1. reuse the existing `OAuthManager` and token path;
2. `channels.list(mine=true, part=contentDetails)` to obtain that channel's uploads playlist;
3. page `playlistItems.list(part=snippet,contentDetails,status, maxResults=50)` only until the
   configured history horizon or item cap is reached;
4. one batched `videos.list(part=snippet,status,liveStreamingDetails,contentDetails)` for candidate
   IDs;
5. accept only `status.privacyStatus == public` completed broadcasts with
   `liveStreamingDetails.actualEndTime`;
6. key the cache by authenticated channel id and source revision, never by OAuth identity count;
7. refresh before the stream and then at a bounded interval; never call YouTube from candidate
   selection or wait for it at stage transition.

The repository already requests `https://www.googleapis.com/auth/youtube`, which includes these
read operations because VOD chapter writing needs the broader scope. Therefore this feature adds
no second login and no new OAuth scope. A previously stored readonly token is also sufficient for
history reads; write-scope reauthorization remains a separate VOD-chapter concern.

Google explicitly recommends the uploads-playlist path for reliable recent uploads, and
`playlistItems.list` costs one quota unit. See
[channel uploads](https://developers.google.com/youtube/v3/guides/implementation/videos),
[playlistItems.list](https://developers.google.com/youtube/v3/docs/playlistItems/list), and
[video live metadata](https://developers.google.com/youtube/v3/docs/videos).

Safe derived facts:

- time since latest completed public stream;
- number of completed public streams in the last 30/90 days;
- median interval only with at least four qualifying streams;
- last same-venue stream only when venue matching uses configured track aliases, not fuzzy LLM
  guessing.

Do not expose private/unlisted history, titles from unrelated channels, or subscriber/view
comparisons. Multi-account support is a separate product feature and is not implied by this filler
scenario.

### 18.2 iRacing Data API

The Data API is an authenticated enrichment source, not a live detector. OAuth access is documented
by iRacing's [Data API workflow](https://oauth.iracing.com/oauth2/book/data_api_workflow.html).
The non-negotiable external prerequisite is an iRacing-issued OAuth client registered with audience
`data-server`. As verified on 2026-09-04, iRacing's
[client-registration page](https://oauth.iracing.com/oauth2/book/client_registration.html) says
creation of new OAuth client IDs is paused. Live integration is therefore possible now only if an
appropriate client ID already exists; fixtures and the internal adapter can be implemented without
it, but live authorization/acceptance cannot be completed.

This application must use a separate `IracingOAuthManager`; the Google/YouTube manager cannot be
reused because hosts, scope, token response and refresh semantics differ. Required flow:

1. Authorization Code flow with PKCE `S256`, state/CSRF verification and an exactly registered
   loopback redirect such as `http://127.0.0.1:17321/iracing/oauth/callback`;
2. request only `iracing.auth` for Data API access;
3. exchange the code at `https://oauth.iracing.com/oauth2/token` and treat access/refresh tokens as
   opaque values;
4. use the returned `expires_in` and `refresh_token_expires_in`, never assumed lifetimes;
5. rotate refresh tokens atomically: each refresh token is single-use and the newly returned token
   must replace it before another refresh can start;
6. send the access token only as `Authorization: Bearer ...` to the iRacing resource server;
7. on `invalid_grant`/revocation, clear only iRacing credentials and require interactive reauth;
   never fall back to storing or submitting the member password.

If iRacing issues a confidential-client secret, it is supplied only through a dedicated environment
variable and masked exactly as required by the token endpoint; it is never committed or put in the
public INI example. A distributed/native build should prefer a public PKCE client with no embedded
secret, subject to the client type issued by iRacing.

Endpoint names below are a discovery shortlist, not an approved slot contract:

| Desired fact | Endpoint(s) to inspect in authenticated `/data/doc` | Minimum normalized output |
| --- | --- | --- |
| hero recent result/form | `stats/member_recent_races`, then `results/get` when detail is needed | subsession, date, series/category, track id, class start/finish, classified flag |
| repeat rival | `results/get` for bounded recent hero subsessions | exact customer ids in the same result; no name-only match |
| track history/alias | `track/get` plus hero result sample | stable track/config ids and official names |
| series/week context | `series/get` and relevant season/lookup document | stable ids and official display metadata |
| profile enrichment | member endpoints exposed by the authenticated document | only explicitly documented country/profile fields; never club-as-nationality |

For every chosen method, retain a redacted successful schema fixture, empty result, permission error,
rate-limit response and linked-payload/expiry example before its propositions or graph node are
enabled. Record field nullability, units, pagination, result classification semantics, response
expiry and whether the first response contains data or an expiring download link. Unknown/schema-
drifted fields disable only their dependent proposition.

Use it to prepare cached, source-stamped facts about prior results, repeat rivals, series/track
metadata and profile flags. The exact response fields and privacy behavior must be captured from
the authenticated `/data/doc/<service>/<method>` response before any slot is approved. The initial
implementation must not promise nationality: the current repository deliberately stores it as
`None`, and club/region is not equivalent.

Rate limits, auth loss and delayed results are normal. Cache with endpoint-provided expiration,
bound concurrency, honor `Retry-After`/rate-limit headers, redact tokens/customer data outside the
minimum fact set, and never hold up stream/session intro waiting for an API. Refresh runs at startup,
before the stream when possible and after a known completed result; it never runs from candidate
selection or the telemetry loop.

### 18.3 Sysinfo

Reuse current `SystemState` for sustained CPU/GPU/RAM/FPS bands. If human-readable hardware names
are desired, add a separate opt-in static `RigProfile` loaded at startup or explicitly configured.
Do not infer a model name from sensor labels in the commentary path and do not read machine/user
names. Suggested usage:

- `system_rig_profile`: once near the beginning of a long Practice stream;
- `system_load_context`: only after a held healthy/high load band and only when no race story is
  active;
- performance degradation warnings stay operational diagnostics unless explicitly approved as
  viewer content.

### 18.4 Source failure matrix

| Source | Failure or absence | Required runtime behavior |
| --- | --- | --- |
| iRSDK/session snapshot | missing optional field | omit only that proposition and dependent plan; no guess |
| iRSDK/session identity | stale/disconnected beyond accepted grace | move to `WAIT_CONTEXT`; expire session/run/stint plans |
| YouTube | OAuth absent/revoked, quota, timeout, malformed item | keep last unexpired cache or omit YouTube plans; never fatal by itself |
| iRacing Data API | auth/rate limit/redirect payload failure | omit enrichment; never affect a live detector or core plan |
| Sysinfo | sensor missing/stale | omit the affected metric/plan; no hardware inference |
| LLM | timeout/transport/invalid JSON/grounding rejection | bounded attempts; no candidate until all 3–5 variants validate |
| LLM plus empty eligible buffer | every eligible current-stage plan exhausted | enter `fatal`; offer the fixed notice once; then silence filler until recovery |
| TTS | fatal notice cannot be spoken | record failed lifecycle; do not retry-loop or block live commentary |

## 19. Runtime ownership and file plan

The implementation extends existing owners; it does not introduce another event bus, Director or
TTS queue.

| Responsibility | Planned owner | Existing integration point |
| --- | --- | --- |
| raw iRSDK/session extraction | `iracing/editorial_facts.py` | reuse `session_context`, `weather`, `drivers`, `sdk_units` helpers |
| material revisions and immutable fact ledger | `race/editorial_context.py` | `RacePipeline.build_context_payload()` publishes it in N12 context |
| authoritative stage and out-lap/start FSM | `race/editorial_stage.py` | `RaceRuntime` feeds accepted normalized state/edges |
| plan inventory and proposition selection | `commentary/filler_plans.py` | pure builder from `EditorialContextRevision` |
| bounded buffer, generation ownership and health | `commentary/prepared_filler.py` | owned by `CommentaryConsumer.run()` and closed in its `finally` |
| OpenAI-compatible generation adapter | `commentary/prepared_generation.py` | reuse commentary LLM endpoint/model settings; async HTTP only |
| graph eligibility and semantic selection | existing `graph.py`, `graph_runtime.py`, `sequence_graph.json` | add §14 nodes/edges, no second scorer |
| final commit and TTS | existing `director.py`, `tts.py` | prepared flag bypasses per-utterance LLM polish; lifecycle marks exposure |
| YouTube history cache | `commentary/sources/youtube_history.py` | `main.py` injects existing `OAuthManager`; source never imports server globals |
| iRacing OAuth and HTTP/cache | new `iracing_data/oauth.py`, `client.py`, `cache.py` | separate PKCE/token rotation and external-data owner; `main.py` wires namespaced routes |
| commentary projection of iRacing history | `commentary/sources/iracing_history.py` | converts a frozen cache snapshot into optional propositions after schema evidence |
| diagnostics | existing `overlay/tape.py`, commentary status API | hashes/ids/counters only; no tokens or full prompts |

The producer remains the only owner of stage and factual revisions. The commentary consumer owns
all LLM tasks because it can lag/fail without delaying telemetry, event arbitration or overlay.
`ProcessTtsSink` must never call the LLM again for `prepared=True`; the text was already generated
and validated. The fixed fatal node is also `prepared=True` and authored locally.

### 19.1 Configuration contract to implement

Add an optional INI section with these first-version defaults:

```ini
[commentary.prepared_filler]
mode = shadow
max_ready_plans = 24
reserved_current_stage = 8
reserved_next_stage = 6
max_inflight = 2
variants_min = 3
variants_max = 5
generation_timeout_s = 30.0
generation_max_attempts = 2
max_utterance_s = 28.0
youtube_history = false
youtube_history_days = 90
youtube_history_max_items = 100
iracing_history = false
system_filler = false
```

Optional iRacing history uses a separate source section:

```ini
[iracing_data]
enabled = false
client_id =
redirect_uri = http://127.0.0.1:17321/iracing/oauth/callback
request_timeout_s = 10.0
recent_results_limit = 20
cache_max_entries = 200
```

`IRACING_OAUTH_CLIENT_ID` and `IRACING_OAUTH_REDIRECT_URI` may override the non-secret values.
`IRACING_OAUTH_CLIENT_SECRET`, only if iRacing issued one, is environment-only. Tokens live in a
separate `data/iracing_oauth_token.json`, are written atomically with restrictive best-effort file
permissions and are never exposed through config reload, API status, logs or tape. Dashboard routes
are namespaced `/iracing/oauth/initiate`, `/iracing/oauth/callback`, `/iracing/oauth/status` and
`/iracing/oauth/disconnect`; the existing YouTube `/oauth/*` contract remains unchanged.

`mode` is clamped to the closed set in §16.1; an unknown value logs a config warning and resolves to
`legacy`. Numeric limits are clamped to safe bounds (`max_ready_plans` 3–64, reservations not above
capacity, `max_inflight` 1–4, variants fixed within 3–5, timeout 2–120 s, attempts 1–3,
utterance 8–40 s, history 7–365 days and 10–500 items). Generation reuses `llm_base_url`,
`llm_model` and `llm_temperature`; it does not reuse the 14-second live-utterance cap or invoke the
existing per-speech polish path.

For `[iracing_data]`, request timeout is clamped to 2–30 s, result limit to 1–100 and cache entries to
20–1000. `enabled=true` without a client ID produces source status `not_configured`, not a startup
failure. `commentary.prepared_filler.iracing_history=true` consumes facts only when the source is
enabled, authorized and fresh.

Migration: absent section means `shadow` on the implementation branch and does not alter audible
output. The later default change to `active` is a separate reviewed config behavior change after
§23. `legacy` restores the old filler path without deleting collected tapes or external caches.

### 19.2 Status and tape contract

`GET /commentary` adds a compact `preparedFiller` object:

```json
{
  "mode": "shadow",
  "health": "ready",
  "stage": "STREAM_LOBBY_INTRO",
  "stageEpoch": 4,
  "contextRevision": "sha256:...",
  "readyPlans": 7,
  "queuedPlans": 2,
  "inflight": 2,
  "rejected": 1,
  "staleDropped": 0,
  "fatalEpisode": 0,
  "fatalNoticeSpoken": false,
  "lastErrorCode": null,
  "sources": {"irsdk": "ready", "youtube": "disabled", "iracing": "disabled"}
}
```

Tape rows use type `prepared_filler` and actions `context`, `plan_queued`, `generated`, `rejected`,
`stale_dropped`, `shadow_selected`, `shadow_compared`, `selected`, `speaking`, `completed`, `interrupted`, `fatal` and
`recovered`. Each row carries mode, stage/epoch, context revision, plan/node/semantic ids, source
revision hashes, attempt, latency, reason code and counts where applicable. Shadow selection also
carries the legacy spoken node/semantic id when one exists and classifies divergence as
`same_semantic`, `different_semantic`, `shadow_only`, `legacy_only`, `not_eligible` or `not_ready`.
Raw prompts, generated variants, OAuth material and full external payloads are excluded from the
status and default INFO tape; generated text already follows the existing DEBUG commentary policy.

## 20. Ordered implementation slices

Every slice is test-first, leaves the main loop runnable and updates this document's evidence table.
Slices 0–5 form the required core vertical cut; slice 6 is optional enrichment and cannot block
activation of core iRSDK-based filler.

### Slice 0 — contract fixtures and characterization

- Add synthetic/malformed fixtures for Practice, Qualifying, rolling/standing Race, AI and
  multiclass before writing extractors.
- Characterize current opener, filler watchdog, graph and TTS lifecycle in `legacy`.
- Define AC/test/docs/config in the implementation issue and record the baseline test count.
- Live stream-PC captures are collected during implementation/test; lack of an earlier capture does
  not block coding. Every unverified field stays nullable and fail-soft until a capture proves it.

**Exit:** fixtures fail for the missing normalized facts; legacy characterization remains green.

### Slice 1 — active normalized context and stage FSM, no new speech

- Implement venue/light/rubber/field/AI/start-mode/traffic/result propositions and material hashes.
- Implement `EditorialStageController`, including stream stop/reset, Practice drain,
  Qualifying/Race cutover, out-lap, formation/lights, green and conclusion transitions.
- Publish the immutable revision in every N12 context and expose current stage in status/tape.

**Exit:** table tests cover every §15 transition, malformed/missing iRSDK input never raises into the
race loop, and poll frequency does not change the semantic revision sequence.

### Slice 2 — complete shadow pipeline

- Implement plan builder, bounded generation queue, 3–5 variant validator, buffer replacement,
  low-water refill, material-change regeneration, expiry, cancellation and health state machine.
- Run actual async LLM generation in `shadow`; keep legacy audible.
- Perform virtual graph selection and update shadow exposure from what the legacy audience really
  heard, so later shadow scores model the same history.
- Implement fatal detection in diagnostics, but never offer the audible fatal notice in shadow.

**Exit:** shadow diagnostics are reconstructable from tape and never reach TTS; limits remain 24/2
under churn; stop/reset leaves zero owned tasks. This optional diagnostic slice is not a prerequisite
for the active private-stream run in §23.

### Slice 3 — active Stream Intro vertical cut

- Add venue/conditions/surface/field/class/AI nodes and the fixed fatal-notice node.
- Route already prepared text through Director -> graph -> commit -> TTS with no second LLM call.
- Replace only overlapping legacy opener/filler ownership in `active`.
- Implement semantic exposure on `speaking`, recovery rearm and one notice per fatal episode.
- Implement Practice finish-chain and Qualifying/Race finish-current-unit behavior.

**Exit:** lobby-to-car replays prove correct ordering/interruption; LLM exhaustion + empty buffer
speaks exactly one localized fatal notice, then filler silence; live events remain audible.

### Slice 4 — event intro, out lap and race start

- Add event-intro, prepare/rollout, out-lap, quali recap/grid/start and formation nodes/edges.
- Pre-generate current/next stage plans using reserved capacity.
- Enforce no long filler after start-ready/set and immediate expiry at green.

**Exit:** Practice/Qualifying pit-exit and rolling/standing start replays pass, including reset,
return-to-pits and green while a unit is speaking.

### Slice 5 — session conclusions and complete core cut

- Add Practice debrief, Qualifying result bands/bridge and Race result/comparison branches.
- Wait for confirmed result identity; use generic close after bounded wait, never last live position.
- Preserve same-stream `QualiBag` only across its allowed class/session boundary.

**Exit:** all §17 table cases and P/Q/R end-to-lobby paths pass; the core feature can run in active
without YouTube, iRacing Data API or hardware-profile facts.

### Slice 6 — optional external colour

- Add one-channel YouTube public history cache first, then its three nodes.
- Implement the iRacing OAuth/client/cache behind `enabled=false` with fixture tests; live OAuth is
  blocked until an issued `data-server` client ID and exact redirect URI are available.
- After live authorization, capture and review the authenticated `/data/doc` schemas listed in
  §18.2, then enable only the approved normalized fields and corresponding graph nodes.
- Add system filler last; static rig identity is explicit opt-in config, never machine discovery.

**Exit:** source outages exercise §18.4, OAuth rotation and cache bounds/expiry are tested, disabling
each source removes only its own plans, and the retained schema/evidence contains no token or
unnecessary personal data. If client registration remains unavailable, this slice may merge
disabled with fixture evidence but cannot claim live acceptance or enable iRacing history.

### Slice 7 — active live calibration

- Run the §23 matrix audibly in `active` on the private test broadcast.
- Adjust only documented thresholds, wording/style cards and graph policy based on evidence.

**Exit:** retained active-run evidence is classified; `legacy` rollback test stays green.

## 21. Test plan

### Unit

- every new source parser, unit, enum and missing/sentinel rule;
- wetness versus rubber-state separation and material threshold boundaries;
- AI detection independent of SoF; overall/class roster digests and unofficial SoF sample counts;
- highest-iRating wording never becomes a prediction and licence never changes its rank;
- light bands, traffic hold, out-lap FSM, start-mode and start-light edges;
- result thirds for class sizes 1–12 and same-stream Qualifying/Race identity;
- every stage transition and simultaneous-guard precedence from §15;
- stable plan/context ids, buffer reservations/bounds/replacement/expiry and stale-result dropping;
- per-situation 3–5 distinct variants, non-selectable 0–2 sets, refill toward five,
  material-change regeneration, sentence/duration/grounding rejection and bounded attempts;
- playback raises exposure without deleting a variant or causing an unbounded generation loop;
- every health transition, one fatal notice per episode and recovery rearm;
- exact semantic exposure: once at `speaking`, never at generation/selection/queueing;
- config defaults, clamps, reload mode changes and legacy rollback.
- iRacing OAuth PKCE/state, exact redirect, optional response fields, atomic single-use refresh-token
  rotation, invalid-grant cleanup and simultaneous refresh single-flight;
- iRacing Data response/link expiry, pagination, rate-limit/backoff, cache bounds, schema drift and
  redaction using HTTP fixtures only—never a real member account in pytest.

### Integration/replay

- stream starts in lobby with late weather/roster facts;
- Practice enter-car drains the assembled intro; Qualifying/Race finishes only the current unit;
- event intro contains only still-valid, unexposed facts;
- engine/motion edge while speaking prevents another pre-drive unit;
- every P/Q pit exit creates one out-lap episode and expires at S/F, pit return, reset or disconnect;
- rolling and standing starts choose different paths; no long filler begins after ready/set;
- green and live race events outrank prepared and fatal-notice candidates;
- Practice/Qualifying/Race conclusions select the right confirmed result branch;
- poll-frequency changes preserve the accepted semantic sequence;
- LLM errors with a nonempty buffer use the buffer and do not announce fatal;
- LLM exhaustion with an empty eligible buffer announces once, then stays silent until recovery;
- YouTube/iRacing/Sysinfo failure leaves core plans and live commentary running;
- iRacing authorization absent/revoked and stale cache remove only iRacing propositions;
- reset/disconnect/config reload cannot revive an old plan or leave an owned task alive;
- `shadow` produces no TTS enqueue while logging a virtual winner and legacy comparator.

### Manual Windows/OBS/Ollama

Retain video, tape, status snapshots and spoken semantic timeline for:

1. Practice with few cars, two pit exits and a quick lobby/setup break;
2. Qualifying entered before Stream Intro completes;
3. rolling Race with formation-lap HR rise near S/F;
4. standing Race with ready/set/green timing;
5. multiclass Race where overall and hero-class field facts remain distinct;
6. AI Race with missing iRating/SoF;
7. Qualifying result followed by better, equal and worse Race finish replays;
8. missing weather/rubber/result fields;
9. Ollama timeout with a ready buffer, then exhausted generation with an empty buffer;
10. YouTube absent, revoked, expired and quota/rate-limited;
11. config reload `shadow -> active -> legacy` during generation;
12. OBS stop and iRacing disconnect while two generations are in flight.

## 22. Acceptance criteria

- [ ] **AC1 Grounding:** zero invented numbers, actors, relations, nationality, causality,
  prediction or result certainty in the curated corpus and retained live samples.
- [ ] **AC2 Timing:** zero prepared units begin after their stage/material revision/scope expired.
- [ ] **AC3 Lifecycle:** exposure increments exactly once on audible start, not on generation,
  selection, queueing, rejection or shadow evaluation.
- [ ] **AC4 Completeness:** every concrete eligible microstory situation is maintained independently;
  a ready plan owns 3–5 valid, structurally distinct variants, 0–2 is never selectable, and the
  producer refills valid partial sets toward five.
- [ ] **AC5 Failure contract:** exhausted LLM plus empty eligible buffer enters `fatal`, speaks the
  fixed localized notice exactly once per episode, then filler stays silent until recovery.
- [ ] **AC6 Priority:** critical/live occurrence recall remains 100% and prepared/fatal candidates
  never preempt them in curated replay.
- [ ] **AC7 Repetition:** a semantic intro topic does not repeat without a material revision;
  variant exposure affects wording only.
- [ ] **AC8 Isolation:** no external request or LLM call runs on the telemetry loop or blocks N12
  fan-out; every task, queue, store, retry and cache is bounded and cancellable.
- [ ] **AC9 Shadow evidence:** every prepared-vs-legacy difference is reconstructable and classified
  without shadow audio or a second per-speech LLM call.
- [ ] **AC10 Reset safety:** session/run/stint/reset/disconnect/config edges cannot publish or speak
  an older revision.
- [ ] **AC11 Regeneration:** a material situation change atomically invalidates the old plan and
  queues a new situation-specific set; a non-material telemetry change causes no LLM work.
- [ ] **AC12 Source independence:** core active behavior works with all optional external sources
  disabled or failing.
- [ ] **AC13 Rollback:** `legacy` restores current audible filler behavior in one config reload and
  remains covered for the compatibility release.
- [ ] **AC14 Data validation:** normalized iRSDK interpretation is exercised against synthetic,
  malformed and retained live fixtures; absent/unverified fields remove facts instead of guessing.
- [ ] **AC15 Docs/API/config:** operator contract, migration, status payload and tape schema match the
  implementation.

## 23. Active private-stream evidence

The private stream intentionally runs the complete `active` candidate pipeline through TTS. It
must generate, validate, expire, select and commit the same prepared units that will be used in
normal operation. `shadow` is optional diagnostic tooling, not an activation prerequisite.

Evidence to retain and evaluate:

| Gate | Pass condition |
| --- | --- |
| factuality | no accepted variant fails manual proposition audit; every validator rejection has a reason code |
| freshness | zero virtual winner from a stale context/stage/source revision |
| priority | zero case where a prepared candidate displaces an accepted live occurrence/story |
| lifecycle | zero duplicate exposure and zero generated result published after reset/cancel |
| bounds | ready <= 24, in-flight <= 2, queues/caches within documented caps for every sample |
| determinism | same replay/config/LLM fixture yields the same plan ids, eligibility and winner sequence |
| scenario coverage | all 12 manual scenarios have a complete tape or an explicit external-system TDD exception |
| failure behavior | timeout, invalid JSON, grounding reject, auth loss, disconnect and stop match §§12.4/18.4 |
| operations | status identifies mode/health/stage/error; `legacy` rollback succeeds without restart |

No percentage agreement with legacy is required: the feature intentionally changes editorial
coverage. Every unexpected audible or silent decision must be explained as desired change,
missing readiness, wrong eligibility, data defect or policy defect. Thresholds remain the current
design values until this evidence motivates a reviewed adjustment.

## 24. Documentation impact and current verification

Runtime implementation must update together:

- `COMMENTARY_ENGINE.md` — prepared pipeline, stage ownership, fatal notice and legacy boundary;
- `CONFIG.md` + `config/config.example.ini` — §19.1 keys, defaults, clamps and migration;
- `API.md` — §19.2 compact status and tape behavior, never prompts or OAuth secrets;
- `YOUTUBE_API_SETUP.md` — same-account public-history read and failure behavior;
- `docs/scenario_coverage_matrix.md` — intro, out-lap, start, conclusion and fatal coverage;
- `docs/commentary_stateful_sequence_graph_spec.md` — prepared candidates and single fatigue owner;
- this document — slice/AC evidence and final node inventory.

No new dependency is required: the core and optional HTTP clients use existing `aiohttp`. Any
additional dependency or secret-bearing config needs separate review.

**Implementation evidence:** the core runtime now includes current/next-stage reserved generation,
versioned completion feedback, stream/session/run/stage/stint/class plan identity, deterministic
Practice/Qualifying/Race result branches, bounded cancellation and the documented TTS reset/stop
policy. Unit/integration coverage lives in `tests/test_editorial_stage.py`,
`tests/test_prepared_filler.py`, `tests/test_n12_consumers.py`, `tests/test_commentary_tts.py` and
`tests/test_stream_start.py`.

The iRacing Data API connector remains Slice 6 backlog until an issued client ID and OAuth evidence
exist. Active playback is already the default; the retained
[private-stream live matrix](commentary_prepared_active_test.md) is used to find and classify real
OBS/iRacing/Ollama/TTS timing or editorial-quality defects.

The generic prepared graph gateway has been removed from the new runtime path. The 53-node
contract, normalized source facts, graph scoring and remaining live validation are tracked in the
[prepared graph completion plan](prepared_graph_completion_plan.md).

**Known evidence risk:** SessionInfo fields vary by simulator build, session type and arrival time;
the Data API response contract is endpoint/account dependent.

**Mitigation:** implementation starts with nullable fail-soft fields plus synthetic tests and then
adds retained live fixtures. Authenticated iRacing `/data/doc` evidence is required only before its
optional enrichment slice, not before the core runtime implementation.
