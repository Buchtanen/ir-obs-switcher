# Finální instrukce pro odstranění log souborů

## ⚠️ Nalezené log soubory v gitu

V gitu jsou následující log soubory, které mohou obsahovat tokeny/secrets:
- `logs/irswitch.log.1`
- `logs/irswitch.log.2`

## 🔧 Postup odstranění

### Krok 1: Zavřít IDE a git procesy
Zavři Cursor/VS Code a všechny procesy, které mohou používat git.

### Krok 2: Odstranit log soubory z gitu

```powershell
cd "c:\Users\richa\Projekty\obs-switcher\richa"
git rm --cached logs/irswitch.log.1 logs/irswitch.log.2
git commit -m "chore: Remove log files from git tracking"
```

### Krok 3: Commitnout ostatní změny

```powershell
git add .gitignore
git add CLEANUP_INSTRUCTIONS.md CLEAN_REPO_STRATEGY.md REPO_CLEANUP_SUMMARY.md LOG_CLEANUP.md CLEANUP_VERIFICATION.md FINAL_CLEANUP_INSTRUCTIONS.md scripts/clean_repo*.ps1
git commit -m "chore: Update .gitignore and add cleanup documentation"
```

### Krok 4: Pushnout na GitHub

```powershell
git push origin master
```

## 🚀 Volitelné: Úplné vyčištění historie

Pokud chceš úplně odstranit log soubory z historie gitu (přepíše historii):

1. **Zálohuj repozitář:**
   ```powershell
   git clone --mirror https://github.com/tvuj-username/obs-switcher.git backup-repo.git
   ```

2. **Spusť skript:**
   ```powershell
   .\scripts\clean_repo.ps1
   ```
   
   Tento skript nyní odstraní z historie:
   - `.cursor/skills/`
   - `config/config.ini`
   - `docs/`, `dist/`, `build/`, `.vscode/`, `.venv/`, `pytest_cache/`
   - **Všechny log soubory** (`*.log`, `*.log.*`, `logs/`)

3. **Force push:**
   ```powershell
   git push origin --force --all
   git push origin --force --tags
   ```

**DŮLEŽITÉ:** Informuj všechny spolupracovníky před force pushem!

## 🔍 Ověření

Po dokončení zkontroluj:
```powershell
# Zkontroluj, že žádné log soubory nejsou v gitu
git ls-files | Select-String -Pattern "\.log"

# Mělo by vrátit prázdný výsledek (nebo jen logs/.gitkeep)
```

## 📝 Poznámky

- Log soubory jsou už v `.gitignore` (řádky 47-49: `*.log`, `logs/*.log*`, `logs/*.log.*`)
- `logs/.gitkeep` zůstává v gitu (je to prázdný soubor pro zachování složky)
- Všechny log soubory budou ignorovány v budoucích commitech
