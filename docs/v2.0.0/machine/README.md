# v2.0.0 branch-only machine freeze artifacts

These files make the human design registries mechanically reviewable before runtime implementation. These documentation-path copies and generators are planning evidence and must be removed by the final-PR exclusion gate. Implementation promotes byte-equivalent canonical registry/schema outputs into `src/irswitch/contracts/schemas/v2/`; those packaged runtime artifacts are retained in the final PR.

- `freeze-registry.json` is the canonical generated projection of the event, lifecycle-event, fact, feature, scalar/enum, reason-domain, terminal-state, director-relation, schema-version and `tape_channel` tables.
- `v4-event-envelope.golden.json` pins the complete master `EventEnvelope.to_dict()` surface and canonical SHA-256 at baseline `0ce75d4`.
- `build_freeze_registry.py` rebuilds the registry in memory and fails if the checked-in artifact is stale, a count/reference/type is invalid, the V4 golden hash changes, narrative fields leak into V4, or current freeze/thaw no longer round-trips exactly.
- `dto-contracts.schema.json` contains 25 closed Draft 2020-12 definitions for every DTO in the architecture gate, including the discriminated 17-kind NarrativeCommand union.
- `dto-schema-goldens.json` and `build_dto_schemas.py` pin positive/negative structural examples, reject unknown/snake-case fields and validate without an undeclared third-party dependency.
- `beat-catalog.json` is the generated exact 64-BeatDefinition projection: trigger routes, story routes, policy/channel, structured session/scene/vehicle axes, claim cardinality/attributes/constraints, global and per-beat forbidden claims, realization family/backend and the four-card minimum.
- `beat-catalog.schema.json`, `beat-catalog-mutations.json` and `build_beat_catalog.py` enforce the closed Draft 2020-12 shape, all fact/family/policy/channel references, exact group counts and canonical lifecycle routing. Nine mutations prove representative invalid catalogs fail closed.
- `successor-graph.json` is the closed 64-node/50-edge natural-successor projection with typed correlation/condition tokens, exact preference bonuses, StoryDefinition caps/cadence, terminal node policies and computed SCC evidence.
- `successor-graph.schema.json`, `successor-graph-mutations.json` and `build_successor_graph.py` reject undeclared edges, dangling references, preference/closure drift, loosened story bounds, stale catalog hashes, false degree/SCC claims and cycles without a bounded-exit proof.
- `config-contract.json` and `config-contract.schema.json` freeze the 50 static keys, two detector templates, defaults, types/ranges/units, boundary owners, sensitive/preflight sets and 13 reject-only v1 migration dispositions.
- `config-goldens.json` and `build_config_contract.py` validate defaults, local/LAN URL and cross-field rules, invalid and legacy inputs, and the F36 generation-7 mixed-boundary/preflight plus generation-8 pending-revert replay.
- `api-contract.json` and `api-contracts.schema.json` freeze four routes, eight closed public payload definitions, nine error/status pairs, write transport bounds, health augmentation, privacy exclusions and the removed assignments route.
- `api-goldens.json` and `build_api_contracts.py` validate ready/degraded status, decision nullability/order, offline validation bindings, manual speech admission, all public errors, transport/limit guards and registry-backed cross-field invariants.
- `actor-transition-model.json` and its schema enumerate the exact five speech-lane states × 17 NarrativeCommand kinds, single-mailbox partitions, admission/coalescing rules and planning-cycle bounds.
- `actor-transition-goldens.json`, `actor-transition-mutations.json` and `build_actor_transition_model.py` execute token/reset/deadline/manual/quarantine/shutdown races, overflow recovery and same-time reducer ordering while rejecting structural policy drift.
- `detector-catalog.json` and its schema freeze the two directional battle detectors' identical 23-parameter algorithm and the two-parameter two-front composite, including ordered actor/correlation identity and registry-backed outputs.
- `detector-catalog-goldens.json`, `detector-catalog-mutations.json` and `build_detector_catalog.py` execute FSM/sign/unknown/rate-limit, band-hysteresis and composite-correlation fixtures and reject unsafe parameter, identity, reference and release-policy drift.
- `catalog-loader-contract.json`, `catalog-loader-goldens.json` and `build_catalog_loader_contract.py` bind registry, beat, graph and detector hashes and exercise mandatory closed-schema, ID/reference, trigger reachability, dead-end/SCC, guard, range, config-template and fail-safe loading checks.

Run from the repository root:

```bash
python3 docs/v2.0.0/machine/build_freeze_registry.py
python3 docs/v2.0.0/machine/build_dto_schemas.py
python3 docs/v2.0.0/machine/build_beat_catalog.py
python3 docs/v2.0.0/machine/build_successor_graph.py
python3 docs/v2.0.0/machine/build_config_contract.py
python3 docs/v2.0.0/machine/build_api_contracts.py
python3 docs/v2.0.0/machine/build_actor_transition_model.py
python3 docs/v2.0.0/machine/build_detector_catalog.py
python3 docs/v2.0.0/machine/build_catalog_loader_contract.py
```

Expected baseline summary:

```text
freeze registry OK: 60 events + 5 lifecycle, 57 predicates, 21 features, 36 tape channels, 6 relations, 27 schemas
DTO schemas OK: 25 definitions, 5 valid + 5 invalid goldens
Beat catalog OK: 64 beats, 37 families, 9 rejected mutations
Successor graph OK: 64 nodes, 50 edges, 36 no-continuation nodes, DAG, 10 rejected mutations
Config contract OK: 50 static + 2 template keys, 14 boundaries, 13 migrations, 2 valid + 8 invalid + 2 legacy goldens, mixed-boundary replay
API contracts OK: 4 routes, 8 public schemas, 18 valid + 10 invalid payload goldens, 6 transport/query guards, 1 removed route
Actor transition model OK: 5 lanes × 17 commands = 85 pairs, 13 race traces, 10 overflow scenarios, 10 rejected mutations
Detector catalog OK: 3 definitions, 23 directional + 2 composite parameters, 7 FSM traces + 14 boundary/composite fixtures, 12 rejected mutations
Catalog loader contract OK: 4 hashed inputs, 12 mandatory checks, 64 beats reachable, 15 rejected integration mutations
```

Reason identity is the pair `(reasonDomain, reasonId)`. Repeated strings across domains are intentional only when their plain-language meaning is identical; uniqueness is enforced inside each domain.

The JSON Schema bundles close field names, types, bounds, nullability, enums, unions and unknown-field rejection. Cross-object/order/hash constraints that Draft 2020-12 cannot compare directly are mandatory named `x-irswitch-invariants`; implementation validators and the structured F01–F44 fixtures must execute those IDs rather than ignore them. The packaged schemas are replay/tooling/API contracts, while typed runtime parsing remains the hot-path authority.
