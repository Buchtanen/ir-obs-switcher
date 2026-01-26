# Release & PR policy (master)

Repo má **chráněnou větev `master`** (vše jen přes PR + review). Cílem je mít **atomic commity** pro vývoj, ale **releasy řídit na úrovni PR** a dělat je dávkově přes **Release PR**.

## Jak funguje vydávání (Release PR model)

- Každý merge do `master` spustí workflow, který **vytvoří nebo aktualizuje jeden “Release PR”**.
- Release PR **akumuluje změny od posledního tagu** a navrhne novou verzi.
- **Teprve merge Release PR vytvoří tag `vX.Y.Z`** a spustí release pipeline (build + GitHub Release).

### Důsledek
Atomic commity ani jejich prefixy **neřídí přímo releasování**. Release je řízený tím, **kdy mergneš Release PR**.

## PR požadavky (běžné PR do `master`)

### 1) SemVer label je povinný
Každý PR do `master` musí mít **přesně jeden** z těchto labelů:

- `semver:major` – breaking change
- `semver:minor` – nová feature bez breaku
- `semver:patch` – bugfix / malá změna kompatibilní zpětně
- `semver:none` – žádná release změna (docs, interní refactor bez dopadu)

> Výjimka: automaticky generovaný Release PR (má label `autorelease: pending`) semver label nepotřebuje.

### 2) PR title (doporučení)
Doporučený styl je conventional (kvůli čitelným release notes):

- `feat: ...` (typicky `semver:minor`)
- `fix: ...` (typicky `semver:patch`)
- `feat!: ...` / `fix!: ...` nebo text `BREAKING CHANGE` v popisu (typicky `semver:major`)
- `docs: ...`, `chore: ...`, `refactor: ...` (typicky `semver:none`)

Policy je: **label je rozhodující**, title je primárně pro lidskou čitelnost.

### 3) Breaking change pravidlo
Pokud dáš `semver:major`, PR musí mít jasně označený breaking change:
- buď `!` v title (např. `feat!: ...`)
- nebo řádek `BREAKING CHANGE:` v těle PR

## Release PR (automatický)

- Release PR **nevytváříš ručně**.
- V Release PR se mění:
  - `pyproject.toml` (`project.version`)
  - `CHANGELOG.md`
  - případně `.release-please-manifest.json`
- Když Release PR mergneš:
  - vznikne tag `vX.Y.Z`
  - proběhne build distribuce a vytvoří se GitHub Release s artefakty

## Tagy a verze

- Tagy jsou ve formátu **`vX.Y.Z`**.
- Verze aplikace je “single source of truth” v `pyproject.toml`.
- Aplikace čte verzi primárně z **package metadata** (instalace) a fallback pro distribuci je `BUILD_INFO.txt`.

## Co nedělat

- **Netaguj ručně** (tagy dělá release systém přes Release PR).
- **Nebumpuj verzi v běžných PR** (verze se bumpuje v Release PR).
- **Nesnaž se “vynutit release” prefixy v atomic commitech** – releasování je PR-driven.

