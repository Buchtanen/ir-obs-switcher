# GitHub Releases - Návod

## Co jsou GitHub Releases?

GitHub Releases jsou oficiální oznámení o nových verzích vašeho projektu. Umožňují:

- **Oznámení nových verzí** - uživatelé vidí, co je nového
- **Stahování binárek** - EXE soubory, ZIP archivy, atd.
- **Git tagy** - označení konkrétního commitu jako release
- **Release notes** - automaticky z CHANGELOG.md nebo ručně napsané

## Jak vytvořit Release

### Automaticky (doporučeno)

Projekt má automatický workflow (`.github/workflows/release.yml`), který se spustí při push tagu.

#### Varianta A: Ruční vytvoření tagu

1. **Zkontroluj verzi** v `pyproject.toml` (single source of truth)
2. **Aktualizuj CHANGELOG.md** - přesuň obsah z `[Unreleased]` do sekce s novou verzí
3. **Vytvoř a pushni tag**:
   ```bash
   git tag -a v0.7.0 -m "Release version 0.7.0"
   git push origin v0.7.0
   ```

#### Varianta B: Automatické vytvoření tagu (volitelné)

Po úspěšném CI na main/master můžeš použít workflow `create-release-tag.yml`:

1. **Zkontroluj verzi** v `pyproject.toml`
2. **Aktualizuj CHANGELOG.md**
3. **Pushni změny** a počkej na úspěšný CI
4. **Spusť workflow** `Create Release Tag` z GitHub Actions UI
   - Nebo se spustí automaticky po úspěšném CI (pokud je aktivní)

Workflow automaticky:
- Vytvoří tag z aktuální verze v `pyproject.toml`
- Pushne tag → spustí release workflow
- Vytvoří EXE build
- Vytvoří ZIP archiv s distribucí
- Extrahuje release notes z CHANGELOG.md
- Vytvoří GitHub Release s binárkami

### Ručně (přes GitHub UI)

1. Jdi na **Releases** → **Draft a new release**
2. Vyber nebo vytvoř tag (např. `v0.3.0`)
3. Vyplň **Release title** (např. "Release 0.3.0")
4. Vyplň **Description** (můžeš zkopírovat z CHANGELOG.md)
5. Přilož binárky (ZIP archiv)
6. Klikni **Publish release**

## Workflow proces

### 1. Příprava release

```bash
# Zkontroluj aktuální verzi
python -c "import irswitch; print(irswitch.__version__)"

# Aktualizuj CHANGELOG.md - přesuň [Unreleased] do nové sekce
# Např. z:
## [Unreleased]
# do:
## [0.3.0] - 2026-01-25
```

### 2. Commit změn

```bash
git add CHANGELOG.md
git commit -m "chore: prepare release 0.3.0"
git push
```

### 3. Vytvoření tagu a release

**Ruční způsob:**
```bash
# Vytvoř tag
git tag -a v0.7.0 -m "Release version 0.7.0"

# Pushni tag (spustí automatický release workflow)
git push origin v0.7.0
```

**Automatický způsob (volitelné):**
- Po úspěšném CI jdi na GitHub Actions
- Spusť workflow "Create Release Tag"
- Workflow automaticky vytvoří tag z aktuální verze
- Tag se pushne → spustí release workflow

### 4. Ověření

- Jdi na GitHub → **Releases**
- Měl by se vytvořit nový release s binárkami
- Release notes by měly být z CHANGELOG.md

## Formát tagů

Používej formát: `v<version>` (např. `v0.3.0`, `v1.0.0`)

- Workflow automaticky odstraní `v` prefix pro verzi
- Tag musí začínat na `v`, aby se workflow spustil

## Release notes

Workflow automaticky extrahuje release notes z `CHANGELOG.md`:

- Hledá sekci `## [0.3.0]` pro danou verzi
- Pokud nenajde, použije default zprávu
- Release notes se zobrazí v GitHub Release

### Příklad CHANGELOG.md

```markdown
## [0.3.0] - 2026-01-25

### Přidáno
- Nová funkce X
- Vylepšení Y

### Opraveno
- Bug fix Z

## [Unreleased]
...
```

## Distribuce

Každý release obsahuje:

- `irswitch-v<VERSION>-windows.zip` - ZIP archiv s:
  - `irswitchd.exe` - hlavní aplikace
  - `config/` - konfigurační soubory
  - `README.txt` - instrukce pro uživatele
  - `BUILD_INFO.txt` - informace o buildu

## Best practices

1. **Vždy aktualizuj CHANGELOG.md** před vytvořením release
2. **Používej semantic versioning** (MAJOR.MINOR.PATCH)
3. **Taguj až po úspěšných testech** na main/master větvi
4. **Release notes by měly být uživatelsky přívětivé** - popis změn, ne technické detaily
5. **Testuj build lokálně** před vytvořením tagu

## Troubleshooting

### Workflow se nespustil

- Zkontroluj, že tag začíná na `v` (např. `v0.3.0`, ne `0.3.0`)
- Zkontroluj, že tag byl pushnut: `git push origin v0.3.0`

### Chybí release notes

- Zkontroluj, že v CHANGELOG.md existuje sekce pro danou verzi
- Formát musí být: `## [0.3.0]` (s hranatými závorkami)

### Build selhal

- Zkontroluj GitHub Actions logy
- Ověř, že všechny závislosti jsou v `pyproject.toml`
- Zkontroluj, že `build_exe.ps1` funguje lokálně

## Integrace s verzováním

Projekt používá automatické verzování přes Git hooky:

- `fix:` → PATCH bump (0.3.0 → 0.3.1)
- `feat:` → MINOR bump (0.3.0 → 0.4.0)
- `rel:` → MAJOR bump (0.3.0 → 1.0.0)

Po automatickém zvýšení verze:

1. Aktualizuj CHANGELOG.md
2. Commit a push
3. Vytvoř tag a pushni (spustí release workflow)

## Příklady

### Minor release (0.3.0 → 0.4.0)

```bash
# 1. Připrav změny
git commit -m "feat: přidána nová funkce"  # Automaticky zvýší na 0.4.0

# 2. Aktualizuj CHANGELOG.md
# 3. Commit CHANGELOG
git add CHANGELOG.md
git commit -m "chore: update changelog for 0.4.0"

# 4. Push a vytvoř tag
git push
git tag -a v0.4.0 -m "Release version 0.4.0"
git push origin v0.4.0
```

### Patch release (0.3.0 → 0.3.1)

```bash
# 1. Oprava bugu
git commit -m "fix: oprava bugu v API"  # Automaticky zvýší na 0.3.1

# 2. Aktualizuj CHANGELOG.md
# 3. Commit a push
git add CHANGELOG.md
git commit -m "chore: update changelog for 0.3.1"
git push

# 4. Vytvoř tag
git tag -a v0.3.1 -m "Release version 0.3.1"
git push origin v0.3.1
```
