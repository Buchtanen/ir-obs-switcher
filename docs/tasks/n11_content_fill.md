# N11 — Content fill (wave A only on landing)

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §4  
**Depends on:** N2 schema + N8 event type  
**v1:** wave A + sparse B/C/D. P5 `attack_range` / `pit_stopped` already filled — do not redo.

## Context

P2–P4 derived types often speak via **templates** (`format_filler_text`). Graph nodes for those are optional polish, not a landing gate.

Stream start needs a **long** cap. Flags/incidents in v1 use `hr_states: ["unknown"]` if nodes exist at all.

## Owns

- `sequence_graph.json` variants for wave A
- density tests (node count will change)
- Must not: Python policy; new slots without producer

## Wave A (landing)

- [x] `stream_start` EN+CS, slot-free line present, `tts.max_seconds` ≥ 15
- [x] TTS timeout **exempts `STREAM_START` only** from `commentary.max_utterance_s` (master default **14**; node 16 s). Do not raise the global cap further
- [x] Spoken stream_start holds `director._busy_until` for that duration (this **is** the opener mutex vs in-car)
- [x] `in_car` mode nodes **or** mode filter on existing node — do not delete generic until migrated
- [x] `validate_utterance` passes
- [x] viewer-facing third person

## Wave B / C / D (shipped after N3/N5/N7)

- [x] B: `incident_off_track` / `incident_unknown` (`hr_states: unknown` only). Generic `incident` stays when classify is off
- [x] C: `session_flag_yellow` / `_green` / `_checkered` — **1 line × 2 locales**, not 5 emotions
- [x] D: `quali_recap` + `parade_pad` graph copy (formatter remains fallback)

## Later (not this epic)

- Optional: graph nodes replacing remaining P2–P4 templates
- Spoken `contact_car` / `contact_object` / `lost_control` — still refused

## Docs impact

- [x] commentary_content_db_plan wave checkbox when A lands

## Config impact

None.
