# v2.0.0 branch-only machine freeze artifacts

These files make the human design registries mechanically reviewable before runtime implementation. These documentation-path copies and generators are planning evidence and must be removed by the final-PR exclusion gate. Implementation promotes byte-equivalent canonical registry/schema outputs into `src/irswitch/contracts/schemas/v2/`; those packaged runtime artifacts are retained in the final PR.

- `freeze-registry.json` is the canonical generated projection of the event, lifecycle-event, fact, feature, scalar/enum, reason-domain, terminal-state, schema-version and `tape_channel` tables.
- `v4-event-envelope.golden.json` pins the complete master `EventEnvelope.to_dict()` surface and canonical SHA-256 at baseline `0ce75d4`.
- `build_freeze_registry.py` rebuilds the registry in memory and fails if the checked-in artifact is stale, a count/reference/type is invalid, the V4 golden hash changes, narrative fields leak into V4, or current freeze/thaw no longer round-trips exactly.
- `dto-contracts.schema.json` contains 25 closed Draft 2020-12 definitions for every DTO in the architecture gate, including the discriminated 17-kind NarrativeCommand union.
- `dto-schema-goldens.json` and `build_dto_schemas.py` pin positive/negative structural examples, reject unknown/snake-case fields and validate without an undeclared third-party dependency.

Run from the repository root:

```bash
python3 docs/v2.0.0/machine/build_freeze_registry.py
python3 docs/v2.0.0/machine/build_dto_schemas.py
```

Expected baseline summary:

```text
freeze registry OK: 60 events + 5 lifecycle, 57 predicates, 21 features, 36 tape channels, 27 schemas
DTO schemas OK: 25 definitions, 4 valid + 4 invalid goldens
```

Reason identity is the pair `(reasonDomain, reasonId)`. Repeated strings across domains are intentional only when their plain-language meaning is identical; uniqueness is enforced inside each domain.

The JSON Schema bundle closes field names, types, bounds, nullability, enums, unions and unknown-field rejection. Cross-object/order/hash constraints that Draft 2020-12 cannot compare directly are mandatory named `x-irswitch-invariants`; implementation validators and the structured F01–F44 fixtures must execute those IDs rather than ignore them. The packaged schema is a replay/tooling/API contract, while typed runtime parsing remains the hot-path authority. Public HTTP/config goldens and catalog schemas remain separate audit blockers.
