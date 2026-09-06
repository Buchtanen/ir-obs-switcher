# PR #162 — Dependabot `actions/upload-artifact` 6 → 7

- URL: https://github.com/Buchtanen/ir-obs-switcher/pull/162
- Větev: `dependabot/github_actions/actions/upload-artifact-7`
- Base: `master`
- Label: `semver:none` + `dependencies` + `github-actions`

Mění jen GitHub Actions (`build.yml`, `tests.yml`, `security.yml`). **Žádný Python runtime, žádné INI, žádné overlay.**

v7: breaking pro GitHub Action API (ESM, optional direct upload). Pro irswitch jde o bump používané akce, ne o kód služby.

Při dokumentaci CI zmiň aktuální major podle **sloučeného** workflow. Dokud PR visí, master může být ještě na v6.
