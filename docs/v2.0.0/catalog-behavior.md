# v2 catalog behavior (implementation projection)

**Status:** generated from the packaged catalogs by [#256](https://github.com/Buchtanen/ir-obs-switcher/issues/256); branch-only, not shipped to `master`.
**Auditor:** `irswitch.contracts.coverage_matrix.audit_coverage_matrix`
**Tests:** `tests/test_coverage_matrix.py` (**15**)

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

## Out of scope

- StoryDefinition production loader ([#257](https://github.com/Buchtanen/ir-obs-switcher/issues/257))
- live EventManager / NarrativeRuntime / V4 overlay tape
- public CONFIG / API / README product contracts
