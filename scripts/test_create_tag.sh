#!/bin/bash
# Test script pro lokální testování create-release-tag workflow (bash verze)
# Simuluje kroky z .github/workflows/create-release-tag.yml

echo "=== Test Create Release Tag Workflow ==="
echo ""

# 1. Get current version from pyproject.toml
echo "[1/4] Getting current version from pyproject.toml..."
VERSION=$(python -c "import tomllib; f=open('pyproject.toml','rb'); d=tomllib.load(f); print(d['project']['version'])")
if [ $? -ne 0 ]; then
    echo "✗ Error reading version"
    exit 1
fi
VERSION=$(echo "$VERSION" | tr -d '[:space:]')
echo "✓ Current version: $VERSION"

# 2. Check if tag exists
echo ""
echo "[2/4] Checking if tag v$VERSION exists..."
TAG_NAME="v$VERSION"
TAG_EXISTS=false

if git rev-parse "$TAG_NAME" >/dev/null 2>&1; then
    TAG_EXISTS=true
    COMMIT=$(git rev-parse "$TAG_NAME")
    echo "✓ Tag $TAG_NAME already exists"
    echo "  Commit: $COMMIT"
else
    echo "✓ Tag $TAG_NAME does not exist - would create"
fi

# 3. Simulate tag creation (dry-run)
echo ""
echo "[3/4] Simulating tag creation..."
if [ "$TAG_EXISTS" = true ]; then
    echo "⚠ Tag already exists - would skip creation"
else
    echo "Would run:"
    echo "  git config user.name \"github-actions[bot]\""
    echo "  git config user.email \"github-actions[bot]@users.noreply.github.com\""
    echo "  git tag -a \"$TAG_NAME\" -m \"Release version $VERSION\""
    echo "  git push origin \"$TAG_NAME\""
    echo ""
    echo "✓ Tag creation command prepared"
fi

# 4. Summary
echo ""
echo "[4/4] Test summary..."
echo ""
echo "=== Test Complete ==="
echo ""
echo "Summary:"
echo "  Version: $VERSION"
echo "  Tag: $TAG_NAME"
echo "  Exists: $TAG_EXISTS"
echo ""
echo "To actually create the tag, run:"
echo "  git tag -a $TAG_NAME -m \"Release version $VERSION\""
echo "  git push origin $TAG_NAME"
echo ""
