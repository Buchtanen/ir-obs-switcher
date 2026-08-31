# N11 — Content fill: new nodes EN+CS

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §4  
**Depends on:** N2 schema + the event types from N3, N5, N7, N8 (fill in waves as nodes land)  
**Branch hint:** `feat/commentary-narrative-texts`  
**Rule:** texts only in `sequence_graph.json` (+ assignment tests). No engine behavior.

## Context

New watches are silent without lines. Voice: viewer-facing third person, CS+EN, validator, 4+ lines per emotion where the node allows. Stream start is **longer**; incidents in race stay short; practice off-track is **wordier**.

## Owns / must not touch

- **Owns:** `sequence_graph.json` variants, assignment briefs, density tests  
- **Must not:** Python policy, new slots without the producing task  

## Waves (can be separate PRs)

| Wave | Nodes | Notes |
| --- | --- | --- |
| A | `stream_start`, mode-specific `in_car_*` | Long TTS caps |
| B | incident branches + recovered | Practice off-track longer |
| C | `flag_*` | All sessions; mode filter |
| D | `grid_wait`, `rolling_start`, `pace_hunt`, `leader_pace` | Recap slots |

## Acceptance criteria

- [ ] Each new node: EN+CS, emotions the node allows, ≥1 slot-free line when slots can be missing  
- [ ] `validate_utterance` passes (long cap only on stream_start)  
- [ ] No second-person driver radio  
- [ ] Checkered flag copy ≠ finish copy  
- [ ] Density test updated for node/line counts  

## Test plan

- [ ] Existing graph validator + director bind tests for sample envelopes per branch  
- [ ] Manual listen later on stream PC (not merge-blocking)  

## Docs impact

- [ ] `docs/commentary_content_db_plan.md` wave checkbox  
- [ ] Assignment markdown if we still generate briefs  

## Config impact

None.
