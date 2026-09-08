# In-flight documentation — `codex/commentary-story-flow-spec`

**Status:** v2 narrative runtime Wave A–B (#235–#245) closed on this branch; **not shipped on `master`**. Next implementation package is [#246](https://github.com/Buchtanen/ir-obs-switcher/issues/246) (unclaimed; blocked until docs-keeper close-gates for #239–#244 are accepted).

## Where to look on this branch

| Need | Authority on this branch | Not shipped here |
| --- | --- | --- |
| Issue index, waves, dependencies | [docs/v2.0.0/README.md](../../v2.0.0/README.md) | `domeny/commentary.md` as master truth |
| Resume identity, closing SHAs, scope boundaries | [docs/v2.0.0/implementation-handover.md](../../v2.0.0/implementation-handover.md) | Public CONFIG/API/README product contracts (unchanged for #239–#244) |
| DTO/tape/schema freeze | [docs/v2.0.0/schema-contracts.md](../../v2.0.0/schema-contracts.md), [machine/](../../v2.0.0/machine/README.md) | Rewriting `machine/` hashes |
| Master domain pages (`domeny/*.md`, `architektura.md`, `mapa-souboru.md`, `stav.md`) | See `master` — **absent on this branch by design** | Copying master pages as if v2 were shipped |

## Implementation lookup (#239–#244, branch-only)

| Issue | Module placement | Key files | Tests |
| --- | --- | --- | --- |
| #239 NarrativeTape schema | contracts + commentary queue framing | `src/irswitch/contracts/schemas/v2/dto-contracts.schema.json`, `commentary/tape_queue.py` | `tests/test_narrative_tape_schema.py` |
| #240 Tape writer | commentary | `commentary/tape_writer.py`, `commentary/tape_queue.py` | `tests/test_narrative_tape_queue.py`, `tests/test_narrative_tape_writer.py` |
| #241 CapturePlan | commentary | `commentary/capture_plan.py`, `capture_safety.py`, `tape_safety.py` | `tests/test_narrative_capture_plan.py`, `tests/test_narrative_capture_safety.py` |
| #242 Replay / labels | commentary | `commentary/tape_replay.py` | `tests/test_narrative_tape_replay.py` |
| #243 StreamTimeline | logic | `logic/stream_timeline.py`, `contracts/session.py` (SessionPlan) | `tests/test_stream_timeline.py` |
| #244 SessionOccurrence | logic + contracts + events | `contracts/session.py` (SessionOccurrence), `logic/stream_timeline.py`, `events/timeline_facts.py` | `tests/test_session_occurrence.py`, `tests/test_timeline_facts.py` |

`NarrativeRuntime`, live `DetectorBank` wiring, and V4 overlay tape remain out of scope until #284 and later issues.

## Index drift note

[docs/dokumentace/README.md](../README.md) mirrors the master lookup table. Rows that link to `domeny/*.md`, `architektura.md`, `stav.md`, or `mapa-souboru.md` **404 on this branch**. For v2 narrative modules, use this page and `docs/v2.0.0/` instead of grepping `src/` or inventing shipped domain pages.
