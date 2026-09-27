# Studio completion roadmap

Source: the 2026-09-27 Studio implementation/migration plan at
`C:/Users/richa/Documents/Codex/2026-09-27/kd/outputs/irswitch-studio-plan.md`.
This checked-in roadmap preserves its stage gates and records subsequent explicit
user decisions. Completion requires evidence; source availability is insufficient.

## User decisions for P3–P6

- New stories are allowed. All links that the domain validator can validate are editable; other supported properties are parameter-only edits.
- Episode history is limited to the current run. No persistent cross-restart history is required; do not infer links across run identities.
- Activated definitions become effective only at the next service startup. Save and activation must not alter the current running instances.

These decisions supersede the original plan's open alternatives about topology,
history retention and activation timing. They do not waive validation, revision
conflicts, bounded memory, rollback or isolation requirements.

## Stage gates

| Stage | Deliverable | Completion gate |
| --- | --- | --- |
| P0 | Legacy feature inventory, providers, authoritative catalogs and dependencies | Each feature has an action/data source, target module and parity check; see [studio-parity.md](studio-parity.md) |
| P1 | Packaged shell, navigation, overview and errors | Direct links/reload, disconnected providers, cleaned-up reads, wheel/EXE assets; historical evidence in [studio-implementation.md](studio-implementation.md) |
| P2 | Native settings, OBS, commentary, diagnostics and overlay preview | Existing writer/security contracts, validation/live-restart/drafts, duplicate-action protection, old route compatibility and parity evidence; see [studio-settings.md](studio-settings.md), [studio-operations.md](studio-operations.md) |
| P3 | Authoritative event/story catalog, graph/list, layout and supported contextual parameters | Versioned read projection, real IDs/links/capabilities, layout separate from engine edits; no invented activity or unsupported toggles |
| P4 | Current-run episode list/detail/timeline and real lineage/decision links | Provider absence distinct from empty; run/occurrence identities survive rewind/restart separation; bounded/paged data, preserved recorded history |
| P5 | New stories and validated editable links, revisioned drafts, diff, undo/redo, import/export and activation | Domain specification first; reject unknown references, invalid links/cycles/parameters; baseRevision conflict; atomic persistence, last valid revision and rollback; activation only next startup |
| P6 | Deterministic isolated replay and final migration/package checks | Virtual clock/reset/run IDs, no OBS/TTS writes, repeatable fixture results; failure/restart/rollback/upgrade evidence and parity before retiring legacy pages |

## Definition persistence and startup activation

Configuration remains INI/FieldSpec through its existing writer. Definition drafts
need explicit ID, schemaVersion and baseRevision; they are not another configuration
store. A saved draft is not active. Activation designates a validated revision for
the next startup and shows both currently effective and pending revision. Invalid
save/activation preserves the previous valid artifact. Startup must validate the
pending artifact against authoritative catalog/hash contracts and fail safely.
Rollback selects a prior valid revision for a later startup, without rewriting
current-run episode history. The concrete API and persistence format require a
separate P5 domain specification and verification before implementation claims.

## Integration and final approval

All stages accumulate on `feat/studio-integration`. Stage PRs target that branch;
their merges are authorized after independent verifier GREEN and handover. One
cumulative draft PR presents the complete result to `master`; final merge requires
explicit user approval. Stage completion and cumulative regression evidence must
remain distinguishable. Preserve clean OBS output and standalone VR contracts.
