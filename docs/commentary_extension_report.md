# Commentary extension report

**Branch:** `commentary-extension-texts`

**Runtime baseline:** `origin/master`

**Text/voice baseline:** `origin/cursor/commentary-content-db-plan-8972` at `692da08`

**Patch:** [`commentary_extension_texts_patch.json`](commentary_extension_texts_patch.json)

**Proposals:** [`commentary_extension_proposals.json`](commentary_extension_proposals.json)

**Engineering handover:** [`commentary_extension_handover.md`](commentary_extension_handover.md)

## Scope and invariants

- The 26 existing node ids, families, event types, phases, priorities, cooldowns, slots, HR states, TTS limits, and 12 edges are unchanged from #127.
- `director.py`, `validator.py`, Event Engine wiring, config, and dependencies remain from `origin/master` and are not modified.
- Existing #127 viewer-facing EN+CS lines are preserved in their original order; the patch is append-only.
- New session/SoF/weather nodes remain under the explicit top-level `proposed_nodes` section of the proposal artifact. They are not active graph topology.
- No database dependency is introduced.

## Acceptance criteria

- [x] All 26 existing nodes have EN+CS coverage for every declared HR state.
- [x] Every active cell has at least 10 lines; standard cells have 12 and priority cells have 16.
- [x] #127 lines remain first and unchanged; additions are delivered as a machine-readable append patch.
- [x] Target-name battle/position nodes have 30–40% slot-light coverage.
- [x] Five new nodes are explicit `needs-engineering` proposals, not active topology.
- [x] Every new slot has an exact iRSDK/SessionInfo source and unimplemented-binding status.
- [x] The complete active and proposed content passes the current validator raw and with example bindings.
- [x] Counts, loop analysis, examples, engineering gaps, and deterministic self-check are documented.

## Test plan, docs, and config impact

- Unit/content: graph load, density, append parity, slot-light ratio, duplicates, voice scan, raw/bound validator checks, proposals, and 60-line seeded self-check.
- Regression: all existing `tests/test_commentary*.py`, then the full pytest suite.
- Static: JSON parser, Ruff, Black check, and `git diff --check`.
- Docs updated: `COMMENTARY_ENGINE.md`, `CONFIG.md`, this report, proposals, and engineering handover.
- Config: no keys, defaults, or example INI values change; commentary remains disabled by default.
- API: no change.

## Counts before and after

| Metric | #127 before | After | Change |
|---|---:|---:|---:|
| Existing nodes | 26 | 26 | 0 |
| Existing edges | 12 | 12 | 0 |
| EN+CS emotion cells | 188 | 188 | 0 |
| Spoken variants | 752 | 2,760 | +2,008 |
| EN variants | 376 | 1,380 | +1,004 |
| CS variants | 376 | 1,380 | +1,004 |
| Minimum variants per cell | 4 | 12 | +8 |
| Priority-cell variants | 4 | 16 | +12 |
| Empty or under-10 cells | 188 | 0 | -188 |

Priority density applies to lap, battle, position, pit, in-car, final-lap, and finish beats. Other cells receive 12 variants.

| Node | Cells | Before | After | Per cell |
|---|---:|---:|---:|---:|
| `lap_complete` | 10 | 40 | 160 | 16 |
| `personal_best` | 10 | 40 | 160 | 16 |
| `gain_found` | 6 | 24 | 72 | 12 |
| `time_lost` | 6 | 24 | 72 | 12 |
| `target_locked` | 6 | 24 | 72 | 12 |
| `projected_lap` | 6 | 24 | 72 | 12 |
| `hot_lap` | 8 | 32 | 96 | 12 |
| `position_attack` | 6 | 24 | 72 | 12 |
| `clean_streak` | 6 | 24 | 72 | 12 |
| `hunting` | 8 | 32 | 128 | 16 |
| `hunted` | 8 | 32 | 128 | 16 |
| `side_by_side` | 6 | 24 | 96 | 16 |
| `overtake` | 8 | 32 | 128 | 16 |
| `position_gained` | 8 | 32 | 128 | 16 |
| `position_lost` | 8 | 32 | 128 | 16 |
| `rival_threat` | 6 | 24 | 96 | 16 |
| `battle_won` | 8 | 32 | 128 | 16 |
| `incident` | 8 | 32 | 96 | 12 |
| `invalid_lap` | 6 | 24 | 72 | 12 |
| `final_lap` | 8 | 32 | 128 | 16 |
| `finish` | 10 | 40 | 160 | 16 |
| `pit_entry` | 6 | 24 | 96 | 16 |
| `back_on_track` | 6 | 24 | 96 | 16 |
| `in_car` | 10 | 40 | 160 | 16 |
| `pit_outcome` | 6 | 24 | 96 | 16 |
| `hr_pressure` | 4 | 16 | 48 | 12 |

## Slot-light coverage

The measurable fallback set is the five battle/position nodes that declare `{target_name}`: `hunting`, `hunted`, `side_by_side`, `overtake`, and `rival_threat`.

- 216 of 576 variants omit `{target_name}`: **37.5%**.
- Every locale/emotion cell in those nodes has exactly 6 of 16 name-free variants.
- 185 of 576 variants omit both `{target_name}` and `{gap}`: **32.1%** of the full target-capable pool.
- The gap metric is used only on nodes that actually declare it; `side_by_side` and `overtake` do not invent a gap slot.

This keeps the ready-line pool useful when `DriverInfo` has no display name and, where appropriate, when the live gap is missing.

## How this breaks the audible eight-line loop

1. The ready bucket grows from 4 to 12 or 16 lines before any slot filtering.
2. Both locales now have equal density, so CS does not collapse into a small EN fallback pool.
3. Each cell mixes factual updates, pace/pressure, opponent-aware copy, viewer asides, sequence bridges, HR tone, and slot-light fallbacks.
4. Edge-adjacent nodes include wording that advances the story instead of restaging the previous beat.
5. Name-free battle lines prevent missing `DriverInfo` from reducing a cell to the same few fully bound sentences.

This is a probability reduction, not a hard no-repeat guarantee. The current master still uses `rng.choice` without history. A bounded anti-repeat window is listed in the handover as a separate engineering change.

## Ten EN+CS examples

| Beat | EN | CS |
|---|---|---|
| Hunting | P{position} is becoming a launch point rather than a destination. | {position}. místo se mění ve výchozí bod místo cíle. |
| Overtake | That whole chase now has a result, and the pressure keeps rising. | Celé stíhání teď dostává výsledek, tlak dál roste. |
| Position lost | The classification turns against him by one place. | Klasifikace se obrací o jedno místo proti němu, obraz závodu je jasný. |
| Lap complete | Lap {lap} adds another piece to this stint, all under control. | Kolo {lap} přidává další část téhle jízdy, všechno má pod kontrolou. |
| Personal best | His work through the stint pays off with a new best! | Práce během stintu se mění v osobní maximum, závod kolem něj ožívá! |
| Pit entry | Viewers now shift attention from track to pit work. | Pozornost diváků se přesouvá z trati k mechanikům, přesně podle plánu. |
| Back on track | His attention moves from the limiter to the road ahead. | Pozornost přesouvá z omezovače na trať před sebou. |
| In car | Preparation gives way to the first live inputs. | Přípravu střídají první živé vstupy, soustředění zůstává pevné. |
| Final lap | The race narrows to one final sequence, and this is getting intense! | Závod se zužuje na jedinou závěrečnou sekvenci, tohle začíná být ostré! |
| Finish | P{position} is the lasting number from this race. | Trvalým číslem z tohohle závodu je {position}. místo, příběh pokračuje. |

## Needs engineering

1. Implement the slot and trigger work in [`commentary_extension_handover.md`](commentary_extension_handover.md).
2. Decide and implement a bounded anti-repeat policy if a hard guarantee is required.
3. Approve the SoF formula and triggers before emitting `SOF_BRIEF`.
4. Distinguish forecast weather from current telemetry and define refresh/anti-spam policy.
5. Add the five proposed event ids to the catalog only together with emitters, metrics, and tests.
6. Bind the new slots in `CommentaryDirector.slot_bindings()` only after their envelope metrics exist.

## Verification

The content test suite validates the complete graph, not only a sample:

- JSON parse for graph, patch, and proposal artifacts.
- Actual `validate_utterance()` for all 2,760 active lines.
- Actual `validate_utterance()` for all 500 proposed lines using temporary nodes and proposed slots.
- Exact append-patch parity against the tail of every active cell.
- No unknown slots, missing terminal punctuation, emoji, URLs, stacked punctuation, ALL-CAPS shouting, four-digit runs, or max length/duration violations. The 5.5-second estimator makes 71 characters the effective cap even though `max_chars` is 90.
- No exact normalized duplicate within any active cell; near-duplicate audit threshold is 0.88 similarity.
- Deterministic self-check sample: 60 active lines selected with seed `20260830`, exceeding the requested minimum of 30.
- Viewer voice scan for direct second-person driver address in EN and CS.

Final local results:

- Commentary suite: **63 passed**.
- Full repository suite: **667 passed**.
- Ruff: passed on every changed Python file.
- Black check: passed on every changed Python file.
- JSON parsing and `git diff --check`: passed.
- Patch replay: all 188 append operations applied to blob `1e91b06ec65cce386d7a50bdd9ec6259c8020da5` reproduce `sequence_graph.json` exactly; 2,008 appended lines.
