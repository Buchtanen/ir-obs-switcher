# Shrnutí čištění repozitáře

## ✅ Co bylo provedeno

### 1. Aktualizace .gitignore
- ✅ Přidáno `.cursor/` do `.gitignore` (s výjimkou `.cursorignore` a `.cursorrules`)
- ✅ Ověřeno, že všechny potřebné položky jsou v `.gitignore`:
  - `config/config.ini`
  - `dist/`, `build/`
  - `.vscode/`, `.venv/`
  - `pytest_cache/`
  - `docs/`

### 2. Vytvořené skripty
- ✅ `scripts/clean_repo_local.ps1` - lokální čištění
- ✅ `scripts/clean_repo.ps1` - vyčištění historie gitu
- ✅ `CLEAN_REPO_STRATEGY.md` - detailní strategie

### 3. Analýza hardcoded tokenů
- ✅ `config.ini` NENÍ v historii gitu (pouze lokálně)
- ✅ `config.example.ini` má placeholderované hodnoty (`your_password_here`, `your_client_id_here`)
- ✅ V dokumentaci jsou pouze příklady, žádné reálné tokeny

## ⚠️ Co je v gitu a musí se odstranit

### Soubory v gitu:
- ⚠️ `.cursor/skills/python-rules/SKILL.md` - je v gitu, musí se odstranit z historie
- ✅ `.cursorignore` a `.cursorrules` - zůstanou (jsou konfigurační soubory projektu)

### Lokální soubory k smazání:
- ⚠️ `config/config.ini` - obsahuje `password = TEST123` (lokální, není v gitu)

## 📋 Postup čištění

### Krok 1: Lokální čištění (SPUSTIT NYNÍ)
```powershell
.\scripts\clean_repo_local.ps1
```

Tento skript smaže:
- `config/config.ini`
- `.cursor/skills/` (zachová `.cursorignore` a `.cursorrules`)
- `dist/`, `build/`, `.vscode/`, `.venv/`, `pytest_cache/`, `docs/` (pokud existují)

### Krok 2: Odstranění z gitu (bez přepisování historie)
```powershell
git rm -r --cached .cursor/skills/
git commit -m "chore: Remove .cursor/skills/ directory from git tracking"
git push origin master
```

**Výhoda:** Rychlé, bez přepisování historie  
**Nevýhoda:** `.cursor/skills/` zůstane v historii, ale nebude v nových commitech

### Krok 3: Úplné vyčištění historie (VOLITELNÉ)
**POZOR: Toto přepíše historii gitu!**

1. **Zálohuj repozitář:**
   ```powershell
   git clone --mirror https://github.com/tvuj-username/obs-switcher.git backup-repo.git
   ```

2. **Spusť skript:**
   ```powershell
   .\scripts\clean_repo.ps1
   ```

3. **Force push:**
   ```powershell
   git push origin --force --all
   git push origin --force --tags
   ```

**DŮLEŽITÉ:** Informuj všechny spolupracovníky před force pushem!

## 🔍 Ověření

Po dokončení zkontroluj:

```powershell
# Zkontroluj, že žádné nechtěné soubory nejsou v gitu
git ls-files | Select-String -Pattern "\.cursor/skills|config\.ini|^docs/|^dist/|^build/|^\.vscode/|^\.venv/|pytest_cache"

# Ověř, že .gitignore funguje
git status

# Zkontroluj historii na secrets (pokud jsi použil git-filter-repo)
git log --all -p | Select-String -Pattern "password|token|secret|api_key" -CaseSensitive
```

## 📝 Poznámky

- `.cursorignore` a `.cursorrules` zůstávají v gitu (jsou konfigurační soubory)
- `config.ini` není v gitu, pouze lokálně (je v `.gitignore`)
- Všechny secrets jsou pouze v lokálním `config.ini`, který se smaže lokálním čištěním
