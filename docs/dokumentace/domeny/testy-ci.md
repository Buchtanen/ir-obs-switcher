# Testy, CI, release

## Testy

- Runner: pytest, `asyncio_mode = auto`, `testpaths = tests`
- `pip install -e ".[test]"`
- Mapování: `tests/test_<modul>.py` ≈ doména. Replay JSON: `tests/fixtures/replay_input/`
- Golden V4: `tests/test_golden_v4_*.py`, `tests/golden_v4_shared.py`
- Přehled starší: [tests.md](../../../tests.md) (může zaostávat za stromem — při konfliktu věř názvu testu + kódu)

Chování: test first (`.cursor/rules/03-tdd-test-drive-policy.mdc`). Bez testu = explicitní TDD-exception v PR.

## CI (GitHub)

Workflows v `.github/workflows/`:

- `tests.yml` — pytest matrix Python 3.11–3.13
- `security.yml` — CodeQL / bandit
- `pr-policy.yml` — přesně jeden `semver:*` label
- `release-please.yml` + `release.yml` — Release PR, tag, build EXE

Větve `cursor/*` **nemusí** spouštět stejné checks jako PR do master (závisí na `on:`). Stacked #181 to v těle PR zmiňuje.

## Release

- `master` jen PR + review
- Normální PR: **jeden** label `semver:major|minor|patch|none`
- Verzi v `pyproject.toml` **nenadouvaj** v feature PR (release-please)
- [RELEASE_POLICY.md](../../../RELEASE_POLICY.md), [VERSIONING.md](../../../VERSIONING.md)
- Skill: `.cursor/skills/pr-semver-label/SKILL.md`

## In-flight CI

[#162](../inflight/pr-162-dependabot.md) bump `actions/upload-artifact` 6→7 v `build.yml`, `tests.yml`, `security.yml`. Runtime Python beze změny.
