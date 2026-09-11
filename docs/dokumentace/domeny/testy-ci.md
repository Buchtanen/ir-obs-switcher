# Testy, CI, release

- Pytest: `./run_tests.sh` / `run_tests.ps1`.
- CI: `.github/workflows/ci.yml` — ruff, black, mypy, tests+coverage (blocking).
- PR do `master`: přesně jeden `semver:*` label (`RELEASE_POLICY.md`). Check `semver-label` na `opened` počká na label z API (~60 s); nepíše ho. Policy: `scripts/check_semver_label.py`, testy `tests/test_semver_label.py`.
- Verze se nebumpuje v běžném PR. Release Please.

Index testů je prefix `tests/test_<oblast>.py`, ne historický `tests.md` katalog počtů.

## #278 vertical-slice fixture pytest harness (Slice 1)

**Status:** offline consumer on branch `cursor/vertical-slice-fixtures-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (**5** tests) |
| Acceptance doc | [vertical-slice-acceptance.md](../../v2.0.0/vertical-slice-acceptance.md) |
| Prose + F01–F44 spec | [vertical-slice-fixtures.md](../../v2.0.0/vertical-slice-fixtures.md) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` |
| Fail-closed mutations | `docs/v2.0.0/machine/vertical-slice-mutations.json` |
| Builder / validator | `docs/v2.0.0/machine/build_vertical_slice_fixtures.py` |

**Slice 1 locks:** frozen JSON matches builder output; **16** mutations stay fail-closed; gap inventory records **6/44** scenarios with adjacent unit-test touchpoints at Slice 1 land (**38** unwired then; superseded by Slice 2 inventory below).

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**.

Lookup: [inflight § #278 slice 1](../inflight/README.md#278-vertical-slice-fixtures-slice-1-lookup) · [acceptance § Slice 1](../../v2.0.0/vertical-slice-acceptance.md#slice-1--frozen-projection-harness) · [dokumentace index](../README.md).

## #278 vertical-slice expiry runtime (Slice 2)

**Status:** offline F08/F15/F24 drivers on branch `cursor/vertical-slice-expiry-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_expiry_runtime.py`](../../../tests/test_vertical_slice_expiry_runtime.py) (**6** tests: **3** parametrized machine projection + F08/F15/F24 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **9/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 2](../../v2.0.0/vertical-slice-acceptance.md#slice-2--f08f15f24-expiry-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F08/F15/F24 rows; hashes **unchanged**) |

**Slice 2 locks:** F08 speaking-critical / no prepared queue; F15 fact-only invalidation silence; F24 half-open TTL + mailbox skip; machine projection still matches frozen expectations/calcs; gap inventory **9/44** wired, **35** unwired.

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**; no live §24.9 GO.

Lookup: [inflight § #278 slice 2](../inflight/README.md#278-vertical-slice-expiry-runtime-slice-2-lookup) · [dokumentace index § #278](../README.md).

## #278 vertical-slice transition runtime (Slice 3)

**Status:** offline F02/F03/F04 drivers on branch `cursor/vertical-slice-transition-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_transition_runtime.py`](../../../tests/test_vertical_slice_transition_runtime.py) (**6** tests: **3** parametrized machine projection + F02/F03/F04 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **12/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 3](../../v2.0.0/vertical-slice-acceptance.md#slice-3--f02f03f04-transition-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F02/F03/F04 rows; hashes **unchanged**) |

**Slice 3 locks:** F02 canonical P0>Q0>R0 lineage inheritance; F03 ordered Race→Qualifying rewind without `SESSION_REWOUND`, speech cancel on occurrence reset; F04 confirmed same-session restart without false positives; machine projection still matches frozen expectations; gap inventory **12/44** wired, **32** unwired.

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**; no live §24.9 GO.

Lookup: [inflight § #278 slice 3](../inflight/README.md#278-vertical-slice-transition-runtime-slice-3-lookup) · [dokumentace index § #278](../README.md).

## #278 vertical-slice scoring runtime (Slice 4)

**Status:** offline F05/F06/F07 drivers on branch `cursor/vertical-slice-scoring-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_scoring_runtime.py`](../../../tests/test_vertical_slice_scoring_runtime.py) (**7** tests: **3** parametrized machine projection + F05/F06/F07 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **15/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 4](../../v2.0.0/vertical-slice-acceptance.md#slice-4--f05f06f07-director-scoring-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F05/F06/F07 rows; hashes **unchanged**) |

**Slice 4 locks:** F05 opening pursuit score 70 clears threshold without V4 priority term; F06 related continuation preferred over weather filler; F07 inclusive switch margin (82 holds / 84 switches); machine projection still matches frozen expectations/calcs; gap inventory **15/44** wired, **29** unwired.

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**; no live §24.9 GO.

Lookup: [inflight § #278 slice 4](../inflight/README.md#278-vertical-slice-scoring-runtime-slice-4-lookup) · [dokumentace index § #278](../README.md).

## Related

[RELEASE_POLICY.md](../../../RELEASE_POLICY.md), [scripts/README.md](../../../scripts/README.md) (`check_semver_label.py`), [VERSIONING.md](../../../VERSIONING.md), skill `pr-semver-label`.
