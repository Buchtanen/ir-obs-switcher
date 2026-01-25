# Odstranění log souborů z repozitáře

## ⚠️ Nalezené log soubory v gitu

V gitu byly nalezeny následující log soubory, které mohou obsahovat tokeny/secrets:
- `logs/irswitch.log.1`
- `logs/irswitch.log.2`

## 🔧 Co bylo provedeno

1. **Aktualizován skript `scripts/clean_repo.ps1`**
   - Přidáno odstranění všech log souborů z historie:
     - `*.log`
     - `*.log.*` (rotované logy)
     - `logs/` složka

2. **Odstranění z aktuálního commitu**
   ```powershell
   git rm --cached logs/*.log*
   ```

## 📋 Další kroky

### 1. Commitnout změny
```powershell
git commit -m "chore: Remove log files from git tracking"
```

### 2. Odstranit z historie (VOLITELNÉ - přepíše historii)
Pokud chceš úplně odstranit log soubory z historie:

```powershell
.\scripts\clean_repo.ps1
```

Tento skript nyní odstraní i všechny log soubory z historie.

### 3. Pushnout na GitHub
```powershell
git push origin master
```

## ✅ Ověření

Po dokončení zkontroluj:
```powershell
# Zkontroluj, že žádné log soubory nejsou v gitu
git ls-files | Select-String -Pattern "\.log"

# Mělo by vrátit prázdný výsledek
```

## 📝 Poznámky

- Log soubory jsou už v `.gitignore` (řádky 47-49)
- `logs/.gitkeep` zůstává v gitu (je to prázdný soubor pro zachování složky)
- Všechny log soubory budou ignorovány v budoucích commitech
