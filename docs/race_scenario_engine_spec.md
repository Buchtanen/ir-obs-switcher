# Deterministic race scenario engine — specification and implementation plan

**Status:** proposed, implementation-ready; no runtime behavior changed by this document

Implementation status: [progress](track_excursion_implementation_progress.md), tracked in
[#216](https://github.com/Buchtanen/ir-obs-switcher/issues/216). A native current-signal subset
is connected for active development testing; this document remains the broader target.
See [actual behavior and test protocol](track_excursion_live_test.md).

**Baseline branch:** `codex/fix-overlay-commentary-test-7`

**Baseline commit:** `4497040` (`fix: harden overlay and commentary lifecycle (#215)`)

**Reference scenario:**
[`docs/scenarios/incident_offtrack_recovery_v1.json`](scenarios/incident_offtrack_recovery_v1.json)

**Composite semantic scenario:**
[`docs/scenarios/track_excursion_story_v1.json`](scenarios/track_excursion_story_v1.json), described
by [track_excursion_story_spec.md](track_excursion_story_spec.md)

**Consolidated delivery plan:**
[track_excursion_implementation_plan.md](track_excursion_implementation_plan.md)

**Related contracts:**
[Test 7 fix](overlay_commentary_test_7_fix_spec.md),
[stateful commentary graph](commentary_stateful_sequence_graph_spec.md),
[Editorial MiniStory lifecycle](implementation_editorial_ministory.md),
[race run epoch](implementation_race_run_epoch.md), and
[scenario coverage matrix](scenario_coverage_matrix.md)

---

## 1. Executive decision

Introduce one versioned, deterministic scenario layer between normalized race facts and event
arbitration. A scenario is a bounded timed state machine whose transitions use registered,
tested guards. It owns the answer to these questions:

1. what episode is currently happening;
2. which actors and run the episode belongs to;
3. when each semantic phase begins and ends;
4. how strong and fresh the evidence is;
5. which factual beats the episode emits;
6. why a possible transition was accepted, rejected, or left unknown.

The first migrated scenario is `incident_offtrack_recovery/v1`, because the Test 7 sequence
around 13:44 already demonstrates the desired narrative shape: incident, consequence, and
recovery at the correct moments.

That low-level migration name follows the existing transport event vocabulary. The audience-facing
semantic story is `track_excursion_story/v1`. Its product contract makes confirmed off-track truth
exclusive over generic incident wording; “incident” is reserved for explicit incident-point count
commentary.

The design is deliberately hybrid:

- deterministic timed state machines own truth and lifecycle;
- robust estimators may calculate features and evidence confidence;
- confidence is bounded, calibrated, and explainable;
- weak or stale evidence produces `UNKNOWN`/abstention, not an invented label;
- the commentary graph chooses only among already valid factual beats;
- the LLM realizes a selected microplan and never detects race truth.

No neural detector, online learning, arbitrary JSON expression evaluator, external graph
database, or new runtime dependency is introduced.

## 2. Problem statement

The current system already contains good deterministic pieces, but their contracts are not
uniform:

- `RaceContextAnalyzer` derives gaps, closing rates, opponents, and normalized `RaceState`;
- classic emitters in `events/` detect battle, position, overtake, pit, lap, and incident facts;
- `RaceObserver` separately owns aftermath, recovery, flags, timing hunt, and grid story FSMs;
- `EventManagerV2` owns arbitration and accepted lifecycle identity;
- `MiniStoryRegistry` protects truth while LLM/TTS work continues;
- `sequence_graph.json` ranks and connects already detected beats;
- replay scenario fixtures begin at `RaceState`, not raw observations, and mostly assert an
  expected subsequence.

Consequences:

1. “scenario”, “event”, “story”, and “graph edge” do not have one precise meaning;
2. some situations are multi-stage FSMs while others are single-tick threshold checks;
3. confidence is commonly the default `1.0`, not a measured probability;
4. scenario identity does not consistently span cause, consequence, and outcome;
5. there is no shared policy for missing data, dwell, hysteresis, coalescing, or reset;
6. a replay can pass while upstream feature extraction or downstream speech timing is wrong;
7. tuning thresholds requires editing unrelated Python implementations and hand-maintained docs.

This specification creates one contract without invalidating the lifecycle fixes delivered by
#215.

## 3. Goals

The scenario engine must:

1. recognize the same episode identically for the same ordered observations and monotonic times;
2. make every state transition explicit, named, testable, and observable;
3. model duration, hysteresis, missing data, evidence freshness, and uncertainty;
4. preserve a stable episode identity while individual emitted beats retain independent
   MiniStory lifecycles;
5. support atomic episodes and composite scenarios without moving telemetry predicates into the
   commentary graph;
6. provide calibrated confidence and provenance to arbitration and the Director;
7. preserve strict editorial tiers and the one-current-waiter behavior from #215;
8. be bounded, async-safe, fail-soft, and dependency-free;
9. run in `shadow` mode against complete tapes before becoming authoritative;
10. allow one scenario definition to drive runtime validation, generated documentation, and
    positive, negative, and boundary replay cases.

## 4. Non-goals

- Letting the LLM decide whether an incident, pass, or battle happened.
- Replacing `EventManagerV2`, `MiniStoryRegistry`, the graph runtime, or TTS scheduling.
- Allowing lower editorial tiers to beat FINISH, START, flags, incidents, or position results
  through a weighted score.
- Speaking every detected event or creating an unbounded commentary queue.
- Loading executable Python, `eval` expressions, or user-authored formulas from JSON.
- Adding a user-facing threshold for every internal constant.
- Changing overlay wire fields in the first behavior-preserving migration.
- Persisting an active episode across a process restart in the first version.
- Treating silence as an error when no useful factual beat exists.

## 5. Terms and ownership

| Term | Exact meaning | Owner |
| --- | --- | --- |
| Observation | Timestamped normalized input value plus validity and age | `race/` |
| Feature | Derived value such as motion, gap trend, or position delta | `race/` |
| Guard | Named pure predicate over observations, features, and bounded episode memory | `events/scenarios/` |
| Transition | Explicit state change with time and evidence requirements | `events/scenarios/` |
| Episode | One real-world occurrence with stable `episode_id` | `events/scenarios/` |
| Beat | One fact emitted by an episode, such as incident, aftermath, or recovery | `events/` |
| Correlation | Lifecycle identity of one beat through ENTER/UPDATE/EXIT or RESULT | `EventManagerV2` |
| Parent story | Identity joining multiple beats of one episode | scenario engine + story context |
| MiniStory | Revisioned speech lease for one correlation | `MiniStoryRegistry` |
| Narrative edge | Editorial relation between already valid beats | commentary graph |
| Utterance | Realization of one committed beat | composer / optional LLM / TTS |

Three edge types remain intentionally separate:

1. **Detection edge:** a guard changes scenario state.
2. **Event lifecycle edge:** ENTER/UPDATE/EXIT or RESULT changes one emitted beat.
3. **Narrative edge:** the commentary graph rewards a truthful continuation or closure.

The commentary graph must never substitute for a missing detection edge.

Atomic scenarios use one flat timed FSM. Composite stories may use a bounded hierarchical
statechart with orthogonal regions when independent dimensions would otherwise create a Cartesian
explosion of states. Cross-region composition is read-only: a rule can emit from one consistent
region snapshot, but it must not hide multiple state mutations inside a getter.

## 6. Target pipeline and layer boundaries

```text
TelemetrySnapshot
  -> RaceContextAnalyzer
  -> RaceState + ObservationQuality
  -> ScenarioFeatureBuilder
       robust features, freshness, uncertainty
  -> ScenarioEngine
       named guards + timed state machines + episode identity
  -> ScenarioBeat / CandidateEvent
  -> EventManagerV2
       accepted lifecycle identity, cooldown, pit guard, run namespace
  -> EventEnvelope
       confidence, reason, episode metadata
  -> OverlayBus                         (peer consumer)
  -> CommentaryConsumer                (peer consumer)
       strict editorial tier
       -> graph score within tier
       -> MiniStory commit/revalidation
       -> microplan -> optional LLM -> TTS
```

Required ownership changes:

- `race/` continues to own `RaceState`, observation normalization, feature quality, run identity,
  and immutable story context;
- `events/scenarios/` becomes the owner of scenario state and emitted candidate facts;
- `RaceObserver` stops accumulating new independent detection policies after migration;
- existing observer FSMs move one at a time behind compatibility facades;
- `commentary/` consumes `EventEnvelope`; it never holds a live `RaceObserver` reference and never
  reads raw iRacing telemetry;
- overlay and commentary remain peer consumers of the same accepted envelope stream.

## 7. Scenario definition contract

### 7.1 Storage and validation

Runtime scenario definitions live under:

```text
src/irswitch/events/scenarios/data/*.json
```

The checked-in reference in `docs/scenarios/` is a design fixture until Phase 1 moves a validated
copy into runtime data.

The loader uses the standard library only. It must:

- require `schemaVersion`, `scenarioId`, and `scenarioVersion`;
- reject unknown top-level fields, states, guards, actions, units, and reset reasons;
- reject duplicate transition IDs and unreachable states;
- reject negative windows, holds, timeouts, or evidence weights;
- validate that all emitted event types and phases are registered;
- validate that identity inputs exist before an episode can emit;
- fail soft at application startup: log one actionable error, keep the legacy detector active,
  and never crash the race loop.

### 7.2 No expression language

JSON selects guard IDs and typed parameters. Guard implementations remain reviewed Python:

```python
GuardFn = Callable[[ScenarioFrame, EpisodeMemory, GuardParams], GuardResult]

GUARDS = {
    "incident_count_rising": incident_count_rising,
    "surface_off_track": surface_off_track,
    "on_track_motion_confirmed": on_track_motion_confirmed,
}
```

The loader must not interpret strings such as `"speed > 2.5 and on_track"`.

### 7.3 Required scenario fields

Each scenario defines:

- scope: supported `overlay_mode` values and subject;
- identity: session, `run_epoch`, actor, and episode sequence;
- observations: field, unit, maximum age, and missing-data policy;
- features: registered estimator ID and reset scope;
- parameters: bounded typed constants and any approved config binding;
- states, or factorized orthogonal regions for composite stories: semantic meaning and terminal
  status;
- transitions: source, target, guard, window, hold, priority, action, and emission;
- emissions: event type, phase, correlation suffix, metrics, confidence rule, and parent story;
- coalescing: whether a new edge updates or starts an episode;
- conflicts: pit, towing, disconnect, finish, and competing scenario behavior;
- reset: session, run, hero, target, and timeout rules;
- Director policy: editorial family, narratability, and closure semantics;
- acceptance traces and measurement tolerances.

### 7.4 Determinism

Given the same:

- ordered input frames;
- normalized field values;
- monotonic timestamps;
- scenario/config version;
- initial session and run identity;

the engine must produce byte-equivalent ordered `ScenarioBeat` values before event sequence
stamping.

Rules:

- timers use injected monotonic time only;
- `clock = state | episode` anchors transition windows/deadlines (default `state`);
- `holdS` is an uninterrupted guard-match interval; unknown/nonmatch breaks it;
- no frame-count delays;
- same-time transitions use definition order, then transition ID as a stable tie-break;
- one engine tick may emit multiple beats only in declared order;
- missing or stale observations are `UNKNOWN`, never false or zero;
- NaN and infinity are invalid observations;
- state and history collections are bounded;
- a scenario exception is isolated, recorded, and cannot stop other scenarios or the main loop.

## 8. Internal data model

The first implementation should introduce immutable types equivalent to:

```python
@dataclass(frozen=True)
class EvidenceValue:
    value: object | None
    observed_at: float
    age_s: float
    valid: bool
    quality: float                 # [0, 1]
    uncertainty: float | None      # same unit as value when meaningful
    source: str


@dataclass(frozen=True)
class GuardResult:
    decision: GuardDecision        # MATCH | NO_MATCH | UNKNOWN
    confidence: float              # [0, 1]
    reason: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioBeat:
    scenario_id: str
    scenario_version: int
    episode_id: str
    parent_story_id: str
    beat_id: str
    event_type: str
    phase: str
    priority: int
    confidence: float
    reason: str
    metrics: Mapping[str, object]
```

`GuardResult.matched` and `.unknown` are derived properties. Unknown confidence is zero.
All nested evidence, episode facts and beat metrics are frozen snapshots rather than mutable
aliases. The atomic kernel binds reviewed Python handlers explicitly; a valid design JSON alone
does not activate a detector.

`CandidateEvent` gains optional, backwards-compatible fields for `confidence`, `reason`,
`scenario_id`, `episode_id`, and `parent_story_id`, all with inert defaults. The V4 adapter copies
`confidence` and `reason` into the existing `EventEnvelope` fields. Episode metadata remains
internal metrics in Phase 1; promoting it to a public wire field requires an `API.md` schema
update.

### 8.1 Identity

An episode ID is stable and namespaced:

```text
scenario:<scenario-id>:session:<subsession>:<session-num>:run:<epoch>:hero:<car>:episode:<n>
```

Every beat receives its own correlation derived from the episode:

```text
<episode-id>:beat:incident
<episode-id>:beat:aftermath
<episode-id>:beat:recovery
```

This is intentional. One episode can contain several independently spoken MiniStories, while
`parent_story_id == episode_id` lets the graph and diagnostics compose them into a whole.

Session change, `run_epoch` change, or authoritative hero identity change invalidates all active
episodes before the first frame of the new scope is evaluated.

## 9. Evidence, confidence, and abstention

### 9.1 Feature quality

Every derived feature provides:

- value and unit;
- sample count and time span;
- latest source age;
- quality in `[0, 1]`;
- uncertainty when calculable;
- reset reason.

Initial mathematical upgrades should be small and reviewable:

- median/Hampel rejection for isolated gap and lap-distance outliers;
- target-keyed histories so one opponent never contaminates another;
- weighted linear regression or an alpha-beta filter for closing rate;
- explicit standard error for a fitted slope;
- hysteresis and minimum dwell on every noisy boundary;
- CUSUM only for sustained pace/trend changes where a fixed threshold is inadequate.

A Kalman filter may follow after replay evidence shows its process/noise model is stable. Bayesian
online change-point detection and learned sequence models are not Phase 1 requirements.

### 9.2 Confidence combination

Scenario confidence is an evidence score, not a replacement for hard validity. A transition first
passes hard guards, then combines independent or grouped evidence using a versioned Python policy.

The default policy is bounded log-odds addition:

```text
logit(p) = prior_log_odds + sum(weight_i * evidence_log_likelihood_i)
p = clamp(sigmoid(logit(p)), 0.01, 0.99)
```

Correlated evidence, such as speed and lap-distance motion, belongs to one evidence group and must
not be counted twice. The trace records every contribution.

Each transition declares:

- `enterConfidence`;
- `stayConfidence` when applicable;
- `exitConfidence` or an explicit inverse guard;
- minimum hold;
- maximum missing duration.

If required evidence is missing or stale beyond its allowance, the result is `UNKNOWN`. An unknown
transition does not emit a guessed fact and does not silently reset an active episode unless a
declared timeout or scope reset occurs.

## 10. Director integration

The #215 editorial invariant remains absolute. Candidate selection is lexicographic:

```text
1. validity and fresh MiniStory identity
2. strict editorial tier
3. within-tier scenario/graph utility
4. deterministic source order and stable ID tie-break
```

Confidence can affect only candidates within the same editorial tier. It cannot make a battle
beat outrank an incident or make any event outrank FINISH.

The initial shadow utility is:

```text
within_tier_utility = existing_graph_score
                      + clip(6 * logit(confidence), -12, 12)
                      - staleness_penalty
```

This formula is diagnostic in Phase 1. It becomes authoritative only after calibration against
held-out full-session replays. Scenario transitions should normally abstain before emitting weak
beats, so Director confidence is a ranking refinement, not a truth repair mechanism.

The following #215 behavior is unchanged:

- one current highest-priority waiter, not a speak-all FIFO;
- newer equal-tier continuation replaces an older waiter;
- failed or invalid LLM polish is silent when polish is enabled;
- `MiniStoryRegistry.commit()` revalidates run, actor, relation, order revision, and resolved facts;
- FINISH preserves result semantics;
- overlay and commentary receive the same authoritative accepted events.

The detailed sequence-graph audit, required graph-v3 selectors, parent-story edge identity,
node inventory, path matrix, text migration, and regressions for the first composite scenario are
normative in [track_excursion_story_spec.md](track_excursion_story_spec.md#9-required-graph-and-microplan-changes).

One explicit scenario change is proposed for Phase 3: `BACK_UNDER_WAY` moves from the generic
fallback tier (`100`) to the aftermath tier (`250`) when it carries a valid incident-recovery
episode identity. It still cannot outrank a lap, pit, sector, battle, position, incident, flag,
start, or finish beat. The change protects closure from unrelated filler without weakening strict
tiers. Until that change is enabled, shadow diagnostics compare both outcomes and production keeps
the baseline tier.

## 11. Reference scenario: incident to recovery

The normative machine-readable draft is
[`incident_offtrack_recovery_v1.json`](scenarios/incident_offtrack_recovery_v1.json).

Its semantic state model is:

```text
IDLE
  -- incident counter rises --> CLASSIFYING

CLASSIFYING
  -- off-track evidence held --> DISPLACED_OFF_TRACK
  -- tow evidence            --> TOWING
  -- on-track stopped held   --> STALLED_ON_TRACK
  -- on-track motion held    --> ROLLING
  -- insufficient evidence   --> UNKNOWN_RESOLVED

DISPLACED_OFF_TRACK / STALLED_ON_TRACK
  -- on track + not towing + motion held --> RECOVERED

TOWING
  -- tow cleared + on track + motion held --> RECOVERED

ROLLING / RECOVERED / UNKNOWN_RESOLVED
  --> terminal
```

### 11.1 Behavior-preserving and improved semantics

The migration has two explicit steps:

1. **Characterization mode:** reproduce current `INCIDENT`, `INCIDENT_AFTERMATH`, and
   `BACK_UNDER_WAY` timing and values from the baseline branch.
2. **Improved mode:** classify evidence over a bounded temporal window, give the whole episode one
   parent identity, distinguish `off_track`, `stalled_on_track`, `towing`, `rolling`, and
   `unknown`, and expose confidence/reasons.

Existing event types remain:

| Beat | Existing event type | Purpose |
| --- | --- | --- |
| Root | `INCIDENT` | Incident count rose by the configured narratable delta |
| Consequence | `INCIDENT_AFTERMATH` | What happened immediately after the incident |
| Closure | `BACK_UNDER_WAY` | Confirmed return to usable on-track motion |

During compatibility rollout, `INCIDENT_AFTERMATH.metrics.kind` remains `stalled` or `rolling` for
existing copy. New exact semantics live in `metrics.cause` as `off_track`, `stalled_on_track`,
`towing`, or `rolling`. Commentary copy may migrate to `cause` only after its validator and
variants are covered. This avoids a silent public schema break.

### 11.2 Temporal rules

- any authoritative incident-count rise starts or coalesces an internal episode;
- the public `INCIDENT` beat still requires `delta >= incident_min_delta`;
- rises within `0.75 s` coalesce into the active episode;
- off-track evidence may occur from `0.40 s` before to `1.20 s` after the counter edge;
- one isolated off-track sample does not classify; evidence must hold for `0.20 s` or be observed
  in two ordered frames;
- motion on track requires speed `>= 2.5 m/s` or valid lap-distance movement and a `0.35 s` hold;
- stopped requires speed `<= 1.0 m/s` with no contradictory distance movement for `0.35 s`;
- the `1.0..2.5 m/s` speed band is unknown and may use lap distance as fallback;
- recovery requires on-track, no tow, and confirmed motion for `0.60 s`;
- an unresolved episode times out after `90 s` without inventing `BACK_UNDER_WAY`;
- disconnect freezes transition timers for the configured grace and then resets without output;
- session, run, or hero change resets immediately without output.

### 11.3 Required narrative behavior

- `INCIDENT` and `INCIDENT_AFTERMATH` in the same Director batch remain mutually exclusive, with
  `INCIDENT` preferred, matching the baseline.
- `BACK_UNDER_WAY` is a protected closure only for the same `parent_story_id`.
- the graph may connect `INCIDENT -> BACK_UNDER_WAY` for the same parent story when an immediate
  aftermath beat was correctly suppressed and never heard;
- a recovery from another run or incident cannot close the active story.
- if the root incident is not narratable because its delta is below the configured threshold, a
  high-confidence aftermath may still exist for diagnostics, but its speech policy defaults to
  silent until product review.
- no nearby opponent is named as the cause without an independent contact fact; proximity remains
  context only.
- the audience-facing vocabulary and expanded precursor/outcome taxonomy are normative in
  [track_excursion_story_spec.md](track_excursion_story_spec.md); internal compatibility event
  names do not authorize generic incident wording.

## 12. Observability and explanation contract

Do not log per-frame non-matches at INFO. Emit one DEBUG/tape decision row for:

- episode start, coalesce, transition, terminal state, timeout, and reset;
- emitted or suppressed beat;
- legacy/shadow divergence;
- Director selection when confidence changes within-tier ordering.

Each transition row contains:

```json
{
  "kind": "scenario_transition",
  "scenarioId": "incident_offtrack_recovery",
  "scenarioVersion": 1,
  "episodeId": "...",
  "parentStoryId": "...",
  "from": "CLASSIFYING",
  "to": "DISPLACED_OFF_TRACK",
  "transitionId": "classify_off_track",
  "atMono": 824.698,
  "guard": "surface_off_track_held",
  "confidence": 0.94,
  "holdRequiredS": 0.2,
  "holdObservedS": 0.24,
  "evidence": [
    {"name": "surface", "value": "OFF_TRACK", "ageS": 0.03, "quality": 1.0}
  ],
  "reason": "off_track_seen_in_incident_window"
}
```

Stable reason IDs are part of the test contract. Human text may change; IDs may not change without
a scenario version bump.

Counters exposed to runtime diagnostics:

- active episodes by scenario;
- transitions and emitted beats;
- unknown/abstained classifications;
- timeouts and resets by reason;
- legacy/shadow disagreements;
- identity conflicts;
- invalid/stale evidence;
- Director confidence reorders;
- scenario exceptions.

## 13. Replay and evaluation contract

### 13.1 Three replay levels

1. **State replay:** existing `RaceState -> events` fixtures remain fast unit/integration tests.
2. **Observation replay:** normalized timestamped observations exercise features and scenarios.
3. **Full speech replay:** tape input exercises analyzer, scenario engine, manager, graph, scheduler,
   MiniStory commit, and a fake deterministic TTS sink.

No one level substitutes for the others.

### 13.2 Ground truth

Labels are intervals with boundary tolerance, not only event points:

```text
scenario, episode, state, earliest_start, latest_start, earliest_end, latest_end
```

Train/tune and acceptance sets are split by complete session or stream. Adjacent ticks from one
episode must never be randomly split across sets.

### 13.3 Metrics

Per scenario and globally measure:

- episode precision, recall, and F1;
- temporal intersection-over-union;
- onset and offset error;
- fragmentation and unintended episode merges;
- actor/target identity switches;
- unknown/abstention rate;
- false narration rate;
- spoken onset latency;
- closure completion rate;
- stale/rejected LLM drafts;
- dropped, replaced, and interrupted utterances by reason.

Thresholds are selected offline using grid search first. Bayesian optimization is allowed later
only if the parameter space justifies it. Chosen parameters, corpus revision, metrics, and
scenario version are committed together. Production never tunes itself online.

## 14. Implementation phases

### Phase 0 — characterization on the fix baseline

- Freeze current #215 tests and Test 7 replay evidence.
- Add exact characterization for current incident/aftermath/recovery timing and correlations.
- Record known inconsistencies: exact-tick incident branch, separate correlations, and default
  confidence `1.0`.
- Do not change speech or overlay output.

### Phase 1 — types, loader, validator, and shadow engine

- Add `events/scenarios/model.py`, `guards.py`, `loader.py`, `engine.py`, and typed trace records.
- Move the validated reference JSON to runtime data.
- Add `[race_scenarios] mode = legacy|shadow|active`, default `legacy`.
- Run legacy and scenario detector from the same immutable `RaceState` in `shadow`.
- Emit comparison diagnostics only; publish legacy events.
- Keep histories bounded and isolate every scenario exception.

### Phase 2 — incident recovery migration

- Implement named guards and the reference FSM test-first.
- Give root, aftermath, and recovery one stable parent episode identity.
- Route scenario beats through `EventManagerV2` and the existing pipeline.
- Preserve event types, baseline tiers, MiniStory commit rules, and legacy metric compatibility.
- Make `RaceObserver.aftermath` a compatibility facade, then remove duplicate ownership after the
  active rollout gate.

### Phase 3 — confidence-aware Director shadow

- Populate existing envelope confidence and reason fields.
- Add parent-story matching to graph candidates and edges.
- Compute confidence adjustment in shadow; retain existing active selection.
- Verify that strict tier ordering and FINISH dominance are unchanged.
- Enable within-tier confidence only after held-out replay review.

### Phase 4 — migrate structured scenarios

Migrate in increasing ambiguity order:

1. pit cycle;
2. battle intensity and outcome;
3. overtake/position change as one composite episode;
4. practice/quali pace changes;
5. session and flag narratives.

Each migration removes one duplicate policy owner only after its shadow gate passes.

### Phase 5 — active rollout and cleanup

- Enable `active` in a test profile, not as the shipped default.
- Complete at least two full race streams and one practice/quali stream without P0/P1 regression.
- Promote active default in a separate reviewed change.
- Remove legacy facades only after rollback evidence and release review.

## 15. Acceptance criteria

### Architecture and determinism

- [ ] One versioned scenario contract defines states, guards, timers, identity, reset, emissions,
      and acceptance traces.
- [ ] Unknown guard/state/action/field names fail validation and fall back to legacy without
      crashing the main loop.
- [ ] The same ordered input and monotonic timestamps produce identical ordered beats.
- [ ] Timers are monotonic and histories are bounded.
- [ ] Scenario detection contains no commentary text, TTS calls, or OBS policy.

### Identity and lifecycle

- [ ] Every episode is namespaced by session, run epoch, hero, and episode sequence.
- [ ] Every beat has an independent correlation and the same stable parent story.
- [ ] Session/run/hero reset prevents a stale recovery from closing a new episode.
- [ ] Accepted identity remains authoritative through EventManager and MiniStory revalidation.
- [ ] Equal-priority queue replacement and failed-LLM silence from #215 are unchanged.

### Incident recovery

- [ ] Off-track before or shortly after an incident edge is classified within the declared window.
- [ ] A single isolated off-track sample does not classify the episode.
- [ ] Off-track motion cannot be classified as on-track rolling.
- [ ] Recovery requires on-track, no tow, and motion held for `0.60 s`.
- [ ] Missing speed uses lap-distance fallback; missing both sources abstains.
- [ ] Incident increments inside the coalesce window create one episode.
- [ ] Timeout/reset never invents `BACK_UNDER_WAY`.
- [ ] Root, aftermath, and recovery events preserve current public event types.

### Director and observability

- [ ] Confidence changes ordering only within one strict editorial tier.
- [ ] A lower-tier event can never beat FINISH, flags, incident, or position through confidence.
- [ ] Closure bonus requires the same parent story.
- [ ] Every emitted, suppressed, reset, and unknown transition has a stable reason ID.
- [ ] Shadow divergence can be reconstructed from tape without per-tick INFO spam.

### Evaluation

- [ ] Unit tests cover every transition, exact boundary, missing-data branch, timeout, and reset.
- [ ] Property tests cover timestamp jitter, duplicated frames, invalid scalars, and bounded memory.
- [ ] Observation replay covers positive, negative, and near-boundary traces.
- [ ] Full speech replay verifies ordering, replacement, MiniStory commit, and fake TTS timing.
- [ ] Held-out sessions meet scenario-specific latency and false-narration gates documented with the
      corpus revision.

## 16. Test plan

### Unit

- JSON validator and typed loader;
- each registered guard as a pure function;
- timed transition holds and time windows with injected monotonic time;
- confidence combination and correlated evidence groups;
- episode/correlation identity and reset;
- bounded history eviction;
- fail-soft isolation of one broken scenario.

### Integration

- `RaceState -> ScenarioEngine -> EventManagerV2 -> EventEnvelope`;
- parent story through graph candidates and MiniStory tokens;
- legacy/shadow comparison;
- same-batch incident/aftermath suppression;
- strict editorial tiers with confidence enabled;
- disconnect, reconnect, session change, same-session run rewind, and hero change.

### Replay / end to end

- Test 7 incident sequence around 13:44;
- off-track without incident increase;
- incident increase without off-track evidence;
- off-track at speed followed by on-track recovery;
- on-track stopped then recovery;
- tow followed by recovery;
- missing speed with valid lap-distance movement;
- missing both motion sources;
- multiple incident increments in and outside the coalesce window;
- position change while aftermath commentary is waiting;
- delayed/rejected LLM result followed by current valid recovery closure.

### Manual

- run scenario mode `shadow` for a complete stream;
- inspect transition reasons and divergence counters;
- confirm no extra HUD cards or audio in shadow;
- replay with active output into fake TTS before enabling real speech;
- verify service health and runtime version after the eventual implementation restart.

## 17. Configuration and documentation impact

This commit is documentation-only.

Implementation will require:

- `CONFIG.md` and `config/config.example.ini` for `[race_scenarios].mode` and any approved public
  override;
- `COMMENTARY_ENGINE.md` for confidence, parent-story sequencing, and unchanged strict tiers;
- `API.md` only if episode metadata becomes a public V4 field;
- `docs/scenario_coverage_matrix.md` as each legacy detector migrates;
- an implementation report with corpus revision and replay metrics.

Initial defaults:

```ini
[race_scenarios]
mode = legacy
```

No existing key changes meaning. `incident_min_delta` remains the public threshold for emitting
the root incident beat. Internal evidence windows remain versioned scenario constants unless a
demonstrated operational need justifies a reviewed configuration key.

Migration note: `shadow` produces diagnostics only. `active` changes event detection and must not
be shipped as default until the replay and live gates pass.

## 18. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Duplicate events while legacy and scenario paths coexist | Shadow path cannot publish; active switch has one explicit owner |
| Overconfident correlated evidence | Evidence groups; calibration on held-out sessions |
| Late incident comment due to classification window | Immediate decisive evidence; bounded root grace; measure spoken latency |
| New knobs become unmaintainable | Typed policy defaults; only proven operational overrides enter INI |
| Scenario JSON becomes hidden code | Named guards only; strict schema; no expressions |
| Stale recovery crosses restart | Session/run/hero namespaced identity and reset-before-observe ordering |
| Director uses confidence to violate editorial safety | Lexicographic tier first; bounded within-tier adjustment only |
| Tape becomes noisy | transitions only at DEBUG/tape; aggregate counters at INFO/status |
| Fix #215 regresses | keep its regressions as mandatory migration gate |

## 19. Definition of done for the implementation PR

- all acceptance criteria checked with evidence;
- focused and full repository tests pass;
- formatter, lint, and type checks pass;
- legacy/shadow comparison report attached;
- Test 7 reference trace and held-out traces recorded with corpus revision;
- docs and config contracts updated as listed above;
- exactly one runtime owner publishes each migrated event;
- rollback to `legacy` is tested;
- normal PR release labeling and local service/version verification are complete.

**TDD exception for this document:** docs-only design change. No runtime behavior is modified.

**Verification:** Markdown links, reference JSON syntax, baseline branch/commit, current event names,
and #215 lifecycle invariants are checked against the repository.

**Risk:** implementation may diverge from the design before a tracking issue is created.

**Mitigation:** treat this file and the versioned reference scenario as the implementation contract;
record intentional deviations with rationale and a scenario version change.
