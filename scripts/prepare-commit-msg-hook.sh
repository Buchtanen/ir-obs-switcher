#!/bin/bash
# Git prepare-commit-msg hook pro automatické zvýšení verze podle commit message prefixu
#
# Tento hook běží PŘED vytvořením commitu, což umožňuje modifikovat staging area
# tak, aby změny byly zahrnuty ve stejném commitu.
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

# Kontrolovat, že nepouštíme při merge squash atd.
# Jen při normálním commit message ("message")
if [ "$COMMIT_SOURCE" != "message" ] && [ "$COMMIT_SOURCE" != "" ]; then
    exit 0
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

# Pokud byla verze zvýšena, přidat změny do staging area
if echo "$NEW_VERSION" | grep -q "^[0-9]\+\.[0-9]\+\.[0-9]\+$"; then
    git add "$PROJECT_ROOT/src/irswitch/__init__.py" "$PROJECT_ROOT/pyproject.toml" 2>/dev/null
    echo "Version bumped to $NEW_VERSION - files staged for commit"
fi

exit 0