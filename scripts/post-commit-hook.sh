#!/bin/bash
# Git post-commit hook pro automatické zahrnutí změn verzí do commitu
#
# Tento hook běží PO vytvoření commitu.
# Pokud byly změněny soubory s verzí (bump_version.py),
# přidá je do staging area a provede amend.
#
# Funguje takto:
# 1. Commit se vytvoří (bez verzí)
# 2. post-commit hook detekuje změnu verzí
# 3. git add + git commit --amend --no-edit --no-verify
# 4. Výsledek: jeden commit včetně změn verzí

set -e  # Exit on error

# OCHRANA PROTI REKURZI: Pokud běžíme z amend operace (via environment variable), přeskočit
if [ "$GIT_VERSION_AMENDING" = "1" ]; then
    exit 0
fi

# Získat cestu k projektu (parent adresář .git)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INIT_FILE="$PROJECT_ROOT/src/irswitch/__init__.py"
PYPROJECT_FILE="$PROJECT_ROOT/pyproject.toml"

# Zkontrolovat, zda soubory existují
if [ ! -f "$INIT_FILE" ] || [ ! -f "$PYPROJECT_FILE" ]; then
    exit 0
fi

# Spočítat hash obsahu souborů
INIT_HASH=$(sha256sum "$INIT_FILE" 2>/dev/null | cut -d' ' -f1)
PYPROJECT_HASH=$(sha256sum "$PYPROJECT_FILE" 2>/dev/null | cut -d' ' -f1)

# Pokud je uložený hash z před-commit stavu, porovnat
PRE_COMMIT_INIT_HASH_FILE="$PROJECT_ROOT/.git/.version_init_hash"
PRE_COMMIT_PYPROJECT_HASH_FILE="$PROJECT_ROOT/.git/.version_pyproject_hash"

if [ -f "$PRE_COMMIT_INIT_HASH_FILE" ] && [ -f "$PRE_COMMIT_PYPROJECT_HASH_FILE" ]; then
    PRE_INIT_HASH=$(cat "$PRE_COMMIT_INIT_HASH_FILE")
    PRE_PYPROJECT_HASH=$(cat "$PRE_COMMIT_PYPROJECT_HASH_FILE")

    # Porovnat hashe - pokud se liší, verze byla změněna
    if [ "$INIT_HASH" != "$PRE_INIT_HASH" ] || [ "$PYPROJECT_HASH" != "$PRE_PYPROJECT_HASH" ]; then
        # Změna detekována - přidat do staging
        if ! git add "$INIT_FILE" "$PYPROJECT_FILE" 2>/dev/null; then
            echo "Warning: Failed to stage version files" >&2
            rm -f "$PRE_COMMIT_INIT_HASH_FILE" "$PRE_COMMIT_PYPROJECT_HASH_FILE"
            exit 0
        fi
        
        # Amendnout commit s environment variable pro ochranu proti rekurzi
        # --no-verify přeskočí všechny hooky (včetně tohoto)
        if GIT_VERSION_AMENDING=1 git commit --amend --no-edit --no-verify 2>/dev/null; then
            echo "Version files amended to commit"
        else
            echo "Warning: Failed to amend commit with version files" >&2
            # Unstage files pokud amend selhal
            git reset HEAD "$INIT_FILE" "$PYPROJECT_FILE" 2>/dev/null || true
        fi
    fi

    # Smazat dočasné soubory
    rm -f "$PRE_COMMIT_INIT_HASH_FILE" "$PRE_COMMIT_PYPROJECT_HASH_FILE"
fi

exit 0