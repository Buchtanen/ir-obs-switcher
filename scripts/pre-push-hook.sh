#!/bin/bash
# Pre-push hook: local safety net before pushing.
#
# Runs:
# - mypy src/ (matches CI type-check) if available
# - bandit (matches CI security-bandit) if available
#
# We keep this lighter than full CI to avoid slowing down pushes too much.
#
# Requirements (local dev):
#   pip install -e ".[lint]"
#
set -euo pipefail

# NOTE:
# This script is copied into `.git/hooks/pre-push`.
# In that location, `$(dirname "$0")/..` would resolve to `.git/`, not repo root.
# Always resolve repo root via git.
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "${REPO_ROOT}" ]; then
  echo "pre-push: failed to resolve repo root (git rev-parse --show-toplevel)" >&2
  exit 1
fi
cd "$REPO_ROOT"

if command -v mypy >/dev/null 2>&1; then
  echo "pre-push: mypy src/"
  mypy "$REPO_ROOT/src/"
else
  echo "pre-push: mypy not found (skipping). Install via: pip install -e \".[lint]\"" >&2
fi

if command -v bandit >/dev/null 2>&1; then
  echo "pre-push: bandit src/ (severity >= medium)"
  bandit -r "$REPO_ROOT/src/" -c "$REPO_ROOT/pyproject.toml" --severity-level medium -q
else
  echo "pre-push: bandit not found (skipping). Install via: pip install -e \".[security]\"" >&2
fi

exit 0

