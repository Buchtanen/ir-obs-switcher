# Instrukce pro dokončení čištění repozitáře

## ✅ Co už bylo provedeno

1. **Aktualizován `.gitignore`**
   - Přidáno `.cursor/` (s výjimkou `.cursorignore` a `.cursorrules`)
   - Všechny potřebné položky jsou v `.gitignore`

2. **Lokální čištění**
   - ✅ `config/config.ini` smazán (obsahoval `password = TEST123`)
   - ✅ `build/`, `.venv/`, `docs/` smazány
   - ⚠️ Částečně: `.cursor/skills/`, `dist/`, `.vscode/` (některé soubory byly zamčené)

3. **Vytvořené soubory**
   - `scripts/clean_repo_local.ps1` - lokální čištění
   - `scripts/clean_repo.ps1` - vyčištění historie gitu
   - `CLEAN_REPO_STRATEGY.md` - detailní strategie
   - `REPO_CLEANUP_SUMMARY.md` - shrnutí

## ⚠️ Co zbývá udělat

### 1. Zavřít IDE a git procesy
Zavři Cursor/VS Code a všechny procesy, které mohou používat git (aby se odemkl git index).

### 2. Odstranit `.cursor/skills/` z gitu

```powershell
cd "c:\Users\richa\Projekty\obs-switcher\richa"
git rm -r --cached .cursor/skills/
git commit -m "chore: Remove .cursor/skills/ directory from git tracking"
```

### 2b. Odstranit log soubory z gitu (DŮLEŽITÉ - mohou obsahovat tokeny!)

```powershell
git rm --cached logs/irswitch.log.1 logs/irswitch.log.2
git commit -m "chore: Remove log files from git tracking"
```

### 3. Commitnout změny v `.gitignore`

```powershell
git add .gitignore
git commit -m "chore: Update .gitignore to exclude .cursor/ directory"
```

### 4. (Volitelné) Commitnout nové soubory dokumentace

```powershell
git add CLEAN_REPO_STRATEGY.md REPO_CLEANUP_SUMMARY.md scripts/clean_repo*.ps1
git commit -m "docs: Add repository cleanup documentation and scripts"
```

### 5. Pushnout na GitHub

```powershell
git push origin master
```

## 🔍 Ověření po dokončení

```powershell
# Zkontroluj, že žádné nechtěné soubory nejsou v gitu
git ls-files | Select-String -Pattern "\.cursor/skills|config\.ini|^docs/|^dist/|^build/|^\.vscode/|^\.venv/|pytest_cache"

# Mělo by vrátit prázdný výsledek (nebo jen .cursorignore a .cursorrules)
```

## 📝 Poznámky

- `.cursorignore` a `.cursorrules` zůstávají v gitu (jsou konfigurační soubory projektu)
- `config.ini` není v gitu, pouze lokálně (je v `.gitignore`)
- Všechny secrets jsou pouze v lokálním `config.ini`, který už byl smazán
- `.venv/` nepatří do gitu - každý vývojář si ho vytvoří lokálně pomocí `python -m venv .venv`

## 🚀 Volitelné: Úplné vyčištění historie

Pokud chceš úplně odstranit `.cursor/skills/` z historie gitu (přepíše historii):

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

---

**Všechny potřebné soubory a dokumentace jsou připravené. Stačí dokončit git commity a push.**
