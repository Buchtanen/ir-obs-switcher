# Správa verzí aplikace

Aplikace používá [Semantic Versioning](https://semver.org/lang/cs/) ve formátu `major.minor.patch` (např. `0.3.0`).

## Kde je verze evidována

Verze aplikace je evidována na třech místech:

1. **`src/irswitch/__init__.py`**
   ```python
   __version__ = "0.3.0"
   ```
   - Primární zdroj verze pro Python kód
   - Importovatelné jako `from irswitch import __version__`

2. **`pyproject.toml`**
   ```toml
   [project]
   version = "0.3.0"
   ```
   - Verze pro Python balíček
   - Používá se při buildu a distribuci

3. **`CHANGELOG.md`**
   - Verze v hlavičce sekcí (např. `## [0.3.0] - 2026-01-24`)
   - Historický záznam změn

## Zobrazení verze

Verze se zobrazuje na následujících místech:

1. **GR Dashboard** (`/gr-status`)
   - V hlavičce: "iRacing OBS Switcher **v0.3.0**"
   - Menší šedý text vedle názvu aplikace

2. **API Response** (`GET /status`)
   ```json
   {
     "version": "0.3.0",
     ...
   }
   ```

3. **Health Check** (`GET /health`)
   ```json
   {
     "status": "healthy",
     "version": "0.3.0",
     ...
   }
   ```

## Automatické verzování (Git Hooky)

Aplikace má automatický mechanismus pro správu verzí pomocí dvou Git hooků:
- **prepare-commit-msg** - běží před vytvořením commitu
- **post-commit** - běží po vytvoření commitu

### Proč dva hooky?

Git commit je atomická operace - jakmile začne, nelze změnit staging area.
Proto používáme dvoufázový přístup:

1. **prepare-commit-msg**: Uloží hashe verzí souborů PŘED commitem
2. **post-commit**: Porovná hashe, pokud se liší, provede `git commit --amend`

### Instalace hooků

**Windows (PowerShell)**:
```powershell
.\scripts\install_hooks.ps1
```

**Linux/Mac/Git Bash**:
```bash
chmod +x scripts/install_hooks.sh
./scripts/install_hooks.sh
```

### Použití

Po instalaci hooků se verze automaticky zvýší podle prefixu commit message:

- **`fix:`** → zvýší **PATCH** (0.3.0 → 0.3.1)
  ```bash
  git commit -m "fix: oprava bugu v API"
  ```

- **`feat:`** → zvýší **MINOR** (0.3.0 → 0.4.0)
  ```bash
  git commit -m "feat: přidána nová funkce lokalizace"
  ```

- **`rel:`** → zvýší **MAJOR** (0.3.0 → 1.0.0)
  ```bash
  git commit -m "rel: major release s breaking changes"
  ```

Workflow:
1. prepare-commit-msg detekuje prefix a zvýší verzi
2. Commit se vytvoří (bez verzí)
3. post-commit detekuje změnu a provede amend
4. Výsledek: Jeden commit včetně změn verzí

**Poznámka**: Pokud commit message nezačíná žádným z těchto prefixů, verze se nezmění. Hooky se také nespouští při merge, squash nebo template commitech.

### Ruční změna verze

Pokud potřebujete změnit verzi ručně (bez commitu nebo s jiným prefixem):

**`src/irswitch/__init__.py`**:
```python
__version__ = "0.4.0"  # Nová verze
```

**`pyproject.toml`**:
```toml
[project]
version = "0.4.0"  # Nová verze
```

### Aktualizace CHANGELOG.md

Po automatickém zvýšení verze je potřeba ručně aktualizovat `CHANGELOG.md`:

Přesuň obsah z `[Unreleased]` do nové sekce s verzí:

```markdown
## [0.4.0] - 2026-01-25

### Přidáno
- Nové funkce...

### Změněno
- Změny...

### Opraveno
- Opravy...

## [Unreleased]

### Přidáno
- Nové funkce ve vývoji...
```

### Git tag (volitelné)

Pro označení release v gitu:

```bash
git tag -a v0.4.0 -m "Release version 0.4.0"
git push origin v0.4.0
```

## Semantic Versioning

Formát: `MAJOR.MINOR.PATCH`

- **MAJOR** (1.0.0) - nekompatibilní změny API, breaking changes
- **MINOR** (0.2.0) - nové funkce zpětně kompatibilní
- **PATCH** (0.1.1) - opravy bugů zpětně kompatibilní

### Příklady

- `0.1.0` → `0.1.1` - oprava bugu
- `0.1.1` → `0.2.0` - přidání nové funkce
- `0.2.0` → `1.0.0` - breaking change, stabilní release

## Aktuální verze

**Aktuální verze**: `0.3.0` (leden 2026)

**Poslední změna**: Přidána lokalizace (i18n) a YouTube API integrace

**Další plánovaná verze**: `0.4.0` (nebo vyšší podle vývoje)
