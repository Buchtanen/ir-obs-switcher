# Studio catalog, authoring, episodes and replay

P3–P6 implementation on `feat/studio-authoring`, accumulated into
`feat/studio-integration`. This is current branch documentation, not a claim of
release to master. Definition contract: [studio-definitions.md](studio-definitions.md).

## Operator workflow

Eventy/Scénáře search the authoritative catalog and offer list and native SVG graph
views. Select a beat to inspect registered triggers, story memberships, certified
edges and supported FieldSpec settings. Zoom/pan/node placement are local layout
preferences; layout never changes the engine. OBS scene logic remains separate.
Unsupported guard/emitter parameters are visible as read-only evidence.

The definition editor accepts JSON and a new-story form, with import/export,
revision diff, undo/redo and unsaved-draft protection. Validate and save before
selecting a revision for the **next startup**. Saving does not activate it; current
runtime definitions remain unchanged. Optimistic `baseRevision` conflicts preserve
the draft and require rereading/reconciliation. Rollback selects an older retained
valid revision for the next startup. No definition action writes INI.

Definitions live in `studio-definitions.json` beside the active config file.
The store retains at most 32 immutable revisions and protects effective/pending
ones. Artifact limit is 128 KiB; store limit is 5 MiB. Atomic replacement and
off-loop filesystem work preserve the last valid state on failure. Startup
validates pending→effective, then falls back to the last valid effective revision
or built-in catalog with an explicit error if needed.

Epizody shows bounded **current-run** instances, recorded transitions, source-event
evidence and decisions linked by exact episode identity. Provider absence differs
from an empty list. Pagination and runId protect against combining different runs;
rewind/occurrence/lineage boundaries remain explicit. `historyComplete=false`
reports truncated history. No cross-restart history database is introduced.

Replay lists 16 packaged existing overlay input scenarios and one existing
narrative accepted-context/shutdown fixture. Each run creates fresh isolated
runtime/registry/manager state and virtual input time. Narrative drafts can be
validated and replayed without saving or activating. Results expose output hash,
timeline, episodes/history and isolated run identity. The UI clock, reset and
comparison observe these recorded outputs; replay never dispatches OBS/TTS effects.
Renderer demo and confirmed live debug emission remain separate operations.

## API and module map

| Module | Responsibility |
| --- | --- |
| `server/studio_data.py` | Versioned catalog and current-run episode HTTP projections |
| `server/studio_authoring.py` | Loopback/same-origin/header/body-bounded revision transport |
| `contracts/studio_definitions.py` | Closed validator, typed catalog composition and atomic bounded revision store |
| `contracts/runtime_catalog.py` | Startup effective catalog/status supplied to actual story consumers |
| `events/studio_story_projection.py` | Authoritative event route/trigger observation into independent story instances |
| `events/episode_registry.py` | Bounded instance/history ownership and snapshot |
| `server/studio_replay.py` | Serialized isolated fixture replay, no live sinks |
| `frontend/studio/src/Catalog.tsx`, `Definitions.tsx`, `Replay.tsx` | Native catalog/episode/editor/replay views |
| `contracts/schemas/v2/studio-replay-scenarios.json`, `studio-narrative-replay.json` | Packaged existing fixture projections |

Paths in the table are relative to `src/irswitch/` except frontend paths.
HTTP contracts are in [API.md](../API.md).

## Verification evidence — 2026-09-27

- Parent reports 187 Python tests passed across the relevant scope.
- HTTP same-origin/conflict checks and determinism of all 17 replay fixtures passed;
  each pair has different run IDs, matching outputs/hash and leaves the live provider unchanged.
- Chrome authoring QA passed against a disposable real revision store: malformed
  JSON, undo/redo, navigation dirty state, save/select, optimistic conflict, export,
  graph click, custom narrative replay and narrow layout.
- Tests: [definition validation/store/startup/routing](../tests/test_studio_definitions.py),
  [catalog/episode identity/history](../tests/test_studio_catalog.py),
  [HTTP and replay](../tests/test_studio_authoring_http.py).
- New occurrence stories require opening-to-closing reachability. Event observation
  uses authoritative catalog routes/triggers and confirmed occurrence stage,
  including lifecycle events; shared memberships create independent world instances.
- A preexisting derived source-hash contract was corrected in its source/package
  counterpart; remaining frozen artifacts were unchanged. This does not authorize
  rewriting catalog identity or certification contracts through the editor.

Wheel build passed. Bounded socket reconnect/invalidation plus polling tests passed; 20 frontend tests/typecheck and all three Chrome suites passed. Source verifier GREEN. Final EXE and wheel runtime/package smoke passed; details below. No production OBS/audio effects were tested. Existing routes
remain compatibility surfaces; full status fields are exposed in JSON readback
alongside native summaries. No legacy retirement claim is made.

## Final replay and package evidence

Final verifier GREEN covers timeline visualization of recorded command/event outputs
and pinned-reference comparison. Graph edges mean recorded sequence, not causal
claims. Results expose reference/current hashes, first differing output and full
recorded results. No invented live node activity is shown.

`scripts/qa_studio_package.py` passed for final EXE (`build/studio-package-woboz3m4`)
and wheel (`build/studio-package-a7l9dkkl`) with final hashes
`index-3ptC8BvU.js` / `index-CNCWPKvB.css`. Three disposable-config starts verify
asset and legacy routes, save/select with builtin still effective, next-startup
custom catalog, isolated custom replay and following-startup builtin rollback.
INI bytes remain unchanged. Wheel packaged assets match source file set and bytes.
The QA rejects missing/stale assets; stale incremental setuptools `build/lib`
Studio resources were removed before repackaging and the final QA passed.
P0–P6 scoped acceptance is complete. No production OBS/TTS/OAuth effect was tested;
legacy routes remain available and are not retired.