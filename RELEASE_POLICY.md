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

- Release PR **nevytváříš ručně** (první krok po merge `semver:*` je počkat na workflow **Release Please**).
- V Release PR se **vždy** mění:
  - `pyproject.toml` (`project.version`)
  - `CHANGELOG.md`
  - `.release-please-manifest.json` (`"."` = stejná verze jako `pyproject.toml`)
- Když Release PR mergneš:
  - vznikne tag `vX.Y.Z` (jen pokud pyproject == manifest; jinak workflow tag **neudělá**)
  - proběhne build distribuce a vytvoří se GitHub Release s artefakty

### Repo setting (povinné pro Actions)

Release Please běží s výchozím `GITHUB_TOKEN`. Ten **nesmí vytvářet ani schvalovat PR**, dokud admin v repo settings nezapne:

**Settings → Actions → General → Workflow permissions →**  
**Allow GitHub Actions to create and approve pull requests** = ON

Toto **nelze opravit jen commitem** — bez tohoto checkboxu workflow selže s chybou typu:

```text
GitHub Actions is not permitted to create or approve pull requests.
```

### Symptom: orphan Release Please větev

Když Actions smí pushnout větev, ale **nesmí vytvořit PR**, typicky vznikne (nebo zůstane) větev ve stylu:

`release-please--branches--master--components--irswitch`

…ale **žádný open Release PR** (label `autorelease: pending`). To je symptom chybějícího permissions checkboxu výše (ne „rozbitého“ release-please configu).

### Recovery po burst mergeích / failed Release Please

1. Ověř, že je zapnuté **Allow GitHub Actions to create and approve pull requests**.
2. Po sérii rychlých merge do `master` (nebo po failed runu) **re-run** workflow **Release Please** na aktuálním `master` (Actions → Release Please → Re-run), nebo pushni prázdný/no-op commit jen pokud re-run nestačí.
3. Ověř výsledek: existuje open Release PR s labelem `autorelease: pending`.
4. Pokud zůstala orphan větev bez PR a po permissions + re-run pořád nic: smaž orphan větev `release-please--branches--…` a znovu spusť Release Please (vytvoří větev + PR znovu).

Workflow má `concurrency` group `release-please-master` (`cancel-in-progress: false`), aby paralelní runy po burst mergeích nesoupeřily o stejný ref.

## Tagy a verze

- Tagy jsou ve formátu **`vX.Y.Z`**.
- Runtime verze aplikace je v `pyproject.toml`.
- **Poslední vydaná verze pro Release Please** je `.release-please-manifest.json` `"."`.
- Tyto tři hodnoty musí být stejné `X.Y.Z`: `pyproject.toml` ↔ manifest `"."` ↔ tag `vX.Y.Z`.
- CI (`scripts/check_release_please_lock.py` + job `version-lock`) to hlídá. Běžný PR **nesmí** změnit `project.version` (výjimka: `autorelease: pending`).
- Aplikace čte verzi primárně z **package metadata** (instalace) a fallback pro distribuci je `BUILD_INFO.txt`.

### Symptom: po merge `semver:minor` nevznikne Release PR

Nejčastěji je manifest **pozadu** za `pyproject.toml` nebo za tagem (historicky 1.1.0 vs 1.2.0).

1. Ověř triad výše.
2. Pokud manifest zaostává: PR `chore/sync-release-please-manifest` (`semver:none`) — **jen** manifest nastav na verzi z pyproject/tagu. `pyproject.toml` neměň, netaguj.
3. Po merge **re-run** workflow **Release Please**.
4. Orphan větev `release-please--branches--…` bez PR: smaž a re-run (viz výše).
5. Ruční Release PR (poslední možnost): bump **pyproject + manifest + CHANGELOG** na stejnou další verzi. **Netaguj první.**

## Co nedělat

- **Netaguj ručně** (tagy dělá release systém přes Release PR).
- **Nebumpuj verzi v běžných PR** (verze se bumpuje v Release PR).
- **Nebumpuj `pyproject.toml` bez manifestu** — Release Please pak další Release PR neotevře.
- **Nesnaž se “vynutit release” prefixy v atomic commitech** – releasování je PR-driven.

