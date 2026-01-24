# Scripts

Tento adresář obsahuje pomocné skripty pro správu projektu.

## Verzování

### `bump_version.py`

Python skript pro automatické zvýšení verze podle commit message prefixu.

**Použití**:
```bash
python scripts/bump_version.py "fix: oprava bugu"
```

**Prefixy**:
- `fix:` → zvýší PATCH (0.3.0 → 0.3.1)
- `feat:` → zvýší MINOR (0.3.0 → 0.4.0)
- `rel:` → zvýší MAJOR (0.3.0 → 1.0.0)

### Git Hooks

#### `commit-msg-hook.sh` / `commit-msg-hook.ps1`

Git commit-msg hook pro automatické zvýšení verze při commitu.

- **Bash verze** (`commit-msg-hook.sh`) - pro Linux/Mac/Git Bash
- **PowerShell verze** (`commit-msg-hook.ps1`) - pro Windows

Hook automaticky:
1. Přečte commit message
2. Detekuje prefix (`fix:`, `feat:`, `rel:`)
3. Zavolá `bump_version.py` pro zvýšení verze
4. Přidá změněné soubory do staging area

#### Instalační skripty

- **`install_hooks.sh`** - instalace hooku pro Linux/Mac/Git Bash
- **`install_hooks.ps1`** - instalace hooku pro Windows

**Instalace**:
```bash
# Linux/Mac/Git Bash
chmod +x scripts/install_hooks.sh
./scripts/install_hooks.sh

# Windows PowerShell
.\scripts\install_hooks.ps1
```

Po instalaci se hook automaticky spustí při každém commitu a zvýší verzi podle prefixu commit message.

## Použití

1. **Instalujte hook** (jednou):
   ```powershell
   .\scripts\install_hooks.ps1
   ```

2. **Commitujte s prefixem**:
   ```bash
   git commit -m "fix: oprava bugu"      # → 0.3.0 → 0.3.1
   git commit -m "feat: nova funkce"     # → 0.3.0 → 0.4.0
   git commit -m "rel: major release"    # → 0.3.0 → 1.0.0
   ```

3. **Verze se automaticky zvýší** v:
   - `src/irswitch/__init__.py`
   - `pyproject.toml`

4. **Změny jsou automaticky přidány** do staging area pro commit.

## Odinstalace

Pro odstranění hooku:

```bash
# Linux/Mac/Git Bash
rm .git/hooks/commit-msg

# Windows PowerShell
Remove-Item .git\hooks\commit-msg
```

## Více informací

Viz [VERSIONING.md](../VERSIONING.md) pro kompletní dokumentaci o verzování.
