# Testy, CI, release

- Pytest: `./run_tests.sh` / `run_tests.ps1`.
- CI: `.github/workflows/ci.yml` — ruff, black, mypy, tests+coverage (blocking).
- PR do `master`: přesně jeden `semver:*` label (`RELEASE_POLICY.md`). Check `semver-label` na `opened` počká na label z API (~60 s); nepíše ho. Policy: `scripts/check_semver_label.py`, testy `tests/test_semver_label.py`.
- Verze se nebumpuje v běžném PR. Release Please.

Index testů je prefix `tests/test_<oblast>.py`, ne historický `tests.md` katalog počtů.

## Related

[RELEASE_POLICY.md](../../../RELEASE_POLICY.md), [VERSIONING.md](../../../VERSIONING.md), skill `pr-semver-label`.
