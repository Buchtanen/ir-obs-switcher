#!/bin/bash
# Instalační skript pro Git hooks (Linux/Mac/Git Bash)
# Instaluje commit-msg hook pro automatické zvýšení verze

set -e

# Získat cestu k projektu
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GIT_HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
HOOK_FILE="$GIT_HOOKS_DIR/commit-msg"
HOOK_SCRIPT="$PROJECT_ROOT/scripts/commit-msg-hook.sh"

# Vytvořit .git/hooks adresář pokud neexistuje
mkdir -p "$GIT_HOOKS_DIR"

# Zkopírovat hook skript
if [ -f "$HOOK_SCRIPT" ]; then
    cp "$HOOK_SCRIPT" "$HOOK_FILE"
    chmod +x "$HOOK_FILE"
    echo "✓ Installed commit-msg hook"
else
    echo "Error: Hook script not found: $HOOK_SCRIPT" >&2
    exit 1
fi

echo ""
echo "Git hook installed successfully!"
echo ""
echo "Usage:"
echo "  git commit -m 'fix: oprava bugu'     → 0.3.0 → 0.3.1 (PATCH)"
echo "  git commit -m 'feat: nova funkce'     → 0.3.0 → 0.4.0 (MINOR)"
echo "  git commit -m 'rel: major release'     → 0.3.0 → 1.0.0 (MAJOR)"
echo ""
