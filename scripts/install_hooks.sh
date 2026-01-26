#!/bin/bash
# Instalační skript pro Git hooks (Linux/Mac/Git Bash)
# Instaluje lokální kontroly podobné CI:
# - pre-commit: ruff --fix + black na staged .py a znovu je nastageuje
# - pre-push: mypy src/ (pokud je nainstalované)

set -e

# Získat cestu k projektu
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GIT_HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
PRE_COMMIT_HOOK="$GIT_HOOKS_DIR/pre-commit"
PRE_PUSH_HOOK="$GIT_HOOKS_DIR/pre-push"
PRE_COMMIT_SCRIPT="$PROJECT_ROOT/scripts/pre-commit-hook.sh"
PRE_PUSH_SCRIPT="$PROJECT_ROOT/scripts/pre-push-hook.sh"

# Vytvořit .git/hooks adresář pokud neexistuje
mkdir -p "$GIT_HOOKS_DIR"

rm -f "$GIT_HOOKS_DIR/prepare-commit-msg" "$GIT_HOOKS_DIR/post-commit" || true

if [ -f "$PRE_COMMIT_SCRIPT" ]; then
    cp "$PRE_COMMIT_SCRIPT" "$PRE_COMMIT_HOOK"
    chmod +x "$PRE_COMMIT_HOOK"
    echo "Installed pre-commit hook"
else
    echo "Error: pre-commit hook script not found: $PRE_COMMIT_SCRIPT" >&2
    exit 1
fi

if [ -f "$PRE_PUSH_SCRIPT" ]; then
    cp "$PRE_PUSH_SCRIPT" "$PRE_PUSH_HOOK"
    chmod +x "$PRE_PUSH_HOOK"
    echo "Installed pre-push hook"
else
    echo "Error: pre-push hook script not found: $PRE_PUSH_SCRIPT" >&2
    exit 1
fi

echo ""
echo "Git hooks installed successfully!"
echo ""
echo "Hooks:"
echo "  pre-commit: ruff --fix + black on staged .py files"
echo "  pre-push:   mypy src/ (if installed)"
echo ""
echo "Dependencies (recommended):"
echo "  pip install -e \".[lint]\""
echo ""