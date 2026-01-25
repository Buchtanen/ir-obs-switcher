#!/bin/bash
# Removes legacy version-bump git hooks (prepare-commit-msg, post-commit).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$PROJECT_ROOT/.git/hooks"

if [ ! -d "$HOOKS_DIR" ]; then
  echo "No .git/hooks directory found at: $HOOKS_DIR" >&2
  exit 0
fi

for hook in prepare-commit-msg post-commit; do
  if [ -f "$HOOKS_DIR/$hook" ]; then
    rm -f "$HOOKS_DIR/$hook"
    echo "Removed hook: $hook"
  else
    echo "Not present: $hook"
  fi
done

