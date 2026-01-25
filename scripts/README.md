# Scripts

Tento adresář obsahuje pomocné skripty pro správu projektu.

## Verzování

### `bump_version.py`

Python skript pro automatické zvýšení verze podle commit message prefixu.

**Status**: deprecated (verzování je řízené přes Release PR / CD pipeline).

**Použití** (jen ručně, pokud to někdy budeš potřebovat):
```bash
python scripts/bump_version.py "fix: oprava bugu"
```

**Prefixy**:
- `fix:` → zvýší PATCH (0.3.0 → 0.3.1)
- `feat:` → zvýší MINOR (0.3.0 → 0.4.0)
- `rel:` → zvýší MAJOR (0.3.0 → 1.0.0)

### Git Hooks (lokální lint/format)

Repo používá **PR-driven release** (Release PR model). Lokální hooky proto řeší jen to,
co dává smysl před commitem/pushem: **format + lint + (volitelně) type-check**.

#### Co se instaluje
- **`pre-commit`**: `ruff check --fix` + `black` na staged `.py` souborech + znovu je nastageuje
- **`pre-push`**: `mypy src/` pokud je nainstalované (jinak jen varování)

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

> Pozn.: tohle už neplatí — bump verze se lokálně nedělá, verzování řeší Release PR.

## Doporučené závislosti
```bash
pip install -e ".[lint]"
```

## Odinstalace / reset hooků
Nejjednodušší je znovu spustit `install_hooks.*` (přepíše hooky). Ručně můžeš smazat:

- `.git/hooks/pre-commit`
- `.git/hooks/pre-push`
- (historicky) `.git/hooks/prepare-commit-msg`, `.git/hooks/post-commit`

## Více informací

Viz [VERSIONING.md](../VERSIONING.md) pro kompletní dokumentaci o verzování.
