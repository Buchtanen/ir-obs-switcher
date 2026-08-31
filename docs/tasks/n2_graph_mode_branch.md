# N2 — Sequence graph mode + branch select

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §4  
**Depends on:** umbrella (P1 already on #179); N1 may land in parallel but **this task lands before N8/N11**  
**Blocks:** N8 (`STREAM_START` in `COMMENTARY_ONLY_EVENTS`), N11 A, N3/N5 event type registration

## Context

Need mode/branch select without exploding cells. Shipped `nodes_for(event, phase)` ignores `envelope.mode` and `metrics.branch`. `COMMENTARY_ONLY_EVENTS` is a frozen allow-list — new types fail validation until listed here.

**Trap:** generic `incident` must not beat `off_track` via higher `speak_priority`. Branch/mode match wins the tier, then priority.

**`_follow_edge`:** `director._pick_node` can return a lower-priority node via `self._last` edges. Mode/branch filtering **runs first** (shrink the candidate set). Then `_follow_edge` may pick only if the edge target is still in that set; otherwise fall through to highest `speak_priority` in the filtered set.

## Owns

- `commentary/graph.py` (`GraphNode` optional `modes` / `branch`, `nodes_for` signature, `COMMENTARY_ONLY_EVENTS`)
- `commentary/director.py` pick using `envelope.mode` + `metrics.branch`
- validator + tests
- **Do not** mass-edit `sequence_graph.json` texts (N11)

## Acceptance criteria

- [ ] Optional `modes` and `branch` on nodes; missing fields = today’s behavior
- [ ] Match ladder: event+phase+mode+branch → branch → mode → unfiltered
- [ ] Filter **before** `_follow_edge`; edge target that fails mode/branch is ignored
- [ ] Inside a remaining tier, highest `speak_priority` wins
- [ ] `COMMENTARY_ONLY_EVENTS` **in this commit** includes `SESSION_FLAG` and `STREAM_START` (even with no graph nodes yet — so later JSON cannot fail the loader). Keep `BACK_UNDER_WAY`. **No** `INCIDENT_RECOVERED`
- [ ] Tests: graph with `event_types: ["STREAM_START"]` loads; unknown type still errors
- [ ] Per-node `tts.max_seconds` already parses; N11 sets the stream_start long cap + validator exception
- [ ] Old graphs still parse

## Test plan

- [ ] Ladder order
- [ ] Generic incident does not steal an off_track node in the same event_type set
- [ ] Default graph still loads (node count may stay 34 until N11)

## Docs impact

- [ ] `COMMENTARY_ENGINE.md` select ladder
- [x] CONFIG — no

## Config impact

None.
