#!/bin/bash
# Instalační skript pro Git hooks (Linux/Mac/Git Bash)
# Instaluje prepare-commit-msg a post-commit hooky pro automatické zvýšení verze
#
# prepare-commit-msg hook běží PŘED vytvořením commitu a ukládá hashe verzí
# post-commit hook běží PO vytvoření commitu a pokud byly verze změněny,
# provede amend pro zahrnutí změn do stejného commitu

set -e

# Získat cestu k projektu
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GIT_HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
PREPARE_HOOK="$GIT_HOOKS_DIR/prepare-commit-msg"
POST_HOOK="$GIT_HOOKS_DIR/post-commit"
PREPARE_SCRIPT="$PROJECT_ROOT/scripts/prepare-commit-msg-hook.sh"
POST_SCRIPT="$PROJECT_ROOT/scripts/post-commit-hook.sh"

# Vytvořit .git/hooks adresář pokud neexistuje
mkdir -p "$GIT_HOOKS_DIR"

# Instalovat prepare-commit-msg hook
if [ -f "$PREPARE_SCRIPT" ]; then
    cp "$PREPARE_SCRIPT" "$PREPARE_HOOK"
    chmod +x "$PREPARE_HOOK"
    echo "Installed prepare-commit-msg hook"
else
    echo "Error: Prepare hook script not found: $PREPARE_SCRIPT" >&2
    exit 1
fi

# Instalovat post-commit hook
if [ -f "$POST_SCRIPT" ]; then
    cp "$POST_SCRIPT" "$POST_HOOK"
    chmod +x "$POST_HOOK"
    echo "Installed post-commit hook"
else
    echo "Error: Post-commit hook script not found: $POST_SCRIPT" >&2
    exit 1
fi

echo ""
echo "Git hooks installed successfully!"
echo ""
echo "Workflow:"
echo "  1. prepare-commit-msg: bumps version, stores pre-commit hashes"
echo "  2. Commit created (without version files)"
echo "  3. post-commit: detects version change, amends commit"
echo "  Result: One commit including version changes"
echo ""
echo "Usage:"
echo "  git commit -m 'fix: oprava bugu'     -> 0.3.0 -> 0.3.1 (PATCH)"
echo "  git commit -m 'feat: nova funkce'     -> 0.3.0 -> 0.4.0 (MINOR)"
echo "  git commit -m 'rel: major release'     -> 0.3.0 -> 1.0.0 (MAJOR)"
echo ""