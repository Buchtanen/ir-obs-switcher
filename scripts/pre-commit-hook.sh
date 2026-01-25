#!/bin/bash
# Pre-commit hook: auto-format + auto-fix lint (matches CI intent).
#
# - Runs only on staged Python files
# - Applies safe autofixes (ruff) + formatting (black)
# - Re-stages changed files so the commit includes the fixes
#
# Requirements (local dev):
#   pip install -e ".[lint]"
#
set -euo pipefail

# NOTE:
# This script is copied into `.git/hooks/pre-commit`.
# In that location, `$(dirname "$0")/..` would resolve to `.git/`, not repo root.
# Always resolve repo root via git.
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "${REPO_ROOT}" ]; then
  echo "pre-commit: failed to resolve repo root (git rev-parse --show-toplevel)" >&2
  exit 1
fi
cd "$REPO_ROOT"

mapfile -t PY_FILES < <(git diff --cached --name-only --diff-filter=ACMR | grep -E '\.py$' || true)
if [ "${#PY_FILES[@]}" -eq 0 ]; then
  exit 0
fi

if ! command -v ruff >/dev/null 2>&1; then
  echo "pre-commit: ruff not found. Install via: pip install -e \".[lint]\"" >&2
  exit 1
fi

if ! command -v black >/dev/null 2>&1; then
  echo "pre-commit: black not found. Install via: pip install -e \".[lint]\"" >&2
  exit 1
fi

echo "pre-commit: ruff --fix on staged python files"
ruff check --fix "${PY_FILES[@]}"

echo "pre-commit: black on staged python files"
black "${PY_FILES[@]}"

git add -- "${PY_FILES[@]}"

echo "pre-commit: verify ruff/black"
ruff check "${PY_FILES[@]}"
black --check "${PY_FILES[@]}"

exit 0

