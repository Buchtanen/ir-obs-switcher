# Testování automatického verzování

## Ruční test skriptu

```powershell
# Test PATCH bump
python scripts\bump_version.py "fix: test oprava"

# Test MINOR bump  
python scripts\bump_version.py "feat: test nova funkce"

# Test MAJOR bump
python scripts\bump_version.py "rel: test major release"

# Test bez prefixu (nemělo by nic změnit)
python scripts\bump_version.py "test bez prefixu"
```

## Instalace hooku

```powershell
.\scripts\install_hooks.ps1
```

## Test hooku

Po instalaci hooku:

```powershell
# Vytvořit test commit s prefixem
git add .
git commit -m "fix: test automatickeho verzovani"

# Mělo by se zvýšit z 0.3.0 na 0.3.1
# A soubory by měly být automaticky přidány do staging area
```

## Kontrola

Po commitu zkontrolujte:

1. **Verze v souborech**:
   ```powershell
   # Zkontrolovat __init__.py
   Select-String -Path "src\irswitch\__init__.py" -Pattern "__version__"
   
   # Zkontrolovat pyproject.toml
   Select-String -Path "pyproject.toml" -Pattern "^version"
   ```

2. **Git status**:
   ```powershell
   git status
   # Soubory by měly být v staging area
   ```

3. **Dashboard**:
   - Otevřít `http://127.0.0.1:17321/gr-status`
   - Verze by měla být vidět v hlavičce

## Řešení problémů

### Hook není nainstalován
```powershell
# Zkontrolovat existenci hooku
Test-Path .git\hooks\commit-msg

# Pokud neexistuje, nainstalovat
.\scripts\install_hooks.ps1
```

### Hook nefunguje
```powershell
# Zkontrolovat obsah hooku
Get-Content .git\hooks\commit-msg

# Měl by obsahovat volání PowerShell skriptu
```

### Verze se neaktualizuje
1. Zkontrolovat, zda commit message začíná správným prefixem (`fix:`, `feat:`, `rel:`)
2. Zkontrolovat výstup hooku při commitu
3. Ručně otestovat `bump_version.py` skript
4. Zkontrolovat, zda jsou soubory zapisovatelné

### Verze se aktualizuje, ale není v dashboardu
1. Restartovat aplikaci (verze se načítá při startu)
2. Zkontrolovat, zda aplikace čte správný soubor (`src/irswitch/__init__.py`)
3. Zkontrolovat cache prohlížeče (hard refresh: Ctrl+F5)
