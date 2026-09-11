# #278 Vertical-slice acceptance

**Status:** Slice 6 — offline director policy drivers for F23/F37 (no live Windows §24.9 GO).

## Slice 1 — frozen projection harness

| Contract | Value |
| --- | --- |
| Machine fixtures | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (**44** / F01–F44) |
| Executable expectations | **248** |
| Boundary calculations | **14** |
| Fail-closed mutations | **16** (`vertical-slice-mutations.json`) |
| Builder | `docs/v2.0.0/machine/build_vertical_slice_fixtures.py` |
| Pytest consumer | `tests/test_vertical_slice_fixtures.py` |

**AC locks (Slice 1):**
- Frozen artifacts match builder (`validate_all` / canonical equality).
- Mutations remain fail-closed.
- Gap inventory records **6/44** named unit-test touchpoints; **38** remain unwired for later runtime slices.
- Does **not** rewrite `machine/*` hashes; does **not** claim live speech or §24.9 GO.

## Slice 2 — F08/F15/F24 expiry runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F08` (speaking critical / no prepared queue), `F15` (fact-only invalidation), `F24` (half-open TTL + mailbox skip) |
| Pytest | `tests/test_vertical_slice_expiry_runtime.py` |
| Inventory | **9/44** wired; **35** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 2):**
- Machine projection for F08/F15/F24 still matches frozen expectations/calcs.
- Runtime drivers prove no barge-in / no prepared queue, fact-only silence path, half-open expiry without fallback.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 3 — F02/F03/F04 transition runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F02` (canonical P0>Q0>R0 inheritance), `F03` (Race→Qualifying rewind), `F04` (confirmed same-session restart) |
| Pytest | `tests/test_vertical_slice_transition_runtime.py` |
| Inventory | **12/44** wired; **32** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 3):**
- Machine projection for F02/F03/F04 still matches frozen expectations.
- Runtime drivers prove lineage inheritance, ordered rewind without `SESSION_REWOUND`, speech cancel on occurrence reset, and confirmed restart without false positives.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 4 — F05/F06/F07 director scoring runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F05` (first pursuit / controlled open score), `F06` (related continuation preference), `F07` (inclusive switch margin) |
| Pytest | `tests/test_vertical_slice_scoring_runtime.py` |
| Inventory | **15/44** wired; **29** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 4):**
- Machine projection for F05/F06/F07 still matches frozen expectations/calcs (`score_70` / `score_76` / margin boundaries).
- Runtime drivers prove threshold open without V4 priority term, related successor over weather filler, and inclusive switch margin (82 holds / 84 switches).
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 5 — F01/F10/F17 stream + silence runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F01` (stream before session), `F10` (long-silence filler threshold), `F17` (lobby stream-scope filler) |
| Pytest | `tests/test_vertical_slice_silence_runtime.py` |
| Inventory | **18/44** wired; **26** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 5):**
- Machine projection for F01/F10/F17 still matches frozen expectations/calcs (`score_36` / threshold gte).
- Runtime drivers prove null session identity on stream start, 24+12 silence pressure selecting filler, and lobby filler limited to stream facts with missing-track rearm.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 6 — F23/F37 director policy runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F23` (fatigue / order / story cap one formula), `F37` (switch policy vs urgency sort / filler) |
| Pytest | `tests/test_vertical_slice_policy_runtime.py` |
| Inventory | **20/44** wired; **24** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 6):**
- Machine projection for F23/F37 still matches frozen expectations/calcs (half-life 0.5 / effective cap 2).
- Runtime drivers prove base-2 fatigue, stable `(40,3)` order, cadence cap with closing escape, inclusive margin switch, lower-urgency switch, critical priority, filler fallback-only, and inclusive replacement breakdown.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Later slices

- Runtime NarrativeRuntime drivers for remaining F scenarios.
- Live Windows/iRSDK/OBS/Ollama/TTS §24.9 gates.
