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

**Slice 1 locks:** frozen JSON matches builder output; **16** mutations stay fail-closed; gap inventory records **6/44** scenarios with adjacent unit-test touchpoints (**38** remain unwired for later runtime slices).

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**.

Lookup: [inflight § #278 slice 1](../inflight/README.md#278-vertical-slice-fixtures-slice-1-lookup) · [dokumentace index](../README.md).

## Related

[RELEASE_POLICY.md](../../../RELEASE_POLICY.md), [scripts/README.md](../../../scripts/README.md) (`check_semver_label.py`), [VERSIONING.md](../../../VERSIONING.md), skill `pr-semver-label`.
