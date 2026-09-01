# Správa verzí aplikace

Aplikace používá [Semantic Versioning](https://semver.org/lang/cs/) ve formátu `MAJOR.MINOR.PATCH` (např. `0.7.0`).

**Primární proces vydávání** je **Release PR model** (release-please). Detaily a PR pravidla: **[RELEASE_POLICY.md](RELEASE_POLICY.md)**.

Tento dokument popisuje, **kde žije verze** a jak se **zobrazuje** v aplikaci. Neslouží jako návod na ruční tagování ani commit-hook bump.

---

## Kde je verze evidována

1. **`pyproject.toml`** (runtime / build)
   ```toml
   [project]
   version = "0.7.0"
   ```
   - Bump probíhá v **Release PR**, ne v běžných feature/fix PR.
   - Používá se při buildu a distribuci.

2. **`.release-please-manifest.json`** (poslední vydaná verze pro Release Please)
   ```json
   { ".": "0.7.0" }
   ```
   - Musí být **stejné** `X.Y.Z` jako `pyproject.toml` a tag `vX.Y.Z`.
   - Když zaostane, Release Please další Release PR **neotevře**.
   - CI: `scripts/check_release_please_lock.py`.

3. **`src/irswitch/__init__.py`**
   - Načítá verzi dynamicky (`resolve_version()`).
   - **Není potřeba ručně aktualizovat.**

4. **`CHANGELOG.md`**
   - Sekce podle verzí (např. `## [0.7.0] - …`).
   - Aktualizuje se v Release PR spolu s `pyproject.toml` a manifestem.

5. **Git tag `vX.Y.Z`**
   - Vzniká **až po merge Release PR** (ne ručně).
   - Spouští release pipeline (build + GitHub Release).
   - Workflow tag **neudělá**, pokud pyproject != manifest.

---

## Jak se verze zvyšuje (Release PR)

Shrnutí z [RELEASE_POLICY.md](RELEASE_POLICY.md):

1. Běžné PR do `master` mají **přesně jeden** label: `semver:major` / `semver:minor` / `semver:patch` / `semver:none`.
2. Merge do `master` aktualizuje (nebo vytvoří) **Release PR**, který akumuluje změny od posledního tagu.
3. Merge **Release PR** bumpne `pyproject.toml` + `CHANGELOG.md` + `.release-please-manifest.json`, vytvoří tag `vX.Y.Z` a spustí release.

### Co nedělat

- **Nebumpuj** `project.version` v běžných PR.
- **Nebumpuj** `pyproject.toml` bez `.release-please-manifest.json`.
- **Netaguj ručně** (`git tag v…`) jako primární release flow.
- **Nespoléhej** na commit-hook bump (`fix:` / `feat:` / `rel:`) — to už **není** řídící mechanismus releasu.

Když po merge `semver:*` nevznikne Release PR: viz [RELEASE_POLICY.md](RELEASE_POLICY.md) (sync manifestu, ne ruční bump pyproject). Skill: `release-please-manifest`.

> Historické skripty/hooky kolem version bumpu mohou v `scripts/` ještě existovat; pro releasování je nepoužívej. Zdroj pravdy je Release PR + [RELEASE_POLICY.md](RELEASE_POLICY.md).

---

## Zobrazení verze

Verze se zobrazuje např.:

1. **GR Dashboard** (`/gr-status`) – v hlavičce vedle názvu aplikace
2. **API** `GET /status` – pole `version`
3. **Health** `GET /health` – pole `version`

Runtime pořadí (`resolve_version()`):

1. **Frozen EXE** → `BUILD_INFO.txt`, pak package metadata
2. **Source checkout / editable install** (existuje `pyproject.toml` u kořene) → `project.version` z pyproject.toml — ignoruje zastaralé dist-info po release bumpu
3. **Nainstalovaný wheel** bez checkoutu → package metadata

---

## Semantic Versioning (význam)

| Část | Význam | Typický PR label |
|------|--------|------------------|
| **MAJOR** | breaking / nekompatibilní změna | `semver:major` |
| **MINOR** | nová funkce zpětně kompatibilní | `semver:minor` |
| **PATCH** | oprava / malá kompatibilní změna | `semver:patch` |
| — | bez release dopadu (docs, čistý refactor) | `semver:none` |

Příklady: `0.7.0` → `0.7.1` (patch), `0.7.1` → `0.8.0` (minor), `0.8.0` → `1.0.0` (major).

---

## Související docs

- [RELEASE_POLICY.md](RELEASE_POLICY.md) – Release PR model, labely, co nedělat
- [CHANGELOG.md](CHANGELOG.md) – historie změn
- [BUILD_AND_DEPLOY.md](BUILD_AND_DEPLOY.md) – build EXE / nasazení (artefakty z release pipeline)
