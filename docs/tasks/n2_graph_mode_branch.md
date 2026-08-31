# N2 — Sequence graph mode + branch select

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md)  
**Depends on:** P1 merged before **director** wiring (`director.py` is owned by [#169](https://github.com/Buchtanen/ir-obs-switcher/pull/169))  
**Can start now:** `graph.py` + validator + fixtures only  
**Blocks:** N11 (texts), N8/N5/N3 node ids  
**Branch hint:** `feat/commentary-graph-select`

## Context

We need more **layers** (session mode, incident/flag branch, longer caps) without `emotion × mode × branch × locale` cells. Match is a fallback ladder; generic `incident` stays as last resort.

## Owns / must not touch

- **Owns (wave A, parallel):** `commentary/graph.py`, graph validator, `sequence_graph.json` schema fields (empty new nodes OK), tests  
- **Owns (wave B, after P1):** `commentary/director.py` `nodes_for` + slot `branch` / mode  
- **Must not:** EventEngine emitters, overlay renderer, inventing event types that N3/N5 have not named  

## Acceptance criteria

- [ ] Graph document supports optional `modes: ["PRACTICE","QUALIFYING","RACE"]` and optional `branch: "off_track"` on a node  
- [ ] `nodes_for(event, phase, mode, branch)` prefers exact match then branch, then mode, then unfiltered (today’s behavior)  
- [ ] Two nodes may share `event_types`; highest `speak_priority` still wins inside a match tier  
- [ ] Per-node `tts.max_seconds` / `max_chars` unchanged (stream_start will use a long cap in N8/N11)  
- [ ] `validate_graph_document` rejects unknown mode/branch tokens from a small allow-list (extendable)  
- [ ] Existing graphs without the new fields load as today  
- [ ] GRAPH_VERSION bump only if loader cannot default missing fields (prefer additive v1)  

## Test plan

- [ ] Unit: ladder match order  
- [ ] Unit: missing branch → generic node  
- [ ] Unit: old graph JSON still parses  
- [ ] Director tests (wave B): envelope `metrics.branch` selects the branch node  

## Docs impact

- [ ] `COMMENTARY_ENGINE.md` — select ladder  
- [ ] Epic §4  
- [x] CONFIG — no  

## Config impact

None. Branch is an envelope metric, not an INI key.
