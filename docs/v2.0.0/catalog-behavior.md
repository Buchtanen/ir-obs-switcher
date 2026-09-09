# v2 catalog behavior (implementation projection)

**Status:** generated from the packaged catalogs by [#256](https://github.com/Buchtanen/ir-obs-switcher/issues/256); typed loader by [#257](https://github.com/Buchtanen/ir-obs-switcher/issues/257); lineage-aware EpisodeRegistry by [#258](https://github.com/Buchtanen/ir-obs-switcher/issues/258); resolved-episode retention by [#259](https://github.com/Buchtanen/ir-obs-switcher/issues/259) (implemented, not closed); branch-only, not shipped to `master`.
**Auditor:** `irswitch.contracts.coverage_matrix.audit_coverage_matrix`
**Loader:** `irswitch.contracts.catalog_loader.load_narrative_catalog`
**Registry:** `irswitch.events.episode_registry.EpisodeRegistry`
**Retention:** `irswitch.events.episode_retention.EpisodeRetention`
**Tests:** `tests/test_catalog_loader.py` (**29**) + `tests/test_coverage_matrix.py` (**15**) + `tests/test_episode_registry.py` (**13**) + `tests/test_episode_retention.py` (**9**)

This page is the implementation-time behavior contract for the frozen event-family matrix. Human design prose stays in [event-beat-disposition.md](event-beat-disposition.md), [fact-feature-registry.md](fact-feature-registry.md) and [detector-catalog-freeze.md](detector-catalog-freeze.md). Machine hashes under `machine/` were reviewed and left unchanged.

## Frozen counts

| Item | Count |
| --- | ---: |
| Current identifiers | 60 |
| Speakable | 52 |
| Visual / operator-only | 4 |
| Compatibility alias | 4 |
| BeatDefinitions | 64 |
| Realization families | 37 |
| Policy profiles | 6 |
| `tape_channel` values | 36 |
| Enabled EN pattern cards | 256 (4 per beat) |
| Successor edges | 50 |
| Story routes | 11 |
| Fact predicates | 57 |
| Features | 21 |
| Detectors | 3 (all `experimental`, `tuning.policy=required`) |

Released detectors must not keep `tuning.required`. The three current detectors remain experimental calibration entries.

## EventOpportunity rule

- `eventClass=speakable` may later create an EventOpportunity.
- `visual_only` and `compatibility_alias` never create speech. Extra beat pointers on those rows are ignored.
- `UNDER_PRESSURE` is not a current identifier.
- Replaced lifecycle identifiers (`STREAM_START`, `SESSION_INTRO_*`, `SESSION_WRAP`) cannot appear as v2 beat triggers. Canonical kinds are `STREAM_STARTED`, `SESSION_STARTED` and `SESSION_ENDED`.

## Beat resolution

Every BeatDefinition resolves all of:

- at least one ordered story route from the 11-route successor graph
- one realization family and one of the six policy profiles
- one registered `tape_channel`
- enabled freedom `tight` only (not above the family `promotedMaxFreedom`)
- at least four enabled audited EN pattern cards

Stage / broadcast / vehicle axes use the normalized enums only. Raw OBS scene names are rejected.

## Successor graph and SCC

`successor-graph.json` is a 64-node / 50-edge DAG (`strongComponentCount=64`, no cyclic component). 28 nonterminal beats expand only through explicit guarded edges; terminals use `no_implicit_continuation`. Every story carries a cadence floor and consecutive-cap; selection keeps `materialRevisionBonus=6`.

## Replay fixture references

Packaged `coverage-matrix-replay-refs.json` points at existing F01–F44 fixtures. It does not add a NarrativeRuntime:

| Claim family | Fixtures |
| --- | --- |
| transition | F01, F02, F03, F04, F22, F25 |
| identity | F17, F31, F43 |
| expiry | F08, F15, F24 |
| counterfactual | F09, F15, F33, F37 |

## Review before catalog generation

#256 re-read [fact-feature-registry.md](fact-feature-registry.md) and [detector-catalog-freeze.md](detector-catalog-freeze.md) against the packaged freeze registry, beat catalog, successor graph, pattern cards and detector catalog. Counts and references match. No `machine/` hash was rewritten.

## Loader fail-soft contract (#257)

Invalid packaged catalogs disable commentary without raising: `outcome=commentary_disabled`, `CatalogLoadFailure` with `commentaryEnabled=false`, `mainLoopRaises=false`, `partialCatalogPublished=false`, `reason=catalog_invalid`, `runtimeStatus=disabled`. Same-beat authored fallback is forbidden (`same_beat_authored_fallback=False`). No sequence-graph v1 fallback.

## EpisodeRegistry (#258)

`EpisodeRegistry` owns runtime episode instances independently of speech. Schema `episode/2`; states `candidate|active|suspended|resolved|invalidated`. Occurrence scope requires occurrence + lineage; stream-only `stream_lifecycle` (and optional stream `filler_single`) may omit both. Semantic identity locates one live instance; distinct identities run concurrently. Exclusive battle group suspends overlapping live instances. Capacity defaults `active_capacity=64`, `resolved_capacity=256` match the frozen public contract. Not exported from `events/__init__.py`; not live-wired. Module lookup: [inflight § #258](../dokumentace/inflight/README.md#258-lineage-aware-episoderegistry-lookup).

## EpisodeRetention (#259)

`EpisodeRetention` stores bounded resolved-outcome metadata without a prepared-speech queue. Schema `episode-retention/2`. Policy TTL/salience come from frozen catalog families (`critical` 45s/90, `result` 30s/78, `live_story` 10s/64, `transient` 6s/56, `context` 20s/46, `filler` 12s/24). `speakable_until_ms = resolvedMonoMs + ttlMs`; half-open validity `now < speakable_until`. Self-contained `critical`/`result` outcomes remain selectable after speech complete; intermediate `live_story`/`transient` revisions supersede same `(occurrenceId, definitionId, semanticIdentity)` and are `skipped` after speech. `on_speech_complete` re-evaluates `expired_ttl` / `skipped` / remaining self-contained by `(-salience, speakable_until_ms, episodeId)`. Default `resolved_capacity=256` matches the frozen public contract. No BeatPlan / TtsUtterance storage. Not exported from `events/__init__.py`; not live-wired. Module lookup: [inflight § #259](../dokumentace/inflight/README.md#259-resolved-episode-retention-lookup).

## Out of scope

- #260 long-silence lifecycle and filler opportunities
- #261 BeatPlan and just-in-time planner
- live EventManager / NarrativeRuntime / V4 overlay tape
- public CONFIG / API / README product contracts
