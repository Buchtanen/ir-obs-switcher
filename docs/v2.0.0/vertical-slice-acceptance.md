# #278 Vertical-slice acceptance

**Status:** Slice 1 — offline machine-fixture pytest consumer (no live Windows §24.9 GO).

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

## Later slices

- Runtime NarrativeRuntime drivers for remaining F scenarios.
- Live Windows/iRSDK/OBS/Ollama/TTS §24.9 gates.
