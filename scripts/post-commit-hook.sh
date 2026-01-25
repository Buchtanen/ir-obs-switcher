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
PYPROJECT_FILE="$PROJECT_ROOT/pyproject.toml"

# Zkontrolovat, zda soubor existuje
if [ ! -f "$PYPROJECT_FILE" ]; then
    exit 0
fi

# Spočítat hash obsahu souboru (pyproject.toml je single source of truth)
PYPROJECT_HASH=$(sha256sum "$PYPROJECT_FILE" 2>/dev/null | cut -d' ' -f1)

# Pokud je uložený hash z před-commit stavu, porovnat
PRE_COMMIT_PYPROJECT_HASH_FILE="$PROJECT_ROOT/.git/.version_pyproject_hash"

if [ -f "$PRE_COMMIT_PYPROJECT_HASH_FILE" ]; then
    PRE_PYPROJECT_HASH=$(cat "$PRE_COMMIT_PYPROJECT_HASH_FILE")

    # Porovnat hash - pokud se liší, verze byla změněna
    if [ "$PYPROJECT_HASH" != "$PRE_PYPROJECT_HASH" ]; then
        # Změna detekována - přidat do staging
        if ! git add "$PYPROJECT_FILE" 2>/dev/null; then
            echo "Warning: Failed to stage version file" >&2
            rm -f "$PRE_COMMIT_PYPROJECT_HASH_FILE"
            exit 0
        fi
        
        # Amendnout commit s environment variable pro ochranu proti rekurzi
        # --no-verify přeskočí všechny hooky (včetně tohoto)
        if GIT_VERSION_AMENDING=1 git commit --amend --no-edit --no-verify 2>/dev/null; then
            echo "Version file (pyproject.toml) amended to commit"
        else
            echo "Warning: Failed to amend commit with version file" >&2
            # Unstage file pokud amend selhal
            git reset HEAD "$PYPROJECT_FILE" 2>/dev/null || true
        fi
    fi

    # Smazat dočasný soubor
    rm -f "$PRE_COMMIT_PYPROJECT_HASH_FILE"
fi

exit 0