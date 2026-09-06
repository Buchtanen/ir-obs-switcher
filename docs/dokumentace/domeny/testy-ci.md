# Testy, CI, release

- Pytest: `./run_tests.sh` / `run_tests.ps1`.
- CI: `.github/workflows/ci.yml` — ruff, black, mypy, tests+coverage (blocking).
- PR do `master`: přesně jeden `semver:*` label (`RELEASE_POLICY.md`).
- Verze se nebumpuje v běžném PR. Release Please.

Index testů je prefix `tests/test_<oblast>.py`, ne historický `tests.md` katalog počtů.

## Related

[RELEASE_POLICY.md](../../../RELEASE_POLICY.md), [VERSIONING.md](../../../VERSIONING.md), skill `pr-semver-label`.
