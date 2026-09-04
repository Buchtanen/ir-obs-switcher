# Track excursion scenario engine — implementation plan

Status: implementation in progress; current-signal subset connected for active development tests

Baseline: `codex/fix-overlay-commentary-test-7` at `4497040`

Source specifications:

- [Deterministic race scenario engine](race_scenario_engine_spec.md)
- [Track excursion story](track_excursion_story_spec.md)
- machine-readable contracts in [`docs/scenarios/`](scenarios/)

Tracking: [#216](https://github.com/Buchtanen/ir-obs-switcher/issues/216).
Actual completed scope and evidence are in the
[implementation progress report](track_excursion_implementation_progress.md); the sequence below
is not a claim that every slice is complete.

## 1. Delivery decision

**Approved development amendment (2026-09-03):** the user requested connecting and logging the
new path now, then evaluating it. `[race_scenarios] mode=active` is therefore the development
default; mandatory pre-activation shadow/recorded replay gates below are superseded for this
subset. Full taxonomy, generic JSON execution and calibrated causes remain unfinished.
The actual shipped subset and deviations are documented in
[the live test contract](track_excursion_live_test.md). Legacy text inventory is not frozen.

The change is delivered as a sequence of small, reversible vertical slices. It is not one large
rewrite of `RaceObserver`, `Director`, and the commentary graph.

The first active scope is intentionally narrower than the complete story taxonomy:

1. establish stable episode identity and deterministic scenario transitions;
2. recognize facts supported by current telemetry;
3. make the graph able to narrate every valid ending of a track excursion;
4. prohibit generic “incident” wording for physical driving events;
5. run the new path in shadow and compare it with the legacy path;
6. activate it only after replay gates pass;
7. add ambiguous causes such as slide, contact, braking overshoot, and avoidance later, after their
   required inputs exist and are calibrated.

This order protects the successful Test 7 behavior around 13:44 and prevents richer commentary
from being built on guessed facts.

## 2. Non-negotiable invariants

Every implementation slice must preserve these contracts:

- the same ordered observations and monotonic timestamps produce the same ordered scenario beats;
- one physical excursion has one `episode_id` and one stable `parent_story_id`;
- individual beats have distinct `correlation_id` values;
- accepted identity remains authoritative through `EventManagerV2`, graph selection, Director,
  MiniStory revalidation, composition, and TTS commit;
- `legacy` remains the shipped default until a separate rollout change is approved;
- `shadow` never publishes audio, overlay events, or extra cards;
- only one runtime owner publishes a migrated event in `active` mode;
- a missing or invalid scenario definition fails soft to the legacy path;
- strict editorial tiers and all #215 queue, replacement, MiniStory, and failed-LLM rules remain
  unchanged;
- an off-track fact is narrated as track excursion/off-track/track limits or remains silent;
- “incident” is allowed only in the numeric `INCIDENT_POINTS_UPDATE` category;
- causes and damage are optional hypotheses and are never invented;
- timeout, tow, reset, or missing motion evidence never fabricate a recovery;
- no scenario detector contains commentary text, OBS policy, or TTS calls.

## 3. Dependency map

```text
fix baseline + characterization
              |
              v
shared contract freeze
  |           |                 |
  v           v                 v
scenario      graph-v3          vocabulary
kernel        kernel            validator
  \           |                 /
   +----------+----------------+
              |
              v
current-signal Track Excursion FSM
              |
              v
pipeline identity + shadow comparison
              |
              v
production graph + Director + composition
              |
              v
replay evaluation and MVP active gate
              |
              v
pace/dynamics inputs -> cause classifiers -> active cause gate
```

The three kernel streams may run in parallel only after the shared contract is frozen. The
production graph, Director arbitration, and active event ownership form one sequential integration
spine because they jointly decide what is heard.

## 4. Work inventory

| ID | Goal | Primary ownership | Depends on |
| --- | --- | --- | --- |
| S0 | Freeze current behavior and reference evidence | characterization tests and replay fixtures | baseline |
| S1 | Freeze shared types, names, identities, and rollout rules | contracts, event catalog proposal, ADR/spec amendments | S0 |
| P1 | Build deterministic scenario kernel | new `events/scenarios/` modules and unit tests | S1 |
| P2 | Build graph schema/runtime v3 kernel | `commentary/graph.py`, `commentary/graph_runtime.py`, fixture tests | S1 |
| P3 | Build semantic vocabulary validator | new vocabulary module and isolated tests | S1 |
| S2 | Implement current-signal Track Excursion FSM | scenario definition, guards, state reducer, observer facade | P1–P3 merged |
| S3 | Carry story identity through the event pipeline | candidate/envelope/manager/pipeline/context serialization | S2 |
| S4 | Migrate production commentary behavior | production graph, priorities, Director, composer, validators | S3 |
| P4 | Build replay corpus and scoring report | labeled fixtures, replay harness, metrics | stable S1 contract |
| S5 | Integrate overlay compatibility and one-owner switching | audience/catalog/overlay mapping and feature modes | S4 |
| S6 | Run shadow and activate the MVP behind an explicit gate | evaluation, docs, configuration, release evidence | S5 + P4 |
| S7 | Add pace reference and sustained pace-loss outcome | pace feature, guards, graph extension | MVP shadow stable |
| S8 | Extract vehicle-dynamics and conflict inputs in shadow | telemetry/model/context changes | MVP stable |
| P5 | Classify slide/spin | isolated classifier, calibration, tests | S8 |
| P6 | Classify contact | isolated classifier, calibration, tests | S8 |
| P7 | Classify braking overshoot/avoidance | isolated classifiers, references, tests | S8 |
| S9 | Integrate proven causes and repair confirmation | FSM/graph/Director integration and rollout gates | P5–P7 evidence |

## 5. Sequential integration spine

### S0 — characterize the fix baseline

Purpose: turn the known-good 13:44 Test 7 sequence and current flaws into executable evidence
before behavior changes.

Changes:

- freeze the observation order, event order, correlations, selection, composition, and speech
  timing for the successful off-track → recovery sequence;
- add focused characterization for the current same-tick incident/aftermath suppression;
- record the known graph defect where `incident_off_track` has no outgoing closure edge;
- add negative traces: one noisy off-track sample, missing speed, tow without recovery, and two
  adjacent but independent excursions;
- replace no production behavior in this slice.

Likely files:

- `tests/test_incident_aftermath.py`
- `tests/test_ministory.py`
- `tests/test_commentary_scheduler_director.py`
- `tests/test_replay_input_scenarios.py`
- new versioned fixtures under `tests/fixtures/scenarios/`

Exit gate:

- Test 7 reference trace is reproducible;
- tests clearly distinguish desired behavior from documented legacy defects;
- fixture timestamps use an injected monotonic clock rather than wall time.

### S1 — freeze the cross-layer contract

Purpose: prevent parallel work from inventing incompatible meanings for episode, beat, graph edge,
or confidence.

Decisions to make explicit in code-facing types:

- `scenario_id`, `scenario_version`, `episode_id`, `parent_story_id`, `beat_id`, `beat_role`;
- cause, outcome, temporal relation, evidence level, confidence, and stable reason IDs;
- reset namespace: session, run epoch, hero, episode sequence;
- graph-v3 node `match` fields and edge identity policies;
- compatibility mapping from legacy event names to the new story vocabulary;
- exact ownership matrix for `legacy`, `shadow`, and `active` modes;
- public versus internal fields and serialization rules;
- versioning rule: semantic/threshold change requires scenario version and replay corpus revision.

The frozen contract is reflected in both JSON specifications and a small typed Python model. Do not
add a general expression language; scenario JSON may reference only registered guards and actions.

Exit gate:

- unknown field, guard, action, state, event type, or identity policy fails validation;
- compatibility fields remain optional so legacy producers keep working;
- no active runtime path is enabled.

### S2 — implement the current-signal Track Excursion FSM

Purpose: recognize the truthful core story using only data already extracted reliably.

Supported in this slice:

- confirmed off-track with debounce/hold;
- moving off-track versus stopped after excursion;
- track rejoined;
- motion restored as a separate fact from track rejoined;
- control and normal-pace conclusions remain unavailable until their independent evidence exists;
- Race tow started;
- Practice/Qualifying reset to pits;
- driven pit entry when geometry and movement support it;
- missing-data abstention and timeout without invented recovery.

Explicitly unsupported here:

- slide/spin classification;
- vehicle/barrier contact classification;
- braking overshoot;
- avoidance;
- damage or repair confirmation;
- sustained pace loss until a clean segment reference exists.

`RaceObserver.aftermath` becomes a compatibility facade, not a second state owner. During shadow it
may still produce the legacy result for comparison, but it must not mutate state observed by the new
engine.

Required tests cover exact time boundaries, duplicate frames, invalid scalars, missing motion
sources, run/session/hero resets, bounded history, and deterministic replay.

### S3 — propagate story identity and compare in shadow

Purpose: make scenario facts usable by the existing event pipeline without changing user-visible
output.

Changes:

- extend candidate/envelope metadata backward-compatibly;
- preserve accepted episode identity across event normalization and queue revalidation;
- add transition-only diagnostics and bounded divergence counters;
- add `[race_scenarios] mode = legacy|shadow|active`, default `legacy`;
- run legacy and scenario detection from the same immutable `RaceState` snapshot in shadow;
- compare emitted type, onset, closure, identity, confidence, and suppression reason;
- keep legacy as the only publisher in `legacy` and `shadow`.

Likely files:

- `src/irswitch/overlay/protocol.py`
- `src/irswitch/events/envelope.py`
- `src/irswitch/events/manager_v2.py`
- `src/irswitch/race/pipeline.py`
- `src/irswitch/race/context.py`
- `src/irswitch/race/runtime.py`
- `src/irswitch/overlay/settings.py`

Exit gate:

- no duplicate public events;
- no extra speech or HUD cards in shadow;
- disconnect/reconnect, hero change, session change, and run rewind cannot cross-link stories;
- one broken scenario is isolated and legacy continues.

### S4 — migrate the production graph, Director, and language behavior

Purpose: close the whole Track Excursion Story and ensure the selected words match the recognized
fact.

This is one-owner sequential work. The owner updates together:

- `src/irswitch/commentary/data/sequence_graph.json` to schema v3;
- `src/irswitch/commentary/priorities.py`;
- `src/irswitch/commentary/director.py`;
- `src/irswitch/commentary/composer.py`;
- final authored/composed/LLM-output validation and the TTS commit path;
- `src/irswitch/events/audience.py` and the event catalog where required.

Required content work:

- add all root, development, closure, and terminal nodes named by the story specification;
- implement explicit `same_parent_story`, `caused_by_parent_story`, and `same_run` edges;
- add direct truthful closure paths when an intermediate beat was suppressed;
- map legacy `incident_off_track` input to `track_excursion` during migration;
- separate `track_rejoined`, `control_regained`, and `normal_running_resumed`;
- distinguish Race tow from Practice/Qualifying reset;
- keep `limping_to_pits` observational and do not assert damage;
- require independent repair evidence before `pit_for_repairs` copy is eligible;
- remove hard-coded “od incidentu/from the incident” history labels;
- ensure raw internal enum labels such as `stalled` or `rolling` cannot leak into Czech speech.

Director rules:

- strict editorial tier is compared before confidence;
- confidence may influence order only within one tier;
- root/development/closure relation is matched by parent story, not reused correlation;
- cause-specific roots fall back to confirmed `track_excursion` when evidence is insufficient;
- a direct closure remains eligible after same-batch development suppression;
- accepted parent identity is revalidated immediately before speech commit.

Graph tests replace brittle exact assertions of 54 nodes and 24 edges with named node inventory,
mode-aware reachability, identity conflict, direct closure, and forbidden-vocabulary assertions.

### S5 — integrate overlay compatibility and event ownership

Purpose: prevent commentary taxonomy changes from accidentally changing HUD semantics or producing
duplicate visual events.

Changes:

- explicitly label each new fact as commentary-only, overlay-visible, or compatibility-only;
- keep current overlay payloads stable unless a separate public API change is approved;
- select exactly one publisher per event in `active` mode;
- preserve legacy metric names through a documented adapter where operational dashboards need them;
- verify that scenario exceptions cannot crash the race loop.

This step is sequential even if only a small HUD change is needed. Overlay HUD files are not split
between multiple workers.

### S6 — shadow evaluation and MVP activation

Activation is not part of the structural implementation PR. It is a separate reviewed decision.

Required evidence:

- deterministic observation replays for all positive, negative, and boundary cases;
- full speech replay with fake TTS and delayed/rejected LLM results;
- Test 7 at 13:44 retains the good event identification and temporal commentary;
- held-out Race and Practice/Qualifying traces;
- root precision/recall, false narration, unknown rate, onset latency, closure completion, identity
  switches, and stale/rejected draft metrics;
- at least two full race streams and one Practice/Qualifying stream without P0/P1 regression;
- explicit rollback test from `active` to `legacy`.

First active MVP may narrate only confirmed core facts and current-signal endings. Cause stays
`unknown` unless independently proven. The shipped default changes only in a later release change.

## 6. Safe parallel work

### Parallel wave A — after S1 contract freeze

These streams may run at the same time because their production file ownership does not overlap.

#### P1 — scenario engine kernel

Owns only new `src/irswitch/events/scenarios/` modules and their focused tests:

- typed models and traces;
- registry of named guards/actions;
- strict JSON loader and validator;
- deterministic timed engine with injected monotonic time;
- bounded histories and fail-soft per-scenario isolation.

It does not wire the engine into `race/pipeline.py`, edit Director, or edit the production graph.

Suggested issue/branch after approval: one new GitHub issue; `feat/scenario-engine-kernel`.

#### P2 — graph-v3 infrastructure

Owns:

- typed schema-v3 parsing in `commentary/graph.py`;
- identity matching and diagnostics in `commentary/graph_runtime.py`;
- isolated v3 fixture graphs and unit tests.

It must support v2 loading during migration. It does not edit the production
`sequence_graph.json`, Director, composer, or event catalog.

Suggested issue/branch after approval: one new GitHub issue; `feat/commentary-graph-v3`.

#### P3 — semantic vocabulary validator

Owns a new isolated vocabulary-policy module and focused CS/EN tests:

- typed semantic categories;
- inflection-aware forbidden “incident” token matching;
- sole allow-list category `INCIDENT_POINTS_UPDATE`;
- validation of authored variants and composed text through a reusable API;
- stable rejection reason IDs.

It does not yet change composer, polish, TTS, or the production graph; those call sites are wired by
S4 after merge.

Suggested issue/branch after approval: one new GitHub issue;
`feat/commentary-vocabulary-policy`.

### Parallel wave B — replay work alongside S2–S5

#### P4 — replay corpus and evaluator

Owns new fixtures/evaluation utilities and avoids production runtime files. It labels:

- Test 7 around 13:44;
- pure off-track and noisy one-frame off-track;
- slide/contact/overshoot/avoidance as `unknown` until supporting inputs exist;
- recovery, stopped, tow, reset, driven pit entry, missing-data abstention;
- two overlapping stories and run-boundary resets;
- counterfactual “near miss” traces.

The corpus is split into tuning and held-out sets. Threshold search happens offline; chosen
parameters, scenario version, corpus revision, and result metrics land together.

Suggested issue/branch after approval: one new GitHub issue; `test/track-excursion-replay`.

### Parallel wave C — only after S8 input contract

The following classifiers may be developed independently in shadow:

- P5 `feat/track-excursion-control-classifier`: slide versus spin versus generic loss of control;
- P6 `feat/track-excursion-contact-classifier`: contact hypothesis and temporal relation;
- P7 `feat/track-excursion-driving-causes`: braking overshoot and avoidance.

Each classifier owns separate pure feature/classifier modules and fixtures. None edits the shared
scenario definition, production graph, Director, or catalog. S9 integrates only classifiers that
pass their held-out accuracy and abstention gates.

## 7. Work that must not be parallelized

Do not split these across concurrent branches:

- the Track Excursion FSM definition and its event naming;
- production `sequence_graph.json` node and edge migration;
- Director root/development/closure arbitration;
- composer history semantics and final vocabulary enforcement;
- event catalog registration plus overlay visibility mapping;
- ownership switch from legacy aftermath to scenario engine;
- changes within the same Overlay HUD asset set;
- final active rollout and legacy-facade removal.

These areas share behavior contracts even where their files differ. Parallel edits would make a
green local test insufficient evidence that the complete spoken sequence is coherent.

## 8. Later feature slices

### S7 — pace model

Add a deterministic clean-lap/track-segment reference keyed by track configuration, car/class,
session conditions, and segment. The model must reject dirty, pit, tow, off-track, and traffic-
compromised samples. It may then support:

- sustained pace loss;
- slow continuation toward pits;
- normal pace resumed.

It still must not say the car is damaged. “Pit for repairs” needs a separate repair fact.

### S8 — additional telemetry extraction

Add inputs in one reviewed extraction slice before building cause classifiers:

- yaw/yaw rate and heading relative to track direction;
- steering, throttle, brake, lateral and longitudinal dynamics;
- optional wheel speeds;
- contact/impulse signals if iRacing exposes a trustworthy source;
- relative-car trajectories and a local track corridor;
- field validity, sampling age, and missing-data quality.

Extraction changes update `iracing/`, normalized models, tape format/version, and tests. New fields
remain observation-only/shadow and may not directly create commentary.

### S9 — integrate causes and repair outcomes

Integrate in increasing ambiguity order:

1. slide/spin/loss of control;
2. contact with unknown target, then vehicle/barrier only when independently supported;
3. braking overshoot against a trusted local reference;
4. avoidance against a conflict-corridor model;
5. repair confirmation from a trustworthy pit/service fact.

Each cause must be optional, calibrated, and allowed to abstain. Compound commentary requires the
confirmed excursion plus a cause above its category-specific threshold. Nearby cars, an incident
point increase, or low speed alone are never enough to name a contact, avoidance, or damage cause.

## 9. Configuration and compatibility matrix

| Scenario mode | Graph mode | Publisher | User-visible effect |
| --- | --- | --- | --- |
| `legacy` | v2 or v3-compatible | legacy aftermath | current behavior |
| `shadow` | v2 | legacy aftermath | diagnostics only |
| `shadow` | v3 shadow | legacy aftermath | detector and graph comparison only |
| `active` | invalid/incompatible | legacy fallback | no crash, explicit reason/counter |
| `active` | validated v3 | scenario engine | one event owner, new story semantics |

Initial public configuration:

```ini
[race_scenarios]
mode = legacy
```

Internal timing and confidence constants remain versioned scenario policy, not a collection of INI
knobs. A setting becomes public only when an operator has a demonstrated need to tune it.

## 10. Test and quality gates

### Per-PR gate

- tests are written before or together with the behavior;
- focused tests pass;
- full repository suite passes when shared contracts or runtime wiring change;
- formatter, linter, and type checks pass;
- no unbounded history, blocking async call, or wall-clock timer is introduced;
- all new exception paths fail soft and expose a bounded diagnostic reason;
- docs/config are updated in the same slice when their contract changes;
- the GitHub issue dev diary records commands, results, risks, and follow-ups.

### Graph-specific gate

- every selectable root reaches every mode-valid closure/terminal;
- direct closure exists when an intermediate beat is suppressed;
- different `parent_story_id` or run epoch cannot link;
- confidence never crosses a strict editorial tier;
- every authored and composed ordinary driving line passes the vocabulary validator;
- `INCIDENT_POINTS_UPDATE` is the only “incident” allow-list exception;
- no exact total-node or total-edge assertion is used as coverage evidence.

### Active rollout gate

- required replay metrics are reported against a named corpus revision;
- false narration and identity-switch regressions are zero for acceptance traces;
- timing regression versus the 13:44 reference is within the approved scenario-specific bound;
- no extra HUD/audio output occurs in shadow;
- rollback to `legacy` is exercised;
- removal of compatibility facades is deferred to a later PR.

## 11. Issue, branch, and merge strategy

The plan itself created no branches, worktrees, issues or agents. Implementation was subsequently
authorized and is tracked in #216 on the user-selected fix branch. No parallel agents/worktrees
have been started; the independent kernels are being implemented sequentially in this checkout.

After approval:

1. create one umbrella GitHub issue referencing both specifications and this plan;
2. create one GitHub issue for each independently deliverable stream; never invent issue numbers;
3. record a dev-diary entry at start, after important tests, and at completion;
4. branch each parallel stream from the exact merged S1 commit, not from drifting working trees;
5. assign exclusive file ownership as described above;
6. merge P1–P3 before starting shared S2 integration;
7. rebase/retest each integration PR against the latest fix-derived integration branch;
8. keep activation and legacy cleanup in separate reviewed changes.

Repository-style branch suggestions are included above. If the task runner requires a `codex/`
namespace, apply that host prefix without changing the semantic branch suffix.

## 12. Recommended PR sequence

| Order | Slice | Parallel? | User-visible behavior |
| --- | --- | --- | --- |
| 1 | S0 characterization | no | none |
| 2 | S1 contract freeze | no | none |
| 3 | P1 scenario kernel | yes, wave A | none |
| 3 | P2 graph-v3 kernel | yes, wave A | none |
| 3 | P3 vocabulary-policy kernel | yes, wave A | none |
| 4 | S2 current-signal FSM | no | none until active |
| 5 | S3 pipeline + shadow | no | diagnostics only |
| 5 | P4 replay corpus/evaluator | yes, isolated ownership | none |
| 6 | S4 graph/Director/composition | no | behind inactive gate |
| 7 | S5 overlay/event ownership | no | behind inactive gate |
| 8 | S6 MVP activation evidence | no | explicit test profile only |
| 9 | S7 pace model | no | shadow first |
| 10 | S8 dynamics extraction | no | observation/shadow only |
| 11 | P5–P7 cause classifiers | yes, wave C | shadow only |
| 12 | S9 cause integration | no | per-cause gated rollout |

## 13. MVP definition of done

The first implementation milestone is complete when:

- the scenario engine and graph-v3 contracts are versioned and strictly validated;
- current telemetry deterministically recognizes the core excursion and truthful current-signal
  outcomes;
- every beat has stable episode/parent identity and its own correlation;
- graph paths cover root, development, direct closure, and mode-specific terminals;
- confirmed off-track never selects generic incident/contact/loss-of-control wording;
- the numeric incident-points category is the only allowed “incident” wording;
- cause is `unknown` unless supported; unsupported classifiers remain disabled;
- shadow comparison is silent and reconstructable;
- Test 7 remains correct and all negative/boundary replays pass;
- active mode has exactly one event publisher and a tested legacy rollback;
- config, commentary documentation, scenario coverage matrix, and implementation metrics are
  updated;
- no legacy facade is deleted in the same change that first activates the replacement.

## 14. Explicitly skipped for the MVP

- online learning or production self-tuning;
- a free-form expression language in scenario JSON;
- neural or opaque end-to-end incident classification;
- claiming damage from speed loss, pit entry, or incident points;
- claiming contact from proximity alone;
- claiming retirement from tow alone;
- enabling cause-specific copy before telemetry extraction and held-out calibration;
- changing existing public overlay payloads without a separate API decision;
- wholesale migration of pit, battle, overtake, flag, and session stories before Track Excursion
  proves the architecture.

These are deliberately excluded to keep the first delivery deterministic, explainable, reversible,
and measurable.
