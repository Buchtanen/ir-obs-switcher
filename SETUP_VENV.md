# Nastavení virtuálního prostředí (.venv)

## Vytvoření nového .venv

Preferovaná verze Pythonu: **3.11–3.13** (stejně jako CI).

### Windows (PowerShell)

```powershell
cd "c:\Users\richa\Projekty\obs-switcher\richa"

# Vytvoření virtuálního prostředí
python -m venv .venv

# Aktivace virtuálního prostředí
.venv\Scripts\Activate.ps1

# Upgrade build tooling (fix Safety findings for old setuptools)
python -m pip install -U "pip" "setuptools>=78.1.1" "wheel"

# Instalace závislostí z pyproject.toml
pip install -e .
```

### Linux/Mac (Bash)

```bash
cd /cesta/k/projektu

# Vytvoření virtuálního prostředí
python3 -m venv .venv

# Aktivace virtuálního prostředí
source .venv/bin/activate

# Upgrade build tooling (fix Safety findings for old setuptools)
python -m pip install -U "pip" "setuptools>=78.1.1" "wheel"

# Instalace závislostí z pyproject.toml
pip install -e .
```

## Ověření

Po aktivaci by měl být v promptu vidět `(.venv)`:

```powershell
(.venv) PS C:\Users\richa\Projekty\obs-switcher\richa>
```

## Deaktivace

Když chceš deaktivovat virtuální prostředí:

```powershell
deactivate
```

## Poznámky

- `.venv/` je v `.gitignore`, takže se necommitne do gitu
- Každý vývojář si vytvoří své vlastní `.venv` lokálně
- Závislosti jsou definované v `pyproject.toml`
