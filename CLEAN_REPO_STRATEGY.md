# Strategie čištění repozitáře

## Aktuální stav

### Co je v gitu a nemělo by být:
- ✅ `.cursor/skills/python-rules/SKILL.md` - je v gitu, musí se odstranit z historie
- ✅ `.cursorignore` a `.cursorrules` - tyto soubory můžou zůstat (jsou konfigurační)

### Co je OK:
- ✅ `config.ini` NENÍ v historii gitu (je pouze lokálně)
- ✅ `.gitignore` je správně nastavený
- ✅ `config.example.ini` má placeholderované hodnoty

### Co je lokálně a musí se smazat:
- ⚠️ `config/config.ini` - obsahuje `password = TEST123` (lokální soubor, není v gitu)

## Postup čištění

### Fáze 1: Lokální čištění ✅
Spusť skript pro lokální čištění:
```powershell
.\scripts\clean_repo_local.ps1
```

Tento skript:
- Smaže lokální `config/config.ini`
- Smaže lokální `.cursor/` složku
- Smaže další nechtěné složky (dist, build, .vscode, .venv, pytest_cache, docs)

### Fáze 2: Vyčištění historie gitu
**POZOR: Toto přepíše historii gitu!**

1. **Zálohuj repozitář:**
   ```powershell
   git clone --mirror https://github.com/tvuj-username/obs-switcher.git backup-repo.git
   ```

2. **Spusť skript pro vyčištění historie:**
   ```powershell
   .\scripts\clean_repo.ps1
   ```

   Tento skript použije `git-filter-repo` k odstranění:
   - `.cursor/skills/` z celé historie (zachová `.cursorignore` a `.cursorrules`)
   - `config/config.ini` z celé historie (pokud tam byl)
   - `docs/`, `dist/`, `build/`, `.vscode/`, `.venv/`, `pytest_cache/` z historie

3. **Ověř změny:**
   ```powershell
   git log --all --oneline
   git log --all --name-only | Select-String -Pattern "\.cursor|config\.ini"
   ```

### Fáze 3: Push na GitHub
**POZOR: Force push přepíše historii na GitHubu!**

```powershell
git push origin --force --all
git push origin --force --tags
```

**DŮLEŽITÉ:**
- Všechny spolupracovníci musí být informováni
- Musí si udělat nový clone nebo `git fetch --all && git reset --hard origin/master`
- Pokud někdo má lokální změny, musí je nejdřív commitnout nebo stashnout

### Fáze 4: Ověření
1. Zkontroluj, že žádné secrets nejsou v historii:
   ```powershell
   git log --all -p | Select-String -Pattern "password|token|secret|api_key" -CaseSensitive
   ```

2. Ověř, že `.gitignore` funguje:
   ```powershell
   git status
   # Mělo by ukázat, že config.ini a .cursor/ jsou ignorovány
   ```

3. Zkontroluj, že žádné nechtěné soubory nejsou v gitu:
   ```powershell
   git ls-files | Select-String -Pattern "\.cursor|config\.ini|^docs/|^dist/|^build/|^\.vscode/|^\.venv/|pytest_cache"
   ```

## Alternativní postup (bez přepisování historie)

Pokud nechceš přepisovat historii, můžeš:

1. **Odstranit soubory z aktuálního commitu:**
   ```powershell
   git rm -r --cached .cursor/skills/
   git commit -m "chore: Remove .cursor/skills/ directory from git tracking"
   ```

2. **Přidat do .gitignore** (už je tam)

3. **Pushnout normálně:**
   ```powershell
   git push origin master
   ```

**Nevýhoda:** Soubory zůstanou v historii, ale nebudou v nových commitech.

## Doporučení

Pro úplné vyčištění doporučuji použít **Fázi 2** (vyčištění historie), protože:
- Odstraní všechny secrets z historie (pokud tam byly)
- Odstraní všechny nechtěné soubory z historie
- Repozitář bude čistý

**Ale:** Ujisti se, že všichni spolupracovníci jsou informováni a souhlasí s přepisováním historie!
