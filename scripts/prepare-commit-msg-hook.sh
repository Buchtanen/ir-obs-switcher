#!/bin/bash
# Git prepare-commit-msg hook pro automatické zvýšení verze podle commit message prefixu
#
# Tento hook běží PŘED vytvořením commitu.
# Uloží hashe verzí souborů, které post-commit hook použije pro detekci změn.
#
# Prefixy:
#   fix:  → zvýší PATCH (0.3.0 → 0.3.1)
#   feat: → zvýší MINOR (0.3.0 → 0.4.0)
#   rel:  → zvýší MAJOR (0.3.0 → 1.0.0)
#
# Argumenty (předány gitem):
#   $1 - cesta k commit message souboru
#   $2 - zdroj commitu ("message", "template", "merge", "squash", "commit")
#   $3 - SHA1 commitu (prázdné pro nový commit)

COMMIT_MSG_FILE="$1"
COMMIT_SOURCE="$2"
# SHA1="$3"  # Nepoužito, ale dostupné pro budoucí rozšíření

COMMIT_MSG=$(cat "$COMMIT_MSG_FILE")

# Získat cestu k projektu (parent adresář .git)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUMP_SCRIPT="$PROJECT_ROOT/scripts/bump_version.py"
INIT_FILE="$PROJECT_ROOT/src/irswitch/__init__.py"
PYPROJECT_FILE="$PROJECT_ROOT/pyproject.toml"

# Kontrolovat, že nepouštíme při merge squash atd.
# Jen při normálním commit message ("message")
if [ "$COMMIT_SOURCE" != "message" ] && [ "$COMMIT_SOURCE" != "" ]; then
    exit 0
fi

# Uložit hashe verzí souborů PŘED jakoukoli změnou
# Tyto hashe použije post-commit hook pro detekci změn
if [ -f "$INIT_FILE" ]; then
    sha256sum "$INIT_FILE" | cut -d' ' -f1 > ".git/.version_init_hash"
fi
if [ -f "$PYPROJECT_FILE" ]; then
    sha256sum "$PYPROJECT_FILE" | cut -d' ' -f1 > ".git/.version_pyproject_hash"
fi

# Kontrolovat, zda existuje bump script
if [ ! -f "$BUMP_SCRIPT" ]; then
    echo "Warning: bump_version.py not found at $BUMP_SCRIPT" >&2
    exit 0
fi

# Spustit bump script s commit message
NEW_VERSION=$(python "$BUMP_SCRIPT" "$COMMIT_MSG" 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "Error: Failed to bump version" >&2
    echo "$NEW_VERSION" >&2
    exit 0  # Nechceme blokovat commit, jen varování
fi

# Pokud byla verze zvýšena, informovat uživatele
if echo "$NEW_VERSION" | grep -q "^[0-9]\+\.[0-9]\+\.[0-9]\+$"; then
    echo "Version bumped to $NEW_VERSION - will be amended to commit"
fi

exit 0