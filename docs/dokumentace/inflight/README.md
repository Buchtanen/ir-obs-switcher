# In-flight documentation — `codex/commentary-story-flow-spec`

**Status:** v2 narrative runtime Wave A–B (#235–#246) closed on this branch; Wave C [#247](https://github.com/Buchtanen/ir-obs-switcher/issues/247) FeatureEngine is claimed and implemented here; **not shipped on `master`**. Next after #247 close is [#248](https://github.com/Buchtanen/ir-obs-switcher/issues/248) / [#249](https://github.com/Buchtanen/ir-obs-switcher/issues/249).

## Where to look on this branch

| Need | Authority on this branch | Not shipped here |
| --- | --- | --- |
| Issue index, waves, dependencies | [docs/v2.0.0/README.md](../../v2.0.0/README.md) | `domeny/commentary.md` as master truth |
| Resume identity, closing SHAs, scope boundaries | [docs/v2.0.0/implementation-handover.md](../../v2.0.0/implementation-handover.md) | Public CONFIG/API/README product contracts (unchanged for #239–#247) |
| DTO/tape/schema freeze | [docs/v2.0.0/schema-contracts.md](../../v2.0.0/schema-contracts.md), [machine/](../../v2.0.0/machine/README.md) | Rewriting `machine/` hashes |
| Master domain pages (`domeny/*.md`, `architektura.md`, `mapa-souboru.md`, `stav.md`) | See `master` — **absent on this branch by design** | Copying master pages as if v2 were shipped |

## Implementation lookup (#239–#247, branch-only)

| Issue | Module placement | Key files | Tests |
| --- | --- | --- | --- |
| #239 NarrativeTape schema | contracts / DTO freeze (no writer) | `src/irswitch/contracts/schemas/v2/dto-contracts.schema.json`, `docs/v2.0.0/schema-contracts.md` | `tests/test_narrative_tape_schema.py` |
| #240 Tape writer | commentary | `commentary/tape_writer.py`, `commentary/tape_queue.py` | `tests/test_narrative_tape_queue.py`, `tests/test_narrative_tape_writer.py` |
| #241 CapturePlan | commentary | `commentary/capture_plan.py`, `capture_safety.py`, `tape_safety.py` | `tests/test_narrative_capture_plan.py`, `tests/test_narrative_capture_safety.py` |
| #242 Replay / labels | commentary | `commentary/tape_replay.py` | `tests/test_narrative_tape_replay.py` |
| #243 StreamTimeline | logic | `logic/stream_timeline.py`, `contracts/session.py` (SessionPlan) | `tests/test_stream_timeline.py` |
| #244 SessionOccurrence | logic + contracts + events | `contracts/session.py` (SessionOccurrence), `logic/stream_timeline.py`, `events/timeline_facts.py` | `tests/test_session_occurrence.py`, `tests/test_timeline_facts.py` |
| #245 AtomicFact ledger | events | `events/fact_ledger.py`, `events/timeline_facts.py` | `tests/test_fact_ledger.py`, `tests/test_timeline_facts.py` |
| #246 inheritance / summaries | events FactLedger | `events/fact_ledger.py` (`inherited_facts`, `historical`, `occurrence_summary`, `compactedSummaryRefs`) | `tests/test_fact_inheritance.py` |
| #247 FeatureEngine | contracts + events | `contracts/feature.py` (`FeatureDefinition`, `FeatureFrame`, 21-ID registry), `events/feature_engine.py` (bounded windows, `estimated_v1` only) | `tests/test_feature_engine.py` |

`NarrativeRuntime`, live `DetectorBank` wiring, and V4 overlay tape remain out of scope until #284 and later issues.

## Index drift note

[docs/dokumentace/README.md](../README.md) mirrors the master lookup table. Rows that link to `domeny/*.md`, `architektura.md`, `stav.md`, or `mapa-souboru.md` **404 on this branch**. For v2 narrative modules, use this page and `docs/v2.0.0/` instead of grepping `src/` or inventing shipped domain pages.
