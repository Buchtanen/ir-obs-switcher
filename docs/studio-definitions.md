# Studio definitions: domain contract

Work item #373; branch `feat/studio-authoring`, integration base `eae7071`.
Status: implementation and scoped test evidence recorded in [studio-authoring.md](studio-authoring.md); final packaging checks remain pending. User decisions: new stories allowed; validatable links
editable; unsupported behavior parameter-only/read-only; history current-run only;
activation effective at next startup.

## Artifact and authority

The editable artifact is JSON with `schemaVersion: "studio-definitions/1"`,
`baseCatalogHash`, a complete `stories` list containing existing and new stories, and `edges`.
The hash binds to the authoritative frozen narrative catalog. Saving does not
rewrite frozen catalog artifacts or their certification hashes. New stories reuse
known beats and certified successor-edge IDs; they cannot introduce executable
guards, emitters, predicates, source code, new beat types or arbitrary edges.

Each story has a unique stable ID, open/update/close beat memberships, selected
certified successor edges, bounded `cadence_minimum_ms` and
`max_consecutive_non_closing_beats`, and a supported `on_no_eligible_successor` disposition.
Typed domain projection follows `StoryDefinition`/`SuccessorEdge` in
`contracts/catalog_loader.py`. Existing guards, emitter parameters and edge
attributes are read-only unless an explicit validated parameter capability exists.
Unsupported values remain visible with evidence explaining the limitation.
INI settings use the existing FieldSpec writer; definitions never write INI.

## Validation and capabilities

Reject unknown properties/schema versions, duplicate IDs/memberships, unknown beat
or edge IDs, catalog hash mismatch, invalid types/bounds and unsupported disposition.
Validate each membership's supported role; selected edge endpoints must belong to
the story. New occurrence stories require opening and closing membership and registered triggers; termination/reachability evidence remains required. Cycles need the certified guard semantics
plus cadence/nonclosing cap; graph shape alone cannot prove termination.

Capabilities expose exact numeric bounds, supported dispositions, role eligibility
and certified edge choices from authoritative data. The UI must not invent them.
Concrete bounds and identity rules are recorded below. The frozen
loader validates baseline identities/hash tables exactly, so a separate overlay
validator must compose overrides with the frozen catalog without weakening its
baseline checks.

## Persistence and revision conflicts

Store beside the active config file as `studio-definitions.json`, independently
of current working directory. One bounded file owns immutable revisions, generation,
effective revision and pending revision. Retain at most 32 revisions, with effective
and pending revisions protected from pruning. If the remaining retained set cannot
fit, fail explicitly; never evict a referenced revision. Validate artifact size
before parsing/writing and use bounded JSON serialization.

Mutation requests supply optimistic `baseRevision` generation. A stale generation
returns a conflict without overwriting data. Successful save appends a validated
immutable revision and advances generation; it does not select or activate it.
Selecting a pending revision is a distinct validated mutation with its own conflict
check. Atomic single-file replacement preserves the previous valid file on write
failure. Serialize concurrent mutations and move filesystem work off async loops.
Reading/exporting a revision never changes generation or activation state.

Imported JSON is an untrusted draft: parse, validate, show diff, then explicitly save.
Export contains the versioned artifact, not credentials or absolute installation
paths. Missing store means built-in baseline; malformed store must be diagnosed
without crashing the main service loop or silently overwriting it.

## Startup-only activation and rollback

At service startup, validate the selected pending revision against the current
catalog and compose a typed runtime catalog before dependent runtime construction.
Promote it to effective only after successful validation/composition. Report
effective and pending revision separately; no hot reload applies definition changes.
On pending failure, use the last valid effective revision; if that also fails, use
built-in definitions and expose the failure reason. Failed promotion/persistence
must not claim that a revision became effective.

Rollback selects a prior retained valid revision for the next startup. Running
instances keep their current definition snapshot; current-run episode records
retain the definition/revision identity used when created. Changing pending or
saved revisions does not rewrite history. A startup activation must reach the
actual story consumers and routing policy; saving a store alone is insufficient.

## UI contract

Provide JSON editing, a new-story form, import/export, revision diff, undo/redo and
validation errors. Save and “use at next startup” are separate controls. Explain
pending restart and current effective revision. Keep unsaved draft through module
navigation; warn on leave/reload. Conflict or failed save preserves the draft.
After an uncertain write, reread generation/revisions before retrying.

Render graph/list from authoritative memberships and selected edges. Native SVG
requires no new dependency. Zoom, pan and node position are local UI preferences;
their changes never save or activate a definition. Invalid/missing preferences
cannot prevent graph use. Read-only guard/emitter details remain distinguished
from editable story topology and supported parameters.

## Required evidence and open implementation decisions

- [ ] Define concrete API request/response fields, generation token semantics, numeric and artifact bounds, ID rules and supported dispositions.
- [x] Prove new-story routing: reused beats and event routes must select the new story with deterministic ownership; do not claim executability from validation alone.
- [ ] Verify overlay composition against frozen catalog/hash checks and known guard/role rules.
- [x] Test rejected references/edges/cycles/parameters and valid representative new story.
- [ ] Test optimistic conflicts, concurrent writes, bounded retention, protected revisions and failed atomic replacement.
- [ ] Test pending→effective at startup, corrupt/hash-incompatible pending fallback, effective fallback and built-in recovery.
- [ ] Test no live activation, no INI writes, history revision identity and rollback next startup.
- [x] Test UI draft/import/export/diff/undo/redo and conflict recovery with disposable store browser QA; graph selection/narrow layout verified. Layout persistence failure and uncertain-write paths still require their specific evidence.

The original bounds and routing questions are resolved by the decisions below; acceptance checkboxes still require evidence.
## Concrete schema and routing decisions

Top-level fields are exactly `schemaVersion`, `baseCatalogHash`, `stories`, `edges`.
Story and edge records use snake_case fields from `StoryDefinition`/`SuccessorEdge`.
The catalog hash identifies immutable beat/realization content; the saved document
SHA-256 identifies a revision separately.

- Stories: 1–64; stable lowercase IDs match `[a-z][a-z0-9_.-]{0,63}`.
- `cadence_minimum_ms`: integer 0–3,600,000; `max_consecutive_non_closing_beats`: integer 1–16.
- Built-in story IDs cannot be removed. New occurrence stories require open and close memberships and registered triggers.
- Membership roles remain registered; all baseline beats retain a story route. Selected edge records must match certified records exactly; each story edge list matches selected edges within its memberships.
- Uncertified guards, rewired edges, emitter/code behavior remain unsupported/read-only capabilities.
- Each artifact is bounded to 128 KiB; at most 32 revisions are retained with effective/pending protected. Store reads have a separate 5 MiB limit.

At startup the composed catalog is injected into story consumers.
`observe_story_events` observes each accepted narrative kind into all declared story
memberships, using independent world instances rather than exclusive first-match
routing. Instances are scoped by occurrence/lineage/correlation; source event IDs
provide evidence. Shared beats do not collapse distinct story identities.

The prior reachability blocker is resolved for new occurrence stories: validator
checks opening-to-closing reachability and rejects untriggered unreachable
nonterminal beats. Routing uses catalog event routes/registered triggers and
confirmed occurrence stage, including lifecycle observations. Definition and
catalog tests cover these cases; cumulative evidence and remaining packaging
checks are recorded in [studio-authoring.md](studio-authoring.md).
