# CI/CD Doporučení a Optimalizace

## Aktuální stav

### Co běží:
- ✅ **Tests** - pytest na 3 Python verzích (3.11, 3.12, 3.13)
- ⚠️ **Black formatting** - volitelný check (`|| true` - neblokuje)
- ⚠️ **Security checks** - Safety a Bandit (`continue-on-error: true` - neblokují)
- ✅ **CodeQL** - security analysis (blokující)
- ✅ **Build** - automatický build po testech na main/master

### Problémy:
1. **Žádný blokující linting** - black je volitelný
2. **Žádný type checking** - mypy chybí
3. **Security checks neblokují** - continue-on-error: true
4. **Žádné coverage reporty** - nevíme, jak dobře jsou testy pokryté
5. **Žádné caching** - pomalé instalace dependencies
6. **Neoptimalizované joby** - některé by mohly běžet paralelně

---

## Doporučený komplexní CI/CD pipeline

### Architektura

```
┌─────────────────────────────────────────────────────────┐
│                    CI Pipeline                          │
│              (push/PR na main/master)                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Linting    │  │ Type Check   │  │   Security   │ │
│  │  (ruff)      │  │  (mypy)      │  │ (bandit,     │ │
│  │              │  │              │  │  safety)     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│         │                 │                 │          │
│         └─────────────────┴─────────────────┘          │
│                        │                               │
│                 ┌──────▼──────┐                       │
│                 │    Tests    │                       │
│                 │  (pytest +  │                       │
│                 │  coverage)  │                       │
│                 └──────┬──────┘                       │
│                        │                               │
│                 ┌──────▼──────┐                       │
│                 │ Build Verify │                       │
│                 │ (jen ověření)│                       │
│                 └─────────────┘                       │
│                                                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              Release Pipeline                           │
│            (push tag v* na main/master)                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐                                      │
│  │    Build     │                                      │
│  │  (EXE + ZIP) │                                      │
│  └──────┬───────┘                                      │
│         │                                              │
│  ┌──────▼───────┐                                      │
│  │   Release    │                                      │
│  │ (GitHub       │                                      │
│  │  Release +    │                                      │
│  │  Artifacts)    │                                      │
│  └──────────────┘                                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Fáze pipeline

#### CI Pipeline (push/PR)
1. **Quick Checks** (paralelně, rychlé)
   - Linting (ruff)
   - Formatting (black/ruff format)
   - Type checking (mypy)

2. **Security** (paralelně)
   - Bandit (code security)
   - Safety (dependency vulnerabilities)

3. **Tests** (po quick checks)
   - Unit tests s coverage
   - Matrix: Python 3.11, 3.12, 3.13

4. **Build Verification** (po testech, jen main/master)
   - Ověření, že build funguje
   - **NENÍ upload artifact** - to je v release workflow

#### Release Pipeline (push tag)
1. **Build** (reusable workflow)
   - Build EXE
   - Vytvoření ZIP archivu
   - Upload artifact

2. **Release** (po buildu)
   - Extrakce changelog
   - Vytvoření GitHub Release
   - Připojení binárek

---

## Implementace

### 1. Přidat do `pyproject.toml`

```toml
[project.optional-dependencies]
test = [
  "pytest>=7.4",
  "pytest-asyncio>=0.23",
  "pytest-cov>=4.1",  # Coverage
  "freezegun>=1.4",
]
lint = [
  "ruff>=0.1.0",      # Linter (rychlejší než flake8)
  "black>=23.0",      # Formatter
  "mypy>=1.5",        # Type checker
]
security = [
  "bandit[toml]>=1.7",
  "safety>=2.3",
]

[tool.ruff]
line-length = 100
target-version = "py311"
select = [
  "E",   # pycodestyle errors
  "W",   # pycodestyle warnings
  "F",   # pyflakes
  "I",   # isort
  "B",   # flake8-bugbear
  "C4",  # flake8-comprehensions
  "UP",  # pyupgrade
]
ignore = [
  "E501",  # line too long (black handles this)
  "B008",  # function calls in argument defaults
]

[tool.ruff.per-file-ignores]
"tests/*" = ["E501", "S101"]  # Allow longer lines in tests

[tool.black]
line-length = 100
target-version = ["py311"]
include = '\.pyi?$'

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false  # Postupně přidávat
disallow_incomplete_defs = false
check_untyped_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
strict_optional = true

[[tool.mypy.overrides]]
module = [
  "pyirsdk.*",
  "obsws.*",
  "pynput.*",
]
ignore_missing_imports = true

[tool.bandit]
exclude_dirs = ["tests", ".git", "build", "dist"]
skips = ["B101"]  # assert_used - pytest používá assert

[tool.coverage.run]
source = ["src"]
omit = ["tests/*", "*/__pycache__/*"]

[tool.coverage.report]
exclude_lines = [
  "pragma: no cover",
  "def __repr__",
  "raise AssertionError",
  "raise NotImplementedError",
  "if __name__ == .__main__.:",
  "if TYPE_CHECKING:",
]
```

### 2. Nový workflow: `ci.yml`

Kompletní CI pipeline s optimalizacemi.

### 3. Optimalizace

#### Caching
- **pip cache** - urychlí instalace
- **Python setup cache** - GitHub Actions cache

#### Paralelní joby
- Linting, type checking, security - všechny paralelně
- Tests až po úspěšných quick checks

#### Conditional runs
- Build verification jen na main/master (jen ověření, ne upload)
- Skutečný build + release jen při push tagu (release.yml)
- Security checks jen na PR a scheduled

#### Matrix optimalizace
- Tests: Python 3.11, 3.12, 3.13
- Quick checks: jen Python 3.11 (rychlejší)

---

## Výhody nového přístupu

### Rychlost
- **Paralelní joby** - linting, type checking, security běží současně
- **Caching** - pip cache, Python setup
- **Fail fast** - quick checks selžou rychle, tests až po nich

### Kvalita kódu
- **Blokující linting** - žádný špatně formátovaný kód
- **Type safety** - mypy zachytí type errors
- **Security** - bandit a safety blokují nebezpečný kód

### Viditelnost
- **Coverage reporty** - víme, jak dobře jsou testy pokryté
- **Artifacts** - coverage HTML, security reporty

### Údržba
- **Centralizovaná konfigurace** - vše v `pyproject.toml`
- **Reusable workflows** - build-distribution.yml už existuje
- **Konzistentní nástroje** - ruff místo flake8 (rychlejší)

---

## Migrační plán

### Fáze 1: Přidat konfiguraci (neblokující)
1. Přidat `[tool.ruff]`, `[tool.mypy]`, `[tool.coverage]` do `pyproject.toml`
2. Přidat optional dependencies
3. Testovat lokálně

### Fáze 2: Nový CI workflow (paralelně se starým)
1. Vytvořit `ci.yml` s novými checky
2. Spustit paralelně se `tests.yml`
3. Ověřit, že vše funguje

### Fáze 3: Aktivace blokujících checků
1. Odstranit `|| true` a `continue-on-error: true`
2. Opravit existující problémy
3. Merge do main

### Fáze 4: Optimalizace
1. Přidat caching
2. Optimalizovat matrix strategy
3. Zkontrolovat dobu běhu

### Fáze 5: Cleanup
1. Odstranit starý `tests.yml` (nebo sloučit)
2. Aktualizovat dokumentaci
3. Nastavit branch protection rules

---

## Branch Protection Rules

Doporučené nastavení pro `main`/`master`:

- ✅ Require pull request reviews (1 approval)
- ✅ Require status checks to pass
  - `lint` (ruff)
  - `format` (black)
  - `type-check` (mypy)
  - `security-bandit`
  - `security-safety`
  - `test (3.11)`
  - `test (3.12)`
  - `test (3.13)`
- ✅ Require branches to be up to date
- ✅ Do not allow bypassing (kromě adminů)

---

## Nástroje - srovnání

### Linting
- **Ruff** ✅ (doporučeno)
  - Rychlý (Rust-based)
  - Podporuje isort, pyupgrade
  - Kompatibilní s black
- **Flake8** ❌
  - Pomalý
  - Starší
- **Pylint** ❌
  - Příliš striktní pro tento projekt
  - Pomalý

### Type Checking
- **mypy** ✅ (doporučeno)
  - Standardní nástroj
  - Dobrá podpora pro async
  - Postupné přidávání strict mode

### Formatting
- **Black** ✅ (doporučeno)
  - Už používaný
  - Ruff format je alternativa (rychlejší)
- **Ruff format** ⚠️
  - Rychlejší než black
  - Kompatibilní s black
  - Novější (méně osvědčený)

### Security
- **Bandit** ✅ (doporučeno)
  - Už používaný
  - Dobré pro Python
- **Safety** ✅ (doporučeno)
  - Už používaný
  - Dependency vulnerabilities

---

## Odhadované časy běhu

### Aktuální (tests.yml)
- Tests (3 Python verze): ~5-8 minut
- Build: ~3-5 minut
- **Celkem: ~8-13 minut**

### Nový CI (ci.yml)
- Quick checks (paralelně): ~2-3 minuty
- Security (paralelně): ~1-2 minuty
- Tests (3 Python verze): ~5-8 minut
- Build verification: ~2-3 minuty
- **Celkem: ~6-10 minut** (díky paralelizaci)

### Release (release.yml) - při push tagu
- Build: ~3-5 minut
- Release creation: ~30 sekund
- **Celkem: ~4-6 minut**

---

## Další doporučení

### 1. Pre-commit hooks (lokální)
- Ruff linting
- Black formatting
- mypy type checking
- Bandit security

### 2. Coverage threshold
- Minimálně 70% coverage
- Blokovat PR s poklesem coverage

### 3. Dependabot
- Automatické PR pro dependency updates
- Testovat automaticky v CI

### 4. Release automation
- Automatické release notes z CHANGELOG.md
- Semantic versioning enforcement

---

## Shrnutí

### Co přidat:
1. ✅ **Ruff** - linting (rychlejší než flake8)
2. ✅ **mypy** - type checking
3. ✅ **pytest-cov** - coverage reporty
4. ✅ **Blokující security checks** - bandit, safety
5. ✅ **Caching** - pip, Python setup
6. ✅ **Paralelní joby** - rychlejší pipeline

### Co optimalizovat:
1. ✅ **Matrix strategy** - quick checks jen na 3.11
2. ✅ **Conditional runs** - build jen na main
3. ✅ **Fail fast** - quick checks před testy

### Co zachovat:
1. ✅ **CodeQL** - security analysis
2. ✅ **Tests na 3 verzích** - kompatibilita
3. ✅ **Release workflow** - build + release při push tagu
4. ✅ **Build workflow** - reusable pro release

### Workflow rozdělení:
- **CI (ci.yml)**: Verifikace kódu (lint, format, type-check, security, tests, build-verify)
- **Release (release.yml)**: Skutečný build + GitHub Release (spouští se při push tagu)
