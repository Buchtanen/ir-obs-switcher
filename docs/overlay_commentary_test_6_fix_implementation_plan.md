# Overlay and Commentary Test 6 — Fix Implementation Plan

Status: proposed

Base branch: `refactor/200-n12-async-consumers`

Evidence: [Overlay and Commentary Test 6 analysis](overlay_commentary_test_6_analysis.md)

## 1. Target outcome

The implementation must turn commentary from skeleton paraphrasing into a directed mini-story system while preserving factual safety and live timing:

1. The graph/director selects the story, fact density, required propositions and a compatible style card.
2. Qwen normally performs one short language-realization request.
3. Validation checks the selected facts and their relations, not unrelated telemetry values.
4. A naturally resolved event completes the mini-story instead of invalidating it.
5. Committed speech owns a narrative lease and normally finishes.
6. A hero order change is the normal hard-preemption condition.
7. Commentary and dynamic overlays consume one shared mini-story lifecycle.
8. Relation state, run identity, chapters and overlay snapshots remain correct through exits, resets and short OBS interruptions.

Model-weight fine-tuning is outside this iteration. Prompt and contract tuning already demonstrated enough potential with local `qwen3:4b`.

## 2. Fixed design decisions

- One Qwen request in the normal path; at most one stricter retry after a hard semantic failure.
- Style warnings never cause a retry.
- No per-fact model calls: they serialized locally, increased latency and encouraged invented trends.
- No model-authored JSON self-check: it was slower and unreliable.
- Use family-specific style cards with one short example. The tested two-front cards yielded 9/9 correct outputs in 0.78–0.99 seconds.
- Temperature controls phrasing diversity, not factual validity.
- Preserve a complete deterministic canonical realization as the final fallback.
- Shared `MiniStory` state belongs in `race/`; `commentary/` and `overlay/` remain peer consumers.
- Ordinary event `EXIT` means `RESOLVED`; `INVALIDATED` is reserved for bad identity/data or a run reset.
- Ordinary `EXIT`, a lower-priority event or an incident does not cancel committed speech by default.
- Hero order change and technical teardown/reset can interrupt.

## 3. Dependency order

```text
P0  Replay/evaluation baseline
 │
 ├── A  Commentary microplans, style cards, prompt and validator ─┐
 ├── C  Relation identity and authoritative overlay state ────────┤
 ├── D  Run epoch, green-relative phase and source fact validity ─┤
 └── E  Monotonic broadcast/chapter clock                         │
                                                                   ▼
                 B  Editorial MiniStory lifecycle and preemption
                                                                   │
                                                                   ▼
                 F  Overlay presentation and production copy
                                                                   │
                                                                   ▼
                 G  Integrated tape replay and live acceptance
```

After P0, A/C/D/E can run in parallel in isolated worktrees. B follows A/C/D because it consumes their contracts. F is sequential because it includes Overlay HUD JavaScript; HUD files must not be split across parallel tasks. G is the final gate.

The plan remains on the current branch. Work branches and issues are created only after approval.

| ID | Delivery | Proposed branch | Issue |
|---|---|---|---|
| P0 | sequential prerequisite | `test/commentary-replay-baseline` | create after approval |
| A | parallel wave 1 | `feat/commentary-style-card-microplans` | create after approval |
| C | parallel wave 1 | `fix/live-relation-story-state` | create after approval |
| D | parallel wave 1 | `fix/race-run-epoch-phase` | create after approval |
| E | parallel wave 1 | `fix/broadcast-chapter-clock` | create after approval |
| B | sequential integration | `feat/editorial-ministory-lifecycle` | create after approval |
| F | sequential HUD work | `fix/overlay-live-copy` | create after approval |
| G | sequential final gate | integration branch | parent issue checklist |

## 4. P0 — Replay and evaluation baseline

### Implementation

- Build a curated corpus from recordings covering hunting, battle, two-front, position gained/lost, leader change, aftermath, finish, naturally resolved battle, invalid zero facts and two starts under one iRacing session.
- Store inputs, required propositions, forbidden actors/numbers and expected story state. Do not require one exact golden sentence.
- Add an evaluator for coverage, invented actors/numbers, relation direction, prompt size, attempts, fallback reason and latency.
- Keep live Qwen execution optional and local. CI uses deterministic fixtures/fakes and never requires Ollama.

Likely files: `tests/fixtures/commentary/`, `tests/test_commentary_replay_eval.py`, `scripts/commentary_llm_eval.py`.

### Acceptance criteria and tests

- Reproduce the 106-operation baseline from repository recordings.
- Curate at least 30 cases across the event families above.
- Separate hard semantic failure from style warning in reports.
- Unit-test evaluator rules and aggregation.
- If localhost Qwen is absent, the optional test skips explicitly without failing the suite.

Docs: document the local evaluation command. Config: none.

## 5. A — Commentary microplans and Qwen realization

### A1. Versioned microplan

Add immutable `commentary-microplan/1` containing:

- event family, story state and relation direction;
- actor roles;
- ordered required and optional propositions;
- density class: `single`, `multi_role` or `resolved`;
- style-card ID and safe optional colour;
- canonical realization;
- source correlation, run epoch and revision fields used later by B.

`CommentaryComposer` remains the deterministic factual source but stops automatically adding every available position, phase, lap and telemetry value.

Fact-density rules:

- `single`: one required proposition plus at most one metric;
- `multi_role`: at most two required relations plus one optional metric;
- `resolved`: two chronological required beats, with position/metrics optional.

### A2. Style-card catalog

Add typed `style_cards.py` and `data/style_cards.json`. Each card declares compatible families, relations and story states, one short example, permitted colour/cadence and proposition capacity. Extend graph nodes with compatible card IDs; the graph/director selects the card before prompt construction.

Initial cards: `fact_first`, `tension_first`, `road_and_mirrors`, plus family-specific resolved/result variants.

### A3. Compact prompt and validator

Create `commentary-facts/3` with only the chosen example, required/optional propositions, actor roles, relation direction and compact prohibitions. Remove the global `allowed_numbers` dump and self-assessment.

Validation becomes:

- `HARD`: invented actor/number, changed direction, missing required proposition, identity/run mismatch;
- `SOFT`: rhythm, repetition, style or omitted optional fact;
- `PASS`.

Derive allowed values from selected propositions. Parse `P<n>` and `S<n>` before generic name detection, apply fact-specific numeric tolerance and use family-specific relation checks. One hard failure may switch to a stricter fact-first card; a second hard failure uses the canonical realization. Never repeat an identical prompt.

Record microplan/card IDs, selected propositions, severity/code, attempts, token counts and fallback reason in tape metrics.

Likely files:

- `src/irswitch/commentary/composer.py`
- `src/irswitch/commentary/polish.py`
- `src/irswitch/commentary/graph.py`
- `src/irswitch/commentary/data/sequence_graph.json`
- new style-card files
- `src/irswitch/overlay/settings.py`, `src/irswitch/config.py`, `src/irswitch/overlay/schema.py`

### Acceptance criteria

- Median replay prompt ≤300 tokens.
- Normal path is one call; no operation exceeds two calls.
- First-pass acceptance ≥85%; canonical fallback <15% on the curated corpus.
- Zero accepted material invented actor/number or reversed relation in the corpus.
- Three cards produce materially distinct, correct versions of the same two-front facts.
- Resolved microplans use result framing without inventing an outcome.
- Model outage/timeout returns the canonical realization without destabilizing the loop.

### Verification and contracts

- Extend composer, graph and polish tests for density, card compatibility, positions/session tokens, relation direction, numeric tolerance, severity, retry and outage.
- Add deterministic HTTP-fake tests and run the optional local Qwen corpus.
- Change default `llm_max_attempts` from 5 to 2 and clamp effective values to 1–2.
- Update `CONFIG.md` and `config/config.example.ini`; document temperature semantics.
- No new dependency.

## 6. C — Live relation and authoritative overlay state

### Implementation

1. Require battle gaps to be finite and non-negative; front/rear class position must agree with claimed direction.
2. Persist the exact correlation key, target IDs and epoch accepted at `ENTER`; reuse them at `EXIT`.
3. Make removal idempotent and measure unmatched exits.
4. Make `OverlayBus.set_active_stories_v4()` participate in dirty/change detection.
5. Always send an authoritative snapshot to a new client, including an empty list.
6. Broadcast an empty snapshot when the final story exits.

Likely files: `events/battle.py`, `events/manager_v2.py`, `overlay/bus.py`, `overlay/consumer.py`, associated models.

### Acceptance criteria and tests

- Negative, NaN or infinite gaps cannot create relations.
- `EXIT` removes exactly its entered relation after target updates; duplicate exit is harmless.
- The final exit and a new empty client both receive an explicit empty snapshot.
- Tape replay ends without stale P14/battle/rival state.
- Extend battle intensity, event manager and overlay snapshot tests and add replay final-state assertion.

Docs: update overlay protocol if the snapshot contract is external. Config/dependencies: none.

## 7. D — Run epoch, race phase and source validity

### Implementation

- Detect a guarded material `SessionTime` rewind under the same session key and increment `run_epoch`; ignore ordinary jitter.
- Propagate epoch through story context, situation payloads, correlations, overlays, microplans and tape records.
- On epoch change reset green origin, uncommitted candidates, active relations and run-scoped observer/narrative state exactly once.
- Compute race phase from a stable green origin, not formation/aborted-start raw time. Prefer completed racing laps for lap-limited races.
- Suppress facts that are not domain-valid: non-positive SoF, non-finite/meaningless delta/gap, unparsable position/session tokens and unconfirmed final classification.

Likely files: `race/pipeline.py`, `race/runtime.py`, `race/observer.py`, `race/story.py`, `race/narrative.py`, typed situation/session models.

### Acceptance criteria and tests

- Two starts under one session key have different epochs; jitter creates none.
- Rewind resets run state once and is visible in tape/correlations.
- Green after formation is early, not middle.
- SoF `0` and invalid delta/gap are absent, not narrated as zero.
- Extend race pipeline, live-fix, session narrative and story-history tests; include the recorded two-start replay.

Docs: document observable epoch fields. Config/dependencies: none unless project convention requires a configurable rewind guard.

## 8. E — Monotonic broadcast and chapter clock

### Implementation

- Prefer OBS `outputDuration` as authoritative while available.
- Maintain one monotonic cumulative broadcast offset through short output stop/start transitions.
- Make metrics and chapter tracking share the same clock and debounce semantics.
- Reset clock and chapter history together only for a confirmed new broadcast.
- Preserve YouTube chapter output formatting.

Likely files: `logic/stream_chapters.py`, `server/metrics.py`, `obs/client.py` or typed status mapping, stream-status glue.

### Acceptance criteria and tests

- Short interruption neither restarts nor moves chapter time backwards.
- A real new broadcast resets clock and history together.
- Chapter offsets strictly increase and match video within OBS polling tolerance.
- Extend stream chapter, YouTube chapter and stream status tests with deterministic stop/start timelines.

Docs: document interruption versus new-broadcast semantics. Config/dependencies: none.

## 9. B — Editorial `MiniStory` lifecycle

### B1. Shared state machine

Add a typed aggregate in `race/`:

```text
CANDIDATE -> BUILDING -> READY -> COMMITTED/SPEAKING -> COMPLETED
                 |         |
                 +-------> INVALIDATED
                 +-------> RESOLVED (updates the ending; it is not a drop)

COMMITTED/SPEAKING -- hero order change --> INTERRUPTED
```

Identity includes run epoch, source correlation/targets, hero/order revision, story family and monotonically increasing story revision. A fact ledger accepts live updates. Normal `EXIT` writes an outcome as `RESOLVED`; reset, identity mismatch or unusable data invalidates an uncommitted story.

### B2. Commit gate after polish

Because polishing runs inside the TTS worker, freshness must be checked after Qwen returns and before speech starts. Provide a narrow thread-safe commit authority owned by the shared story registry:

- `UNCHANGED`: commit generated text;
- `RESOLVED`: use a new result-oriented realization within the two-call budget, otherwise canonical result text;
- `INVALIDATED` or epoch mismatch: do not speak;
- changed hero-order revision: preempt and prioritize the new position story.

Successful commit creates the narrative lease; a later ordinary `EXIT` does not cancel it.

### B3. Coalescing and preemption

- Coalesce uncommitted candidates by semantic identity and keep only their latest revision.
- Re-rank after current speech and reject no-longer-current candidates.
- Prefer a resolved ending over an obsolete present-tense draft.
- Hero position gained/lost safely cancels active TTS, restores ducking in `finally`, marks the old story interrupted, invalidates candidates from the old order and prioritizes the new position story.
- Incidents and ordinary exits do not hard-interrupt by default.

Likely files: new `race/ministory.py`, `race/observer.py`, `race/pipeline.py`, `commentary/director.py`, `commentary/scheduler.py`, `commentary/tts.py`, shared typed consumers.

### Acceptance criteria

- Resolution during Qwen work is spoken as an outcome, not dropped or presented as still live.
- Resolution after speech begins is allowed to finish.
- Reset/epoch/identity invalidation blocks uncommitted speech.
- Hero order change stops active speech and promotes the position story.
- Ordinary incident/exit does not interrupt committed speech.
- Queue holds only the latest revision and never starts an invalidated candidate.
- Cancellation always restores ducking and leaves the worker reusable.

### Verification and contracts

- State-transition tests, scheduler/director revision/coalescing tests and fake TTS cancellation tests.
- Delayed fake-polish race tests for event resolution and active-speech hero position change.
- Keep scheduler/director/TTS regression suites green.
- Document lifecycle and migration of the existing hard-interrupt setting; retain backward-compatible parsing during a compatibility window.
- No new dependency.

## 10. F — Overlay lifecycle and production copy

Status: implemented on the integration branch; automated acceptance complete, live OBS visual acceptance remains in G. See [MiniStory overlay bridge implementation](implementation_ministory_overlay_bridge.md).

### Implementation

- Map the shared story to presentation states: building/live, committed/speaking, resolved/result, completed/removed and interrupted/replaced.
- Keep a committed card through ordinary source `EXIT` until speech completes or a short result hold ends.
- Remove immediately on technical invalidation, run reset or hero-order preemption.
- Remove fixture/default copy such as `stack centre`; use real data or omit it.
- Keep `display-v4.js`, `hud.html`, `hud.css` and localization edits in this one sequential workstream.

### Acceptance criteria and tests

- Card and speech share story ID/revision.
- Ordinary exit transitions to result while narration finishes; preemption replaces card and speech coherently.
- Reset/invalidation/empty snapshot leaves no stale card.
- Fixture copy is absent from payload and rendering.
- Extend overlay consumer/asset tests and visually inspect recorded live→resolved→completed and live→interrupted timelines.

Docs: update visible overlay state/payload contract. Config/dependencies: none.

## 11. G — Integrated acceptance

### Automated replay gate

Run all focused suites plus the prescribed full suite. Full recordings must show:

- no negative-gap activation;
- no unmatched active story at end;
- no zero/invalid narrated fact;
- monotonic chapters and distinct epochs;
- each spoken/presented story references one valid revision;
- no polishing path exceeds two calls.

### Local Qwen gate

Run the curated corpus against localhost `qwen3:4b`, record first-pass/fallback/latency/tokens/semantic failures and repeat high-risk two-front, resolved, position and finish cases. Any accepted material hallucination or reversed relation blocks release.

| Metric | Baseline | Target |
|---|---:|---:|
| Median prompt tokens | 861 | ≤300 |
| Normal / maximum calls | up to 5 | 1 / 2 |
| First-pass acceptance | not dominant | ≥85% |
| Canonical fallback | 61.3% | <15% |
| Normal median latency | 1.43 s | ≤1.5 s |
| Accepted material hallucinations | present/unknown | 0 in corpus |

### Live/VOD gate

Run one controlled stream with tape enabled. Verify current-story timing, resolved completion, hero-order interruption, card/speech agreement, absence of stale/fixture content, unchanged game-owned inner dashboards and chapter/video alignment. Attach tape metrics and VOD review to the parent issue.

## 12. Merge, rollback and skipped work

Merge sequence:

1. Approve plan; create issue/worktree per independent stream.
2. Merge P0.
3. Rebase and implement A/C/D/E independently; merge only with tests and docs/config complete.
4. Create B from the updated integration branch.
5. Implement F sequentially after B/C.
6. Run G and record after-metrics before promoting config defaults.

Rollback/compatibility:

- Canonical realization always remains available if Qwen is disabled or fails acceptance.
- Tape readers tolerate missing new fields; overlay fields are added before old ones are removed.
- Old config keys remain parseable for one compatibility window with an explicit migration warning.
- If Qwen still misses the factual target, retain microplans/style cards and route realization to the canonical renderer while evaluating another constrained approach.

Explicitly skipped:

- Qwen weight fine-tuning/LoRA;
- per-fact model calls;
- model JSON self-validation;
- blind same-prompt retry;
- unrelated visual redesign or game-owned dashboard changes;
- tape-recorder fix—the recorder worked and files were initially absent only from the repository.
