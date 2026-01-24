# Automatické verzování - Rychlý start

## Instalace

**Windows**:
```powershell
.\scripts\install_hooks.ps1
```

**Linux/Mac/Git Bash**:
```bash
chmod +x scripts/install_hooks.sh
./scripts/install_hooks.sh
```

## Použití

Po instalaci stačí použít správný prefix v commit message:

```bash
git commit -m "fix: oprava bugu"      # 0.3.0 → 0.3.1 (PATCH)
git commit -m "feat: nova funkce"      # 0.3.0 → 0.4.0 (MINOR)
git commit -m "rel: major release"     # 0.3.0 → 1.0.0 (MAJOR)
```

Verze se automaticky zvýší v:
- `src/irswitch/__init__.py`
- `pyproject.toml`

Změny jsou automaticky přidány do staging area.

## Více informací

Viz [VERSIONING.md](VERSIONING.md) pro kompletní dokumentaci.
