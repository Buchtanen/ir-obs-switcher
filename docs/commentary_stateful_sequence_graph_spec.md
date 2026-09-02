# Stateful commentary sequence graph — specification and implementation plan

**Status:** proposed; documentation only, no runtime behavior implemented

**Base branch:** `refactor/200-n12-async-consumers`

**Baseline commit:** `8788f95`

**Tracking context:** [#200](https://github.com/Buchtanen/ir-obs-switcher/issues/200) and the implemented N12 consumer split

**Related:** [Commentary engine](../COMMENTARY_ENGINE.md), [Test 6 analysis](overlay_commentary_test_6_analysis.md), [Test 6 fix plan](overlay_commentary_test_6_fix_implementation_plan.md), [Editorial MiniStory lifecycle](implementation_editorial_ministory.md)

This document specifies a future commentary-policy change. It is not a description of current behavior. Implementation must receive its own issue, acceptance checklist, and PR before any active-mode rollout.

---

## 1. Executive decision

Replace the overlapping commentary-selection policies with one stateful weighted sequence graph owned by `CommentaryConsumer`:

- graph nodes represent speakable editorial beats;
- graph edges represent truthful narrative transitions;
- node, edge, semantic-fact, and short-path visits create decaying repetition fatigue;
- a reserved runtime `SILENCE` node accumulates time-based pressure and promotes suitable factual beats;
- one deterministic score ranks all currently valid commentary candidates;
- only the winner is composed or sent to the LLM;
- the existing `MiniStory` commit gate remains the final factual authority before audio starts.

The graph therefore becomes the single owner of commentary priority, narrative continuation, semantic repetition, cooldown-like behavior, and silence recovery. It does not become the source of race truth, a free-form rule engine, or an external graph database.

The design uses one runtime state object, not two independent editorial memories. Repetition fatigue and silence duration are two dimensions of the same graph traversal state.

## 2. Problem statement

The current commentary path distributes editorial decisions across several mechanisms:

1. accepted envelopes are ordered by `EventEnvelope.priority`;
2. matching graph nodes are ordered by `GraphNode.speak_priority`;
3. `_last` and `_follow_edge()` prefer a matching outgoing edge;
4. `_cooldowns` hard-block individual nodes;
5. `_global_ready_at` controls minimum speech spacing;
6. `RecentUtteranceHistory` reduces exact wording and tail repetition;
7. `SpeechScheduler.silence_due()` triggers a filler request;
8. `RaceObserver.next_filler_envelope()` rotates a separate set of context facts.

Each mechanism is locally reasonable, but together they do not produce one explainable editorial ranking. In particular:

- lexical variation can hide semantic repetition;
- an LLM can restate the same fact with different words and evade the current anti-repeat check;
- graph `speak_priority` does not rank candidates belonging to different envelopes;
- deferred scheduling uses envelope priority rather than the graph's editorial value;
- edge preference can select a node which is then rejected by a hard cooldown without evaluating a useful alternative;
- graph edges mainly reconstruct composer history and only rarely change node selection;
- long-silence handling is enabled only when deferred scheduling is enabled;
- initial silence has no `last_spoke_at`, so the current watchdog does not become due;
- fixed filler rotation does not compare context against an active live story;
- counting pipeline ticks would make behavior depend on sampling rate rather than editorial events.

At the baseline commit the commentary graph has 54 nodes and 24 edges. Twenty-seven nodes participate in at least one edge. Most event types map to one node, so a last-node edge preference often returns the same node that normal priority ordering would already choose.

## 3. Goals

The stateful graph must:

1. make one component responsible for commentary selection;
2. suppress repeated meaning, not merely repeated wording;
3. prefer coherent continuation and closure of an active mini-story;
4. use silence duration to promote relevant facts without fabricating content;
5. preserve unique critical results even after similar earlier commentary;
6. behave identically for the same accepted-event timeline regardless of telemetry polling frequency;
7. preserve N12 producer/consumer isolation and immutable message boundaries;
8. remain deterministic, bounded, observable, fail-soft, and dependency-free;
9. retain the factual revalidation and narrative lease semantics already implemented by `MiniStoryRegistry`;
10. allow tape replay to explain every selected and rejected candidate through a score breakdown.

## 4. Non-goals

- Replacing Event Engine arbitration or `RaceObserver` as the source of truth.
- Moving telemetry predicates, gap validity, position direction, or run detection into JSON.
- Letting the graph choose a fact which is not present in the current immutable context or accepted event stream.
- Replacing `MiniStoryRegistry`, its commit gate, or TTS lifecycle handling.
- Replacing the bounded TTS worker with a speak-all queue.
- Using Neo4j, SQLite, a graph service, a new dependency, or an unbounded graph-search library.
- Creating a user-authored expression language in `sequence_graph.json`.
- Using an LLM to assign scores or decide what is true.
- Guaranteeing continuous speech. When no useful factual candidate exists, silence is correct.
- Persisting runtime visit counters to disk or across process restarts in the first version.
- Removing lexical anti-repeat; semantic graph fatigue and wording diversity solve different problems.

## 5. Fixed design decisions

1. **One runtime owner.** `CommentaryConsumer` owns exactly one `SequenceGraphRuntime` together with the director and scheduler.
2. **Static graph, dynamic state.** JSON contains topology and policy metadata. Visit counters and timestamps live only in runtime memory.
3. **Count audience exposure, not sampling.** Fatigue increments once when speech enters `speaking`, never once per telemetry tick, candidate observation, model attempt, or deferred replacement.
4. **Monotonic time only.** Fatigue decay, silence dwell, cooldown compatibility, and retry backoff use the monotonic clock.
5. **Truth before score.** Invalid or stale candidates are unavailable, not merely given a low score.
6. **Commit revalidation remains.** A high graph score cannot bypass run, actor, relation, or hero-order validation immediately before TTS.
7. **Critical occurrence floor.** A new unique critical result cannot be removed by generic node or path fatigue.
8. **Bounded path context.** Path fatigue and transition scoring use at most the latest three spoken graph nodes.
9. **No weight-knob explosion.** Nodes select typed policy IDs and small normalized multipliers. Detailed formulas remain tested Python code.
10. **Compose only the winner.** Candidate scoring must not spend LLM work on candidates that will be rejected.
11. **Lexical anti-repeat remains last.** `RecentUtteranceHistory` continues to choose among textual variants after semantic selection.
12. **Depth-one defer remains.** The TTS scheduler may keep at most one best current waiter; the graph does not introduce a backlog.
13. **Safe staged rollout.** Legacy, shadow, and active modes are required until replay and live evidence allow removal of legacy selection.

## 6. Target ownership and boundaries

```text
RacePipeline / RaceObserver
  owns: truth, accepted event identity, immutable context, filler facts
  must not: decide speech fatigue or silence promotion

CommentaryConsumer
  owns: SequenceGraphRuntime, CommentaryDirector, TTS scheduler
  must not: retain or call a live RaceObserver

SequenceGraphRuntime
  owns: available candidates, weighted transitions, traversal state,
        repetition fatigue, SILENCE dwell, deterministic selection
  must not: synthesize unsupported facts or start audio

Composer / optional Qwen
  owns: realization of the already selected microplan
  must not: change selected facts, actors, direction, or score

MiniStoryRegistry + TTS commit path
  owns: last-moment truth validation, lease, interruption, completion
  must not: reconsider normal editorial ranking after commit
```

`StoryHistory` remains an authoritative history of accepted facts used to reconstruct possible story context. It is not editorial exposure memory: an accepted beat may never have been heard. Only `SequenceGraphRuntime` records spoken traversal and uses it for repetition fatigue.

## 7. Runtime graph model

### 7.1 Reserved `SILENCE` node

`SILENCE` is a runtime-only node injected by `SequenceGraphRuntime`; it is not an event type and has no authored variant.

The runtime enters `SILENCE`:

- at commentary run/session start when commentary is eligible;
- after audio completion;
- after interruption, unless a replacement critical beat is committed immediately;
- after a selected draft is invalidated and no speech remains in flight.

The runtime does not accumulate silence while audio is playing or while the TTS backend is actively producing audible output. The authoritative start of silence is an audio lifecycle event, not the moment the director enqueues text.

### 7.2 Runtime state

The initial implementation should use one typed object equivalent to:

```python
@dataclass
class SequenceGraphRuntimeState:
    run_epoch: int
    current_node_id: str
    entered_at: float
    last_audio_completed_at: float | None
    active_story_id: str | None
    spoken_path: deque[str]               # maxlen=3
    node_fatigue: dict[str, FatigueStat]
    edge_fatigue: dict[tuple[str, str], FatigueStat]
    semantic_fatigue: dict[str, FatigueStat]
    path_fatigue: dict[tuple[str, ...], FatigueStat]
    committed_occurrences: BoundedIdSet
```

All collections must be bounded. Suggested initial ceilings:

- node stats: graph node count;
- edge stats: graph edge count plus `SILENCE` transitions;
- semantic stats: 128 entries per run;
- path stats: 64 entries per run;
- committed occurrence IDs: 2,048, matching the existing consumer dedupe order.

Eviction is oldest-last-visited first. Eviction changes diversity preference only; it must never invalidate truth or lifecycle state.

### 7.3 Candidate model

Before composition, every possible spoken beat becomes a typed candidate:

```python
@dataclass(frozen=True)
class GraphCandidate:
    node_id: str
    event_id: str
    event_type: str
    story_id: str | None
    correlation_id: str
    run_epoch: int
    source_revision: int
    semantic_key: str
    material_revision: str
    priority: int
    envelope: EventEnvelope
```

`semantic_key` identifies what the audience would learn. `material_revision` identifies whether a previously mentioned subject has changed enough to justify another call.

Candidate construction is deterministic and must not mutate the envelope.

## 8. Graph schema v2

Adding active editorial semantics requires a schema version bump from graph version 1 to version 2. The loader remains strict: code support, the data migration, validator changes, and compatibility tests land together.

### 8.1 Node metadata

Each node receives an `editorial` object:

```json
{
  "speak_priority": 50,
  "cooldown_s": 16,
  "editorial": {
    "policy": "live_relation",
    "semantic_policy": "battle_relation",
    "criticality": "story",
    "repeat_weight": 1.0,
    "silence_affinity": 0.65,
    "material_change_policy": "gap_intensity"
  }
}
```

Allowed fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `policy` | enum | Shared score/fatigue defaults: `critical_result`, `live_relation`, `story_result`, `periodic_context`, `once_per_scope` |
| `semantic_policy` | enum | Typed Python key builder; no JSON expression language |
| `criticality` | enum | `critical`, `story`, or `context` |
| `repeat_weight` | float 0–2 | Multiplier over the selected policy's fatigue penalty |
| `silence_affinity` | float 0–1 | How strongly time in `SILENCE` promotes this node |
| `material_change_policy` | enum | Typed definition of a meaningfully new revision |

`cooldown_s` remains parseable during migration. In shadow/active graph mode it becomes a compatibility input to recent-node fatigue or a minimum-repeat guard defined by the node policy. It must not remain a separate competing `_cooldowns` decision after cutover.

### 8.2 Edge metadata

Edges gain optional editorial metadata:

```json
{
  "from": "side_by_side",
  "to": "overtake",
  "when": {
    "same_correlation": true,
    "min_gap_s": 0.4,
    "max_gap_s": 12.0
  },
  "editorial": {
    "transition_bonus": 8,
    "closure": true,
    "repeat_weight": 1.0
  }
}
```

Allowed fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `transition_bonus` | integer 0–20 | Reward for a coherent valid continuation |
| `closure` | boolean | Marks an outcome/closure edge deserving a protected bonus |
| `repeat_weight` | float 0–2 | Multiplier for repeated-edge/path fatigue |

The existing correlation and time predicates remain hard availability conditions.

### 8.3 Policy implementation

Policy IDs map to closed Python enums and tested functions. Unknown policy IDs fail graph validation at startup and invoke the existing fail-soft graph-load handling. Policies may inspect only documented candidate/context fields.

Do not store runtime counters in JSON and do not introduce strings such as `"gap < 0.8 and closing"`.

## 9. Semantic identity and material change

Raw node IDs are insufficient. A second `HUNTING` beat may be redundant or may describe a new rival and a new story.

Initial semantic policies:

| Policy | Semantic identity | Material revision |
| --- | --- | --- |
| `unique_result` | run epoch + event type + occurrence/event ID | result identity itself; dedupe exact occurrence only |
| `position_result` | run epoch + hero + old/new class position | any different old/new pair |
| `battle_relation` | run epoch + relation + hero + target car ID(s) + relation epoch | target change, direction change, intensity-band change, or live→resolved |
| `pit_story` | run epoch + pit-cycle/story ID | entry→stopped→exit/result transition |
| `lap_result` | run epoch + lap + result kind | new lap, PB state, or meaningful delta band |
| `context_fact` | run epoch + fact kind + involved actor | value band or actor change |
| `weather_fact` | session/run + normalized weather signature | existing weather thresholds determine change |
| `once_scope` | configured session/run/stream scope + node ID | never material within the same scope |

Continuous numbers must be quantized by domain-aware policies. A gap changing from 1.42 s to 1.41 s is not a new semantic fact. Crossing graph-relevant intensity bands, reversing trend, changing target, or resolving the story is material.

Critical unique results use occurrence identity before fatigue. Repeating the same event ID remains a dedupe rejection; a later real position gain remains a new occurrence even if the same graph node was used earlier.

## 10. Repetition fatigue

Every fatigue statistic stores a decayed visit value and its last update time. At time `t`:

```text
decayed(previous, elapsed, half_life)
    = previous × exp(-elapsed / half_life)

on speaking start:
    fatigue = decayed(...) + 1

on score read:
    fatigue = decayed(...)
```

The penalty for one candidate is:

```text
repeat_penalty = repeat_weight × (
    node_weight     × log2(1 + node_fatigue)
  + semantic_weight × log2(1 + semantic_fatigue)
  + edge_weight     × log2(1 + edge_fatigue)
  + path_weight     × log2(1 + path_fatigue)
)
```

The logarithm prevents an often-used family from becoming permanently unreachable. Decay lets an old topic become usable later.

Initial weights and half-lives are implementation hypotheses, not configuration defaults. They must be chosen from replay evidence. Suggested shadow-mode starting points:

| Component | Weight | Half-life |
| --- | ---: | ---: |
| node | 6 | 90 s |
| semantic fact | 14 | 120 s |
| edge | 5 | 120 s |
| 2–3 node path | 8 | 180 s |

`critical_result` does not apply generic semantic/path suppression to a new occurrence. It may still use lexical anti-repeat and omit already-known optional context.

## 11. Silence pressure

Silence is measured as dwell time in the reserved `SILENCE` node.

Let:

```text
quiet_s = now - silence_entered_at
soft_s  = 0.60 × max_silence_s
hard_s  = max_silence_s

silence_progress = clamp((quiet_s - soft_s) / (hard_s - soft_s), 0, 1)
silence_bonus = silence_affinity × max_silence_bonus × silence_progress
```

The first implementation reuses `[commentary.scheduler].max_silence_s` as `hard_s` for compatibility. Suggested initial `max_silence_bonus` is 30 score points; shadow replay must calibrate it.

Rules:

- before `soft_s`, silence does not alter ranking;
- between `soft_s` and `hard_s`, live-story and context candidates gain a proportional bonus;
- at/after `hard_s`, the runtime requests or admits bounded factual filler candidates;
- a live, unresolved story outranks generic context when both remain useful;
- after finish/mute, existing post-race eligibility rules still suppress generic filler;
- disconnected or unavailable truth never becomes speech merely because silence is long;
- no candidate above threshold means remain in `SILENCE`;
- a `no_fact` filler result uses monotonic retry backoff and must not cause a request every 200 ms consumer tick.

`defer_enabled` continues to control whether one busy candidate may wait. It no longer controls whether silence time is observed in active graph mode.

## 12. Unified editorial score

For each factually available candidate:

```text
score =
    node.speak_priority
  + transition_bonus
  + closure_bonus
  + material_change_bonus
  + silence_bonus
  - repeat_penalty
```

Initial bounded bonuses for shadow evaluation:

| Component | Range |
| --- | ---: |
| transition | 0–20, normally 8 |
| closure | 0–20, normally 15 |
| material change | 0–15, normally 10 |
| silence | 0–30 |
| repeat penalty | 0–60 |

Suggested initial selection threshold: 45. These values are deliberately on the existing 0–100 `speak_priority` scale.

Scoring order:

1. build all candidates from the accepted batch and any due factual filler batch;
2. remove candidates failing truth, run, event TTL, branch, mode, slots, or story identity;
3. enumerate only direct valid transitions plus a bounded path context of up to three spoken nodes;
4. calculate score breakdowns without composing text;
5. apply the critical-occurrence floor;
6. choose one winner with a stable tie-break;
7. compose and validate only that winner;
8. park, commit, or speak through the existing bounded lifecycle.

Stable tie-break order:

1. descending final score;
2. descending criticality (`critical`, `story`, `context`);
3. descending node `speak_priority`;
4. ascending accepted stream sequence;
5. ascending event ID;
6. ascending node ID.

Randomness is allowed only later when choosing among already-safe textual variants. It must not influence semantic candidate selection.

## 13. Critical results and story closure

The graph must distinguish repetition from a new important occurrence.

### Critical occurrence floor

For a unique, not-yet-committed `critical` occurrence:

- generic node/path fatigue cannot lower it below the selection threshold;
- an already speaking authoritative hero-order result retains current hard-preemption rights;
- exact event/occurrence dedupe still applies;
- factual invalidity, reset, stale identity, or commit-gate failure can still reject it.

Initial critical set:

- `FINISH`;
- `POSITION_GAINED` and `POSITION_LOST`;
- confirmed `LEADER_CHANGE`;
- configured terminal session results;
- technical teardown remains cancellation, not a critical spoken result.

The exact set must be asserted by graph compatibility tests rather than duplicated in an unvalidated Python set.

### Closure bonus

A truthful result closing a mini-story receives an edge closure bonus. This prevents fatigue on the opening beat from suppressing the audience's payoff. Examples:

- `hunting → overtake`;
- `side_by_side → overtake`;
- `overtake → battle_won`;
- `pit_entry → pit_outcome`;
- `incident_aftermath → back_under_way`;
- `final_lap → finish`.

Closure does not bypass truth or permit two redundant result sentences for the same occurrence.

## 14. Lifecycle and counter update points

The following events are the only mutation points for editorial graph state:

| Lifecycle event | Graph mutation |
| --- | --- |
| accepted candidate | none; availability only |
| scored/rejected | none |
| selected for composition | none |
| parked/deferred | none |
| replaced/dropped waiter | none |
| invalidated before audio | none; return to `SILENCE` if idle |
| `speaking` starts | atomically record occurrence and increment node/semantic/edge/path fatigue |
| `completed` | enter `SILENCE`, set its monotonic `entered_at` |
| `interrupted` after audio began | exposure remains counted; enter `SILENCE` or immediate replacement |
| session/run reset | clear run-scoped graph state and enter fresh `SILENCE` |

This prevents model retries, TTS queue replacements, and telemetry frequency from inflating repetition counters.

The TTS worker must not mutate `SequenceGraphRuntime` directly from its thread. Lifecycle notifications are marshalled into the commentary consumer's owned execution lane, matching the existing thread-safe MiniStory/overlay lifecycle pattern.

## 15. Filler candidate contract

### Initial slice

The first active slice may keep the current one-at-a-time `FillerRequest` transport. The graph owns when the request is due and whether the returned candidate crosses the score threshold. This already removes `SpeechScheduler.silence_due()` as a competing decision.

### Target slice

To let the graph choose rather than accept a fixed rotation, the producer should return a bounded immutable set of currently true commentary-only candidates:

```text
FillerRequest
  → RaceObserver derives at most four current facts
  → producer assigns normal event IDs and publishes one accepted batch
  → CommentaryConsumer scores them beside live candidates
```

Candidate kinds initially remain:

- material weather change;
- current hero position;
- current leader;
- current relevant gap/opponent;
- pit/in-lap/out-lap context where already supported.

The producer owns derivation and validity. The graph owns selection. Fixed `_last_filler_kind` round-robin selection is removed only after the bounded-candidate path is active and tested.

## 16. Simplification target

After active-mode cutover and one compatibility release, these responsibilities move into `SequenceGraphRuntime`:

| Current mechanism | Target disposition |
| --- | --- |
| director `_last` | replaced by graph `current_node_id` and spoken path |
| `_pick_node()` / `_follow_edge()` | replaced by candidate generation and weighted transition ranking |
| director `_cooldowns` | represented by decaying node/semantic state and policy minimum-repeat guards |
| director `_global_ready_at` | retained only as a technical minimum TTS separation, not editorial ranking |
| scheduler `silence_due()` | removed; `SILENCE` dwell owns cadence pressure |
| RaceObserver filler rotation | replaced by bounded factual candidates in target slice |
| envelope-only busy defer priority | replaced by the chosen candidate's final graph score/criticality |
| semantic anti-repeat proposal | absorbed by node/semantic/edge/path fatigue |
| lexical anti-repeat | retained for wording selection |
| MiniStory commit/revalidation | retained unchanged in authority |

The success criterion is single ownership, not a raw line-count reduction. There must be exactly one function producing the final editorial score and exactly one runtime object mutating traversal fatigue.

## 17. Failure model

- Graph parse or policy validation failure at startup follows existing fail-soft commentary behavior and records an actionable error.
- A per-candidate semantic-policy exception rejects that candidate, records `graph_policy_error`, and continues with remaining candidates.
- A batch-level ranking failure in `active` mode falls back to legacy director selection for that batch during the compatibility period; it must not crash the consumer or race loop.
- Non-finite score inputs are rejected by validation before comparison.
- TTS, Ollama, OBS ducking, and consumer failures retain their current isolation/backoff behavior.
- Graph-state reset is idempotent.
- A stale lifecycle callback carrying an earlier run epoch cannot mutate current graph state.

## 18. Observability contract

Every candidate evaluated in shadow or active mode produces a bounded DEBUG/tape decision with:

```json
{
  "graphMode": "shadow",
  "eventId": "...",
  "storyId": "...",
  "runEpoch": 1,
  "nodeId": "hunting",
  "semanticKey": "battle_relation:...",
  "path": ["hunting", "attack_range"],
  "available": true,
  "score": 47.3,
  "threshold": 45.0,
  "components": {
    "base": 50.0,
    "transition": 8.0,
    "closure": 0.0,
    "materialChange": 0.0,
    "silence": 4.3,
    "nodeFatigue": -6.0,
    "semanticFatigue": -9.0,
    "edgeFatigue": 0.0,
    "pathFatigue": 0.0
  },
  "decision": "selected",
  "reason": "highest_score"
}
```

Required reason codes:

- `highest_score`;
- `below_threshold`;
- `semantic_repeat`;
- `path_repeat`;
- `material_change`;
- `story_continuation`;
- `story_closure`;
- `silence_promoted`;
- `critical_floor`;
- `unavailable_truth`;
- `stale_candidate`;
- `graph_policy_error`;
- `legacy_fallback`.

`/commentary` status in shadow/active mode should expose only compact current state:

- graph mode;
- current graph node;
- seconds in silence;
- last winning node and score;
- bounded fatigue-entry counts;
- last graph error.

Full semantic keys and score breakdowns remain DEBUG/tape data, not a high-frequency public status payload.

## 19. Acceptance criteria

### Architecture

- [ ] `CommentaryConsumer` owns one `SequenceGraphRuntime`; no other lane mutates it directly.
- [ ] One deterministic ranking function owns priority, transition, repetition, closure, and silence bonus.
- [ ] Race truth remains in producer/RaceObserver and reaches commentary only through accepted immutable data or frozen context.
- [ ] `MiniStoryRegistry` remains the pre-audio authority for run, story, actor, relation, and hero-order validity.
- [ ] No new runtime dependency or external graph database is added.
- [ ] All runtime collections and path searches are explicitly bounded.

### Repetition

- [ ] Two differently worded utterances with the same semantic key increase the same fatigue statistic.
- [ ] Scoring the same candidate repeatedly without speaking does not increase fatigue.
- [ ] Changing telemetry polling from 5 Hz to 8 Hz produces the same spoken semantic decisions for the same accepted-event timeline.
- [ ] A material target, intensity, direction, position, lap, weather, or live→resolved change creates the specified new revision.
- [ ] A repeated two- or three-node path loses score while another truthful path can win.
- [ ] Fatigue decays monotonically with monotonic elapsed time.
- [ ] Lexical variant anti-repeat still operates after semantic selection.

### Criticality and closure

- [ ] Every new valid critical occurrence remains selectable regardless of prior generic node/path fatigue.
- [ ] Exact duplicate critical event IDs are not spoken twice.
- [ ] Story-result edges receive closure bonus without bypassing factual availability.
- [ ] A closure cannot produce two result utterances for one occurrence.
- [ ] Repeated optional context can be omitted while a new critical result remains spoken.

### Silence

- [ ] Silence begins at run/session eligibility before the first utterance.
- [ ] Silence duration restarts on audio completion, not on selection or enqueue.
- [ ] Silence does not accumulate while audio is actively playing.
- [ ] `defer_enabled=false` does not disable silence observation in active graph mode.
- [ ] Before the soft boundary, silence adds no score.
- [ ] At the hard boundary, truthful context candidates may cross the threshold according to `silence_affinity`.
- [ ] A current live story outranks generic filler when its final graph score is higher.
- [ ] With no valid fact, the runtime remains silent and applies bounded filler-request backoff.
- [ ] Finish/mute and disconnected-state eligibility continue to suppress inappropriate fillers.

### Lifecycle and reset

- [ ] Fatigue increments exactly once at `speaking` for direct, deferred, and fallback realization paths.
- [ ] A pre-audio invalidation does not increment fatigue.
- [ ] An interruption after audio begins retains the exposure count.
- [ ] Session/run reset clears run-scoped traversal state exactly once and rejects stale callbacks.
- [ ] TTS lifecycle notifications mutate graph state only on the commentary consumer lane.

### Determinism and failure handling

- [ ] Identical replay input, config, graph, and seed produce identical semantic selections and score breakdowns.
- [ ] Stable tie-breaking does not depend on dict/set iteration order.
- [ ] Invalid graph policy metadata fails validation with a precise path.
- [ ] A policy exception or graph-ranking failure does not stop the commentary consumer or race loop.
- [ ] Active mode can fall back to legacy selection during the compatibility period and records why.

### Simplification

- [ ] `_pick_node()` and `_follow_edge()` no longer participate in active-mode selection.
- [ ] Per-node editorial cooldown is not independently enforced outside the graph runtime in active mode.
- [ ] `SpeechScheduler.silence_due()` no longer decides active-mode filler timing.
- [ ] Busy defer replacement compares final graph score/criticality rather than raw envelope priority.
- [ ] Target filler selection is graph-ranked rather than fixed round-robin before legacy mode is removed.

## 20. Implementation plan

Implementation is sequential because the graph runtime, director, scheduler, and consumer ownership overlap. Parallel work is appropriate only for later independent tape-analysis or documentation tasks.

### Phase 0 — Issue, replay baseline, and score contract

**Purpose:** lock evidence before behavior changes.

Implementation:

- create a dedicated feature issue referencing this specification;
- copy the acceptance criteria, test plan, docs impact, config impact, and rollback plan into the issue;
- extend deterministic commentary replay cases with repeated semantic facts, repeated paths, material changes, critical results, initial silence, long silence, and no-fact silence;
- define the typed `ScoreBreakdown`, policy enums, semantic-key contract, and lifecycle mutation table in tests before production code;
- record legacy decisions as the comparison baseline.

Evidence:

- deterministic fixture suite runs without Ollama;
- baseline report includes semantic duplicate rate, repeated path rate, critical-result recall, filler share, and silence-gap distribution;
- live model remains optional and is not needed for scoring tests.

Likely files:

- `tests/fixtures/commentary/`
- `tests/test_commentary_replay_eval.py`
- `src/irswitch/commentary/replay_eval.py`
- optional replay/report script already used by the repository

### Phase 1 — Graph v2 schema and compatibility

**Purpose:** add static editorial policy without changing selection.

Test-first implementation:

- add graph v2 validation tests for node and edge editorial metadata;
- add closed enums for policy, semantic policy, criticality, and material-change policy;
- parse immutable editorial dataclasses on `GraphNode` and `GraphEdge`;
- migrate all 54 nodes and 24 edges with explicit compatible metadata;
- extend the graph assignment/export/import path so editorial metadata cannot be lost;
- retain existing line, slot, branch, mode, style-card, and edge compatibility coverage.

Acceptance gate:

- all graph nodes have an explicit valid policy;
- critical nodes and closure edges match an asserted inventory;
- version 1 is rejected once version 2 data lands, unless a deliberate one-release compatibility loader is justified in the issue;
- no current commentary output changes.

Likely files:

- `src/irswitch/commentary/graph.py`
- `src/irswitch/commentary/data/sequence_graph.json`
- `src/irswitch/commentary/assignments.py`
- `tests/test_commentary_graph.py`
- `tests/test_commentary_assignments.py`
- `tests/test_commentary_content_extension.py`

### Phase 2 — `SequenceGraphRuntime` core

**Purpose:** implement bounded state, semantic identity, fatigue, silence, and scoring in isolation.

Test-first implementation:

- add `graph_runtime.py` with typed state and pure score functions;
- implement bounded fatigue stores with monotonic exponential decay;
- implement semantic and material-revision policy functions;
- implement the runtime `SILENCE` node and silence bonus;
- implement direct transition and bounded path scoring;
- implement critical floor and stable tie-breaks;
- implement idempotent run reset and stale lifecycle rejection;
- keep all functions independent of TTS, OBS, and a live RaceObserver.

Acceptance gate:

- unit tests cover all repetition, silence, criticality, determinism, bound, and reset AC;
- 5 Hz versus 8 Hz replay produces identical decisions;
- score computation is bounded by candidate count and graph degree; no unbounded path walk exists.

Likely files:

- new `src/irswitch/commentary/graph_runtime.py`
- new `tests/test_commentary_graph_runtime.py`
- focused additions to graph and replay tests

### Phase 3 — Shadow-mode director integration

**Purpose:** observe the new graph without changing audible behavior.

Implementation:

- add `legacy | shadow | active` graph-runtime mode;
- construct graph candidates before current director node selection;
- in shadow mode, compute and tape the graph winner while legacy selection remains authoritative;
- forward TTS `speaking`, `completed`, `interrupted`, and invalidation lifecycle events into the commentary consumer lane;
- update shadow graph visits from the utterance actually spoken by the legacy path so shadow state models audience exposure;
- expose compact graph status and score breakdown diagnostics;
- do not call Qwen for shadow losers.

Acceptance gate:

- audible output is bit-compatible with legacy mode for deterministic non-LLM tests;
- shadow ranking never blocks or delays the producer or overlay consumer;
- every legacy-spoken utterance causes exactly one shadow exposure update;
- graph errors are visible and fail soft.

Likely files:

- `src/irswitch/commentary/director.py`
- `src/irswitch/commentary/consumer.py`
- `src/irswitch/commentary/tts.py`
- `src/irswitch/overlay/settings.py`
- `src/irswitch/config.py`
- `src/irswitch/overlay/schema.py`
- `src/irswitch/overlay/tape.py`
- `tests/test_commentary_director.py`
- `tests/test_n12_consumers.py`
- `tests/test_commentary_tts.py`
- `tests/test_overlay_tape.py`

### Phase 4 — Active selection for repeated live/context families

**Purpose:** limit first behavior change to the noisy families with the clearest benefit.

Initial active families:

- `HUNTING` / `APPROACH`;
- `HUNTED` / `RIVAL_THREAT`;
- `ATTACK_RANGE` / `SIDE_BY_SIDE`;
- `BATTLE_FOR_POSITION`;
- `FIELD_FACT` / `WEATHER_CHANGE`.

Implementation:

- rank all candidates from one accepted batch before composing;
- use graph score as the scheduler defer priority;
- preserve current critical and other families on the legacy path during this slice;
- reuse the current one-at-a-time filler transport, but let graph `SILENCE` state decide request timing and acceptance;
- remove active-family use of `_pick_node()`, `_follow_edge()`, and separate node cooldown blocking;
- compare shadow and active replay reports.

Acceptance gate:

- semantic duplicates and repeated 2–3 node paths decrease against baseline;
- no increase in stale/invented facts;
- live→resolved transitions and actor direction remain correct;
- no-fact silence produces bounded requests, not polling spam;
- critical legacy events retain 100% valid-occurrence recall.

### Phase 5 — Graph-ranked filler candidates

**Purpose:** remove fixed filler rotation as an editorial decision.

Test-first implementation:

- extend the typed filler request/producer path to publish at most four immutable valid candidates;
- keep event IDs, session/run identity, TTL, and accepted-stream ordering;
- score returned context candidates beside any current live story;
- remove `_last_filler_kind` selection after parity and rotation tests are replaced by graph-choice tests;
- keep weather/leader factual thresholds and post-finish suppression in RaceObserver.

Acceptance gate:

- RaceObserver derives facts but does not rank them for speech;
- generic context cannot displace a higher-scoring live story;
- repeated position/leader/gap facts decay independently by semantic identity;
- no consumer reaches through to a live RaceObserver.

Likely files:

- `src/irswitch/events/stream.py`
- `src/irswitch/race/observer.py`
- `src/irswitch/race/runtime.py`
- `src/irswitch/commentary/consumer.py`
- `tests/test_race_observer.py`
- `tests/test_n12_consumers.py`
- `tests/test_n12_race_pipeline.py`

### Phase 6 — Full active cutover and policy deletion

**Purpose:** achieve architectural simplification after evidence, not before it.

Implementation:

- migrate remaining node families to graph selection;
- assert critical inventories and closure behavior;
- remove active selection's `_last`, `_pick_node()`, `_follow_edge()`, and independent `_cooldowns` ownership;
- reduce `_global_ready_at` to technical minimum speech spacing only;
- remove scheduler `silence_due()` and raw-envelope defer ranking;
- make active graph mode the documented default only after replay and live acceptance;
- keep legacy fallback for one compatibility release, then schedule its deletion in a separate cleanup issue.

Acceptance gate:

- all simplification AC are met;
- one score breakdown explains each selected/rejected beat;
- full deterministic commentary, graph, scheduler, consumer, MiniStory, and tape suites pass;
- legacy-versus-active differences are reviewed and classified as intended, neutral, or defect.

### Phase 7 — Windows/OBS/Ollama live acceptance

**Purpose:** verify cadence and listener quality that fixtures cannot prove.

Manual scenarios:

1. practice with repeated laps and few battles;
2. qualifying with timing facts and initial silence;
3. race with repeated hunting against the same target;
4. target change and two-front story;
5. side-by-side closure into overtake/position result;
6. long green-flag silence with and without valid filler facts;
7. incident and recovery without redundant aftermath;
8. run restart inside the same iRacing session;
9. finish and post-finish mute;
10. Ollama timeout and TTS interruption.

Evidence to retain:

- session tape and graph score rows;
- spoken semantic timeline;
- audio/listening notes;
- p50/P90/P95 quiet gaps in eligible race time;
- critical occurrence recall;
- semantic duplicate and repeated-path rates;
- failure/fallback counts.

Do not tune weights from one anecdotal sentence. Change one policy/weight group at a time and replay the same corpus before another live run.

## 21. Test plan

### Unit

- graph v2 parsing, defaults, invalid enum/range/path reporting;
- semantic keys and material revisions for every initial policy;
- decay math under monotonic elapsed time;
- node, semantic, edge, and path penalty composition;
- `SILENCE` soft/hard boundaries and first-speech behavior;
- critical floor, closure bonus, threshold, and stable tie-breaks;
- bounded-store eviction and idempotent reset;
- lifecycle update points and stale run callbacks;
- lexical anti-repeat compatibility.

Use explicit monotonic timestamps. Follow the repository time-test policy where wall-time freezing is useful, but do not make correctness depend on wall-clock time.

### Integration

- director ranks multiple envelope families by one graph score;
- deferred replacement uses graph score and remains depth-one;
- no LLM call occurs for losing candidates;
- MiniStory resolution/invalidation during generation does not inflate fatigue;
- commentary consumer remains independent from overlay consumer latency/failure;
- filler request/result and bounded candidate batches preserve N12 ordering and identity;
- tape and `/commentary` status expose the specified diagnostics;
- fail-soft fallback continues after injected graph-policy exceptions.

### Replay

- identical timeline at different producer poll frequencies;
- repeated semantic fact with varied text;
- repeated generic path with an available truthful alternative;
- repeated path with no truthful alternative;
- material change and story closure;
- critical occurrence after heavy family fatigue;
- initial silence, long silence, no-fact silence, and post-finish silence;
- session/run reset with stale callbacks.

### Manual

- Windows/SAPI or configured device;
- OBS ducking and interruption restoration;
- optional local/LAN Ollama;
- `/commentary` status plus tape inspection;
- full session listening rather than isolated sentence review.

## 22. Quality metrics

The implementation issue must record the baseline before setting numeric gates. At minimum track:

| Metric | Required interpretation |
| --- | --- |
| valid critical occurrence recall | must remain 100% in curated deterministic replay |
| semantic duplicate rate | same semantic key without material revision inside its policy window |
| repeated path rate | repeated spoken node bigrams/trigrams after decay window normalization |
| eligible quiet-gap distribution | exclude disconnected, muted, post-finish-ineligible, and actively speaking time |
| filler share | distinguish live story, context filler, opener, and terminal result |
| stale/invalidated before audio | must not count as exposure |
| LLM calls per accepted candidate | losers are zero; winner retains current one/two-call microplan contract |
| active vs shadow/legacy delta | each difference classified and reviewable through score components |

The target is not maximum speech count or minimum silence. It is fewer redundant claims, preserved critical facts, coherent story closure, and controlled cadence.

## 23. Configuration impact

Proposed migration control:

```ini
[commentary.graph_runtime]
mode = legacy
```

Allowed values:

- `legacy`: current director behavior; graph runtime inactive;
- `shadow`: current audible behavior plus graph scoring/diagnostics;
- `active`: stateful graph is authoritative.

Rules:

- initial shipping default is `legacy`;
- no individual score weights or half-lives are exposed as INI keys before replay evidence shows an operator need;
- graph data owns relative editorial policy; `CONFIG.md` remains the user-facing config contract;
- `[commentary.scheduler].max_silence_s` remains accepted and supplies active graph `hard_s` during migration;
- `[commentary.scheduler].defer_enabled` controls only busy defer in active mode, not silence observation;
- changing the default to `active` is a later explicit behavior change with migration notes and release labeling;
- removing `legacy` mode requires a later deprecation/cleanup issue.

When implemented, update both `CONFIG.md` and `config/config.example.ini`, including the interaction with existing scheduler settings.

## 24. Documentation and API impact

This specification is the only document changed by the current docs-only work item.

When implementation begins, review and update:

- `COMMENTARY_ENGINE.md`: target pipeline, graph v2, active score, silence semantics, and lexical-versus-semantic anti-repeat;
- `CONFIG.md` and `config/config.example.ini`: graph runtime mode and scheduler migration behavior;
- `API.md`: compact `/commentary` graph-runtime status fields if exposed;
- `docs/scenario_coverage_matrix.md`: commentary-selection and silence behavior;
- this document: phase status and evidence links;
- PR description: full Docs impact checklist.

No README, build, installer, VR, or scene-switch documentation impact is expected unless implementation scope expands.

## 25. Rollout and rollback

1. Ship graph v2 parsing and shadow mode without audible changes.
2. Run deterministic replay and at least one Windows live session in shadow mode.
3. Activate only repeated live/context families.
4. Run the same replay and live scenarios; correct policy data/formulas rather than adding special-case gates in the director.
5. Activate graph-ranked filler candidates.
6. Migrate critical and remaining families.
7. Make active mode default only after all AC and live evidence pass.
8. Retain `mode=legacy` as immediate rollback for one compatibility release.
9. Remove legacy code only in a later reviewed cleanup after no unresolved rollback has occurred.

Rollback must not require a graph downgrade. Graph v2 remains readable while `mode=legacy` selects the old policy path during the compatibility window.

## 26. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Important event suppressed by accumulated fatigue | unique critical occurrence floor plus 100% replay recall gate |
| Poll-frequency-dependent behavior | update fatigue only at `speaking`; replay identical accepted timelines at 5/8 Hz |
| Same meaning evades penalty through new wording | semantic keys operate before composition; lexical anti-repeat remains separate |
| Continuous telemetry makes every fact appear new | typed material-change policies and domain bands |
| Long silence causes irrelevant chatter | node `silence_affinity`, threshold, live-story comparison, and correct silence when no fact exists |
| Graph selects stale truth while Qwen works | existing MiniStory commit gate remains authoritative |
| Stateful graph becomes an opaque rule language | closed enums, small metadata surface, score breakdown, strict validation |
| Cycles cause path explosion | score only direct candidates with at most three spoken nodes of history |
| Runtime memory grows for every actor/value | bounded semantic/path stores with deterministic eviction |
| TTS callback races graph reset | marshal callbacks to consumer lane and verify run epoch |
| Shadow mode changes timing | scoring is CPU-only, bounded, no LLM work for losers, and measured in consumer tests |
| Fixed filler rotation continues to undermine graph choice | explicit bounded-candidate Phase 5 before legacy removal |
| Weight tuning becomes config sprawl | keep weights in tested policies/graph metadata until evidence requires user knobs |

## 27. Definition of done

The feature is complete only when:

- all acceptance criteria are checked with linked evidence;
- deterministic replay and focused/full regression suites pass;
- Windows/OBS/Ollama manual scenarios are recorded or an explicit external-system TDD exception documents what remains;
- graph v2, configuration, API/status, and commentary documentation agree;
- active selection has one editorial score owner and one traversal-state owner;
- no important event regression or main-loop failure is present;
- rollback to legacy remains tested for the compatibility release;
- the PR carries exactly one required semver label and passes CI.

## 28. TDD exception for this document

**TDD-exception:** docs-only design and implementation-plan capture; no executable behavior changed.

**Verification:** cross-check terminology, paths, settings, graph inventory, and lifecycle contracts against the baseline branch; render/read the Markdown and inspect the final diff.

**Risk:** the proposal could drift from implementation before work begins.

**Mitigation:** Phase 0 creates the implementation issue and baseline; later PRs update this specification with actual status and evidence rather than treating proposed values as shipped behavior.
