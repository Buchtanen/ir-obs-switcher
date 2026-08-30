# Commentary content DB + fill plan

**Status:** plan / working document (return here; not implemented beyond PR #120 scaffolding)  
**Depends on:** [COMMENTARY_ENGINE.md](../COMMENTARY_ENGINE.md), PR #120 (`cursor/commentary-engine-2dc4`)  
**Out of scope:** Neo4j or any new runtime DB dependency; overlay HUD / Event Engine math; OBS media sink

## 1. Intent check (keep re-reading)

| Claim | Truth in this repo |
| --- | --- |
| “Grafová DB” | **Graph-shaped content store**: nodes + edges + variant cells. Today that is `src/irswitch/commentary/data/sequence_graph.json` loaded by `graph.py`. **Not** Neo4j / SQLite / network graph DB. |
| Who decides *what happened* | Event Engine (emit → arbitrate → `EventEnvelope`). |
| Who decides *whether / what to speak* | `CommentaryDirector` after accepted envelopes. |
| Who writes *spoken text* | Another **text model** (or human), via assignment briefs → validated JSON patch. |
| Today’s mock | EN `neutral` lines on **four** nodes only: `in_car`, `lap_complete`, `pit_entry`, `back_on_track`. Live path works with placeholders. |
| Gradual connect | Mock stays audible until a cell is authored; director already falls back `emotion → neutral` and `locale → en`. Filling a cell is additive. |

If a future proposal needs a real graph DB server, it is a **separate approved track** (new dep + hosting). This plan stays on the JSON graph as the content DB until that is explicitly requested.

## 2. Architecture the plan must respect

```text
iRacing / BLE HR
  → emitters → CandidateEvent
  → EventManager / V2
  → accepted EventEnvelope
  → CommentaryDirector + SequenceGraph
  → validate_utterance
  → TtsSink
```

Stable contracts (do **not** change when filling texts):

- node `id`, `family`, `event_types`, `phases`
- `speak_priority`, `cooldown_s`, `slots`, `hr_states`, `tts.*`
- `edges` (sequence preferences)
- validator rules in `validator.py`
- config keys under `[commentary]` (defaults remain off)

Mutable content surface (this plan fills only this):

- `nodes.*.variants.{locale}.{emotion}` → `list[str]` (1–3 lines per cell)
- optional: `nodes.*.notes` (author hints only)

Playback fallbacks that make gradual fill safe:

1. Empty cell → silence for that emotion (or mock EN if present).
2. Missing emotion bucket → use `neutral` if present (mock stays audible with BLE HR).
3. Missing `cs` → fall back to `en` (`GraphNode.variant_bucket`).
4. `commentary.enabled=false` by default → fill work never forces speech on existing installs.

## 3. Content DB definition (v1)

### 3.1 Physical store (Phase A — now)

| Item | Path / owner |
| --- | --- |
| Document | `src/irswitch/commentary/data/sequence_graph.json` |
| Schema version | top-level `"version": 1` (`GRAPH_VERSION` in `graph.py`) |
| Loader | `load_sequence_graph()` / `parse_sequence_graph()` |
| Integrity | `validate_graph_document()` + catalog event ids |
| Inventory | `SequenceGraph.unfilled_cells()` → `(node_id, locale, emotion)` |
| Briefs | `render_assignments(only_unfilled=True)` |

**Inventory at plan time (graph v1):**

- 26 nodes, 12 edges, locales `en` + `cs`
- Mock-filled EN `neutral`: 4 nodes
- Unfilled cells: **184** (~90 en, ~94 cs) — every emotion × locale without authored lines

### 3.2 Logical cell key

```text
cell_id = "{node_id}/{locale}/{emotion}"
example: "overtake/cs/pushing"
```

Emotion buckets: `neutral` | `calm` | `focused` | `pushing` | `high`  
(`unknown` HR maps to `neutral` for authoring and playback.)

### 3.3 Optional later store (Phase D — not scheduled)

Only if JSON in-repo becomes painful (size, multi-author, A/B):

- Keep the **same logical schema** (nodes/edges/variants).
- Export/import still round-trips to `sequence_graph.json` (or a split `variants/*.json` merged at load).
- No runtime Neo4j unless separately approved. Director must keep loading a local document.

## 4. Fill waves (mock → authored)

Each wave is a PR (or PR slice) that only patches `variants` (+ tests). Mock lines remain until replaced or demoted.

| Wave | Scope | Goal | Mock behaviour |
| --- | --- | --- | --- |
| **W0** | Structure + EN mock (PR #120) | Live path tryable | EN `neutral` on 4 nodes |
| **W1** | EN emotions on mock-4 | Prove emotion matrix without new events | Replace/extend mock with calm/focused/pushing/high; keep ≥1 neutral |
| **W2** | EN high-priority race beats | Speak real race story | Fill: `overtake`, `side_by_side`, `hunting`, `hunted`, `battle_won`, `position_gained`, `position_lost`, `incident`, `final_lap`, `finish` |
| **W3** | EN pit + session sidecar | Close pit story; keep in-car | `pit_outcome`; deepen `pit_entry` / `back_on_track` / `in_car` |
| **W4** | EN timing / quali / practice | Non-race chatter | `personal_best`, `gain_found`, `time_lost`, `target_locked`, `projected_lap`, `hot_lap`, `position_attack`, `clean_streak`, `rival_threat` |
| **W5** | EN bio | Rare HR line | `hr_pressure` (only pushing/high) |
| **W6** | CS parity | Czech speech | Same cell keys as EN waves; director locale `cs` |
| **W7** | Sequence polish | Edge-aware wording | Re-brief nodes that sit on edges so previous/next lines do not clash |

**Recommended order inside a wave:** highest `speak_priority` first (finish → … → hr_pressure), so silence gaps hurt less.

**Definition of done for a wave:**

- [ ] All target cells have 1–3 lines
- [ ] Every line passes `validate_utterance` with that node’s slots + TTS limits
- [ ] Unit test: sample lines bind with example slots; director speaks non-empty for wave events
- [ ] `unfilled_cells()` count drops by the expected number
- [ ] Docs: this plan’s wave checkbox updated; `COMMENTARY_ENGINE.md` mock section if mock nodes change
- [ ] No new dependencies; no Event Engine / overlay behaviour change

## 5. Text-model handoff protocol

### 5.1 Roles

| Role | Responsibility |
| --- | --- |
| **Repo / engineer agent** | Owns graph structure, validator, director, tests. Emits briefs. Merges validated patches. |
| **Text model (author)** | Writes only spoken lines. Does not invent nodes, slots, events, or overlay tokens. |
| **Human reviewer** | Voice taste, CS idiom, merge approval. |

### 5.2 Recommended text model

Default for generation batches:

- **Primary:** Cursor / cloud agent with a strong writing model (prefer Claude Opus-class or GPT-5-class when available in the agent picker).
- **Constraint:** same model for one wave (consistent voice). Do not mix styles mid-wave.
- **Human fallback:** paste the same brief into ChatGPT / Claude web if offline; return JSON in the schema below.

Do **not** use a code-only / “fast” model for authoring — tone drift and ALL-CAPS / stacked punctuation failures waste cycles.

### 5.3 Brief generation (input to the text model)

From a checkout of the commentary branch:

```bash
# Markdown briefs for unfilled cells only (default)
.venv/bin/python -c "from irswitch.commentary import render_assignments; print(render_assignments())" \
  > /tmp/commentary_assignments.md

# One locale / include already-filled (for rewrite waves)
.venv/bin/python -c "from irswitch.commentary import render_assignments; print(render_assignments(locale='cs', only_unfilled=True))"
```

Optional wave filter (engineer): slice the markdown to the node ids of the active wave before sending.

Each brief already includes: event types, phases, slots + examples, emotion hints, previous/next nodes, overlay tokens (do not copy), TTS limits, author notes, deliver rules.

### 5.4 System prompt (paste with every batch)

```text
You fill spoken race-commentary variants for irswitch.
Input: markdown assignment briefs generated by render_assignments().
Output: ONLY a JSON object matching the delivery schema (see plan §5.5).
Rules:
- Fill spoken variants only. Never change node ids, slots, edges, or TTS limits.
- Locales: en and/or cs as requested in the batch header.
- 1–3 lines per emotion cell. Second person or implied driver. One breath.
- Use slot tokens verbatim, e.g. {position}, {gap}, {target_name}.
- Terminal punctuation required: . ! or ?
- Forbidden: ALL-CAPS words, stacked !!/??/..., emoji, URLs, digit runs of 4+.
- SSML only if needed: <break time="…ms"/> (≤500ms) and <emphasis>…</emphasis>.
- Overlay HUD tokens are visual only — do not speak them as labels.
- Intensity comes from word choice per emotion, not shouting.
- Czech (cs): natural spoken Czech for a driver coach, not literal EN translation.
```

### 5.5 Delivery schema (output from the text model)

```json
{
  "graph_version": 1,
  "wave": "W2",
  "author_model": "claude-opus-… / gpt-5-… / human",
  "patches": [
    {
      "node_id": "overtake",
      "locale": "en",
      "emotion": "pushing",
      "lines": [
        "You take {position} from {target_name}.",
        "Past {target_name} — that's {position}."
      ]
    }
  ]
}
```

Rules:

- `graph_version` must match the loaded graph.
- Unknown `node_id` / `locale` / `emotion` → reject whole batch.
- Empty `lines` → reject cell.
- Engineer merges into `sequence_graph.json` under `nodes[node_id].variants[locale][emotion]`.

### 5.6 Merge + verify loop

```text
1. Engineer selects wave + generates briefs
2. Text model returns JSON patches
3. Script/check (manual OK for first waves):
   - schema validate
   - for each line: validate_utterance(line, slots=node.slots, limits=node.tts)
   - optional: fill_slots with examples and speak once on /commentary
4. Patch sequence_graph.json
5. pytest: tests/test_commentary_graph.py + wave-specific asserts in test_commentary_mock.py (or new test_commentary_content_wN.py)
6. Update unfilled count in this doc’s checklist
7. Commit: docs/content only — message like "feat: commentary EN W2 race-beat variants"
```

Suggested one-liner check (after a small helper exists; until then use pytest + `/commentary`):

```bash
.venv/bin/python -c "from irswitch.commentary.graph import load_sequence_graph; print(len(load_sequence_graph().unfilled_cells()))"
```

### 5.7 Batch sizing

| Batch size | Guidance |
| --- | --- |
| Small (preferred) | 1 family or ≤5 nodes × one locale × all emotions |
| Medium | One full wave × one locale |
| Avoid | Entire 184 cells in one shot (voice drift + hard review) |

Pass previous/next node sample lines when the node sits on an `edges` path (W7 / edge-aware batches).

## 6. Gradual mock → data connection map

| Runtime path | Today (W0) | After authored cell |
| --- | --- | --- |
| `in_car` / lap / pit / exit | EN mock `neutral` matrix, `rng.choice` | Same picker; authored emotions used when HR matches; mock `neutral` remains fallback |
| Other graph nodes | Empty → silence | Speak when cell filled |
| Locale `cs` | Falls back to EN mock where EN exists | Speaks CS when CS cell filled |
| Assignments | `only_unfilled=True` lists empty cells (mock EN counts as filled for that bucket) | Shrinks as waves land |
| Overlay / Event Engine | Unchanged | Unchanged |

**Do not** delete mock EN until W1+ has reviewed replacements and a test asserts non-empty `neutral` for those four nodes.

## 7. Non-goals

- Free-form LLM at race time (all speech is pre-authored + validated)
- Changing Event Engine arbitration to “sound better”
- Storing secrets / API keys for external LLM APIs in the repo
- Neo4j / hosted graph DB in Phase A–C
- Reading overlay i18n tokens aloud

## 8. Docs / config impact

| Doc | Action |
| --- | --- |
| This file | Source of truth for fill plan + handoff |
| `COMMENTARY_ENGINE.md` | Link here; keep runtime truth |
| `README.md` | Link under documentation |
| `CONFIG.md` / example ini | No change (no new keys for fill) |
| `API.md` | No change unless a content-admin endpoint is later approved |

## 9. Checklist (progress)

- [x] W0 — structure + EN mock (PR #120)
- [x] W1 — EN emotions on mock-4 (gpt-5 patches; unfilled 184 → 172)
- [x] W2 — EN high-priority race beats (gpt-5; unfilled 172 → 132)
- [ ] W3 — EN pit_outcome *(brief: `docs/commentary_assignments_w3_GPT_PASTE.txt`, 3 cells)*
- [ ] W4 — EN timing / quali / practice *(brief: `docs/commentary_assignments_w4_GPT_PASTE.txt`, 30 cells)*
- [ ] W5 — EN bio
- [ ] W6 — CS parity
- [ ] W7 — sequence polish
- [ ] (optional) Phase D store split / export — only if approved

## 10. Open decisions (parked)

1. Whether CS is primary live locale (dashboard language) before EN is “done” — default: finish EN W2 before large CS batches.
2. Whether mock EN lines stay forever as `neutral` fallbacks or get rewritten in W1.
3. Whether to add `scripts/apply_commentary_patches.py` (stdlib only) once W1 proves the JSON handoff — **not** required to start W1 manually.
4. **`stream_start` node** (OBS stream started + typed samples with irsdk `{vars}` via `fill_slots`) — discussed in PR #120 agent chat, **not in the graph yet**. Treat as a new structure PR before any text-model batch for that node; do not invent free-form LLM lines at stream start.

---

**Return point:** update §9 checkboxes and inventory counts when a wave merges. Do not fork a second plan file — extend this one.
