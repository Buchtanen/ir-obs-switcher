# v2.0.0 branch-only machine freeze artifacts

These files make the human design registries mechanically reviewable before runtime implementation. They are planning evidence and must be removed by the final-PR exclusion gate.

- `freeze-registry.json` is the canonical generated projection of the event, lifecycle-event, fact, feature, scalar/enum, reason-domain, terminal-state, schema-version and `tape_channel` tables.
- `v4-event-envelope.golden.json` pins the complete master `EventEnvelope.to_dict()` surface and canonical SHA-256 at baseline `0ce75d4`.
- `build_freeze_registry.py` rebuilds the registry in memory and fails if the checked-in artifact is stale, a count/reference/type is invalid, the V4 golden hash changes, narrative fields leak into V4, or current freeze/thaw no longer round-trips exactly.

Run from the repository root:

```bash
python3 docs/v2.0.0/machine/build_freeze_registry.py
```

Expected baseline summary:

```text
freeze registry OK: 60 events + 5 lifecycle, 57 predicates, 21 features, 36 tape channels, 27 schemas
```

Reason identity is the pair `(reasonDomain, reasonId)`. Repeated strings across domains are intentional only when their plain-language meaning is identical; uniqueness is enforced inside each domain.

This package does not yet claim that all DTO JSON Schemas exist. That remains a separate checked blocker in `design-freeze-audit.md`; structural schemas must encode field types, bounds, nullability and cross-field invariants rather than treating this registry as a substitute.
