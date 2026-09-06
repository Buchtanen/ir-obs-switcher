# Prepared commentary graph completion plan

Status: automated implementation complete on `codex/fix-overlay-commentary-test-7`; active is the
default and audible stream-PC validation remains pending.

## Context

The prepared-commentary runtime currently creates situation-specific `semantic_key` values, but
all of them are ranked through the single `prepared_filler` graph node. That node contains only
schema placeholders and has no graph edges. The runtime therefore works as a hybrid: stage and
result branching live in Python while the graph does not describe the actual editorial tree.

This change makes the sequence graph the single source of truth for prepared situations. The graph
will own situation meaning, stage eligibility, mode, priority, terminality, factual contract,
relation, prohibited claims, generation guidance and transitions. Python will bind current facts
to a selected graph contract. The LLM will still generate 3–5 actual variants for every immutable
situation plan. Graph anchors are review and generation guidance only; they are never a static
speech fallback. Exhausted generation plus an empty eligible buffer keeps the existing single
fixed fatal notice followed by silence.

The iRacing Data API and its OAuth flow remain backlog and are not part of this core graph cut.

## Definition of a complete graph

The prepared graph is complete only when:

1. every semantic situation producible by the runtime resolves to exactly one concrete graph node;
2. every prepared node defines allowed stages/modes, tier, priority, terminality, required and
   optional fact IDs, relation, material-change policy, localized intent and prohibited claims;
3. every core node has reviewed Czech and English generation anchors;
4. every node is reachable from a stage root or an explicit predecessor edge;
5. the runtime never ranks a new prepared situation through the generic `prepared_filler` node;
6. graph validation and coverage tests fail for an unknown runtime key, dead node, incomplete
   locale, invalid edge or unsupported fact/relation;
7. reset, disconnect and OBS stop remain non-speaking lifecycle invalidations rather than being
   misrepresented as commentary nodes.

## Closed core inventory

The target core manifest contains 53 prepared nodes plus reuse of the existing critical green
node. Phase 0 may rename a node for consistent snake case but may not add an unclassified catch-all
without recording its evidence and policy.

### Stream and venue opening (8)

- `stream_intro_venue`
- `stream_intro_circuit_character`
- `stream_intro_conditions`
- `stream_intro_surface_state`
- `stream_intro_field_overall`
- `stream_intro_field_class`
- `stream_intro_ai_field`
- `practice_quiet_track`

### Session intro and leaving the pits (9)

- `event_intro_practice`
- `event_intro_qualifying`
- `event_intro_race`
- `hero_prepares_to_drive`
- `engine_started`
- `rollout_started`
- `out_lap_preparation`
- `out_lap_field_context`
- `returned_to_car`

### Race grid and start (9 new nodes, existing green reused)

- `race_quali_recap_result`
- `race_grid_field`
- `race_grid_highest_rated`
- `rolling_start_setup`
- `formation_lap_preparation`
- `formation_lap_tension`
- `standing_start_setup`
- `start_lights_ready`
- `start_lights_set`
- reuse existing `session_flag_green`/green critical semantics for the green edge

### Results and chapter transitions (26)

- Practice: `practice_checkered_summary`, `practice_value_debrief`, `practice_lobby_break`
- Qualifying: `quali_result_pole`, `quali_result_podium`, `quali_result_top_third`,
  `quali_result_middle_third`, `quali_result_rear_third`, `quali_result_classified`,
  `quali_result_unclassified`, `quali_to_race_bridge`
- Race: `race_result_win`, `race_result_podium`, `race_result_gain_vs_quali`,
  `race_result_hold_vs_quali`, `race_result_loss_vs_quali`, `race_result_gain_vs_grid`,
  `race_result_hold_vs_grid`, `race_result_loss_vs_grid`, `race_result_top_third`,
  `race_result_middle_third`, `race_result_rear_third`, `race_result_classified`,
  `race_result_unclassified`
- Shared safe paths: `result_unconfirmed`, `stream_chapter_bridge`

### Operational notice (1)

- `prepared_filler_fatal_notice`

Generic runtime topics such as `session_setup`, `hero_position`, `start_setup` and `live_context`
are migration inputs, not target nodes. They must be replaced by specific contracts. Live-session
occurrences continue to use existing lap, battle, pit, weather, flag and incident nodes rather than
an unrestricted prepared `live_context` filler.

## Prepared graph contract

The persisted JSON uses schema revision 4 so older saved graphs and replays can be rejected or
migrated deterministically. This is an internal compatibility marker, not a separate product
rollout or a future implementation track.

Add an optional `prepared` object to `GraphNode` and bump the shipped graph to v4 while preserving
v1–v3 parsing:

```json
{
  "allowed_stages": ["SESSION_CONCLUSION"],
  "tier": 0,
  "terminal": true,
  "required_facts": ["finish_position", "qualifying_position"],
  "optional_facts": ["track"],
  "relation": "finish_better_than_qualifying",
  "intent": {
    "en": "Confirmed race finish improved on qualifying.",
    "cs": "Potvrzený výsledek závodu je lepší než kvalifikace."
  },
  "forbidden_claims": ["cause", "prediction", "blame"],
  "anchors": {
    "en": ["...", "..."],
    "cs": ["...", "..."]
  }
}
```

Validation uses closed enums for stages, relations and prohibited claim categories. Required and
optional facts may not overlap. Both supported locales are mandatory, anchor collections are
bounded and non-empty, terminality is boolean, and tier is bounded. A prepared contract is valid
only for `PREPARED_FILLER` or `PREPARED_FATAL`.

## Runtime migration

1. Build plans by selecting graph nodes and binding immutable propositions; do not construct node
   IDs from string interpolation.
2. Include a stable hash of the graph contract in `plan_id` so content-policy changes invalidate
   previously generated variants.
3. Read allowed stage, tier and terminality from the graph contract.
4. Pass localized intent, relation, prohibited claims and anchors to the LLM request.
5. Resolve and score the actual node in `rank_prepared_fillers()`; remove the generic-node
   substitution from the new path.
6. Keep the legacy generic node only for old replay compatibility during the compatibility window.
7. Treat a missing/mismatched graph contract as fail-soft `graph_contract_missing`; never raise
   into the race loop.

## Grounding and relation validation

Result relations must not be inferred only from two allowed numbers. The plan must include a
localized, deterministic relation proposition such as “gained two places, from P6 to P4”. Accepted
variants must contain the required relation realization and may not reverse its actors or direction.

The validator must explicitly cover:

- gain/hold/loss against qualifying and grid;
- Practice claims that must not invent setup improvement;
- provisional versus confirmed result wording;
- win/podium precedence over relative branches;
- unconfirmed result copy without a claimed position;
- absence of unsupported cause, prediction, blame, nationality and certainty.

## Graph topology

The core optional chain is:

```text
stream_start
  -> venue / circuit / conditions / surface / field
  -> event intro
  -> prepare / rollout / out lap OR grid / formation / lights
  -> existing critical green and live microstories
  -> confirmed result or bounded unconfirmed close
  -> chapter bridge
```

Missing facts shorten the chain and never delay another eligible node. Start-ready/set forbids long
filler. Critical/live candidates always outrank prepared and fatal candidates. Result and fatal
nodes are terminal for their editorial episode.

## Ordered implementation

### Phase 0 — contract and characterization

- Add a machine-readable expected manifest and old-to-new mapping.
- Add failing characterization tests proving the current generic-node behavior.
- Record current graph version, node count and full-suite baseline.

Exit: tests express every missing node and generic routing defect before production behavior changes.

### Phase 1 — prepared graph parser and validation

- Implement `PreparedNodeContract`, closed enums, parsing and validation.
- Keep graph v1–v3 compatibility tests green.
- Add content-hash support independent of runtime plan generation.

Exit: small fixture graphs prove every accepted and rejected contract shape.

### Phase 2 — complete node content and edges

- Author all 53 contracts in `sequence_graph.json`.
- Add localized intent and reviewed anchors.
- Add optional edges and terminal closures.
- Exempt prepared-only anchors from the legacy audible-copy density requirement while applying
  dedicated prepared-content validation.

Exit: no missing locale, dead node, invalid edge or duplicate semantic contract.

### Phase 3 — graph-driven plan builder and generator

- Replace hard-coded prepared semantic construction with graph lookup and fact binding.
- Send the complete graph contract to the LLM.
- Add relation propositions and validation.
- Preserve current/next reservation, regeneration, scope and cancellation behavior.

Exit: every emitted plan names a concrete graph node and no active/shadow plan uses
`prepared_filler`.

### Phase 4 — concrete graph scoring and lifecycle

- Score concrete prepared nodes and their real edges.
- Preserve live-event priority and single exposure at TTS `speaking`.
- Wire the explicit fatal node while retaining the one-notice-then-silence contract.

Exit: replay proves correct ordering, priority, terminality and lifecycle across every stage.

### Phase 5 — integration, documentation and live validation

- Run all unit/integration/replay tests, Ruff, mypy and diff checks.
- Update `COMMENTARY_ENGINE.md`, `API.md`, `CONFIG.md`, the scenario matrix and live-test procedure
  to name the prepared graph contract.
- Run the stream-PC matrix audibly in `active` on the private test broadcast.

Exit: all automated AC pass and manual evidence contains concrete node IDs with no generic routing.

## Acceptance criteria

- [x] AC1: all 53 core prepared nodes and the green reuse are present and validated.
- [x] AC2: every runtime-producible prepared situation maps one-to-one to the graph manifest.
- [x] AC3: no new prepared candidate is ranked through `prepared_filler`.
- [x] AC4: every prepared node has complete EN/CS intent, anchors and factual policy.
- [x] AC5: every node is reachable or explicitly declared as a stage root; all edges are valid.
- [x] AC6: relation branches cannot reverse gain/hold/loss or their reference.
- [x] AC7: 3–5 generated variants remain required before selection; graph anchors are never spoken
  as fallback.
- [x] AC8: current/next reservations and immutable scope invalidation remain intact.
- [x] AC9: critical/live events always outrank prepared and fatal candidates.
- [x] AC10: LLM exhaustion plus an empty current buffer selects the graph fatal node once, then
  filler remains silent until recovery.
- [x] AC11: session/run reset lets current TTS finish but discards waiters; disconnect stops
  generation; OBS stop hard-interrupts TTS.
- [x] AC12: shadow evidence names the concrete node and reconstructs every legacy comparison.
- [x] AC13: v1–v3 graph/replay compatibility remains green.
- [x] AC14: iRacing Data API absence cannot affect core graph readiness.
- [x] AC15: docs, API, active defaults and operational matrix match the delivered behavior.

## Test plan

### Unit

- prepared graph parser/validator positive and negative fixtures;
- exact manifest equality and duplicate semantic-key detection;
- EN/CS intent and anchor validation;
- graph reachability, edge identity and terminal closure;
- result bands for class sizes 1–12;
- gain/hold/loss against matching qualifying/grid scope;
- relation proposition and unsupported-claim rejection;
- graph-contract hash invalidation;
- missing-node fail-soft behavior.

### Integration and replay

- lobby intro with missing intermediate facts;
- Practice and Qualifying pit exit/out-lap closure;
- rolling and standing starts including ready/set/green preemption;
- all Practice/Qualifying/Race conclusion branches;
- current/next pre-generation across a correct transition;
- stale generation after session/run/stage reset;
- disconnect, OBS stop/start, fatal episode and recovery;
- shadow comparator using concrete node/semantic IDs;
- legacy rollback and old graph replay.

### Manual

Run every row in `docs/commentary_prepared_active_test.md` audibly in `active`. Retain VOD, tape,
status snapshots, config/build identity and factuality notes.

## Documentation impact

- `COMMENTARY_ENGINE.md`: graph-owned prepared contracts and lifecycle boundary.
- `API.md`: concrete prepared node IDs and graph-contract diagnostics in status/tape.
- `CONFIG.md`: no new keys; clarify that mode behavior is graph-driven.
- `docs/commentary_content_db_plan.md`: implementation status and link to this plan.
- `docs/scenario_coverage_matrix.md`: core-node coverage and remaining external backlog.
- `docs/commentary_prepared_active_test.md`: audible active-path and generic-node rejection checks.

## Config impact

No new dependency and no new config key. Existing prepared-filler limits remain unchanged. Both
graph runtime and prepared filler now default to `active`; `legacy` remains an explicit rollback.

## Work sequencing

The graph schema and shared semantic manifest are sequential. After that contract is frozen,
content authoring (`sequence_graph.json` plus content tests) and runtime binding
(`prepared_filler.py`, `director.py`, `consumer.py` plus runtime tests) may proceed independently.
Final integration, docs and audible private-stream validation are sequential.

No iRacing Data API/OAuth work, OBS/HUD work or static generated-text fallback belongs in this
implementation.

## Automated verification — 2026-09-04

- `pytest -q`: **1586 passed**;
- `mypy src`: **187 source files, no issues**;
- Ruff: all files changed by this cut pass;
- `git diff --check`: pass;
- repository-wide Ruff still reports only pre-existing whitespace/f-string findings in
  `scripts/bump_version.py`, outside this change.

Manual Windows/OBS/iRacing/Ollama evidence is not represented by these results. It will be
collected audibly in `active` on the private test broadcast.
