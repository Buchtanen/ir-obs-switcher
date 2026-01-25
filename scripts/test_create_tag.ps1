# Test script pro lokální testování create-release-tag workflow
# Simuluje kroky z .github/workflows/create-release-tag.yml

Write-Host "=== Test Create Release Tag Workflow ===" -ForegroundColor Cyan
Write-Host ""

# 1. Get current version from pyproject.toml
Write-Host "[1/4] Getting current version from pyproject.toml..." -ForegroundColor Yellow
$versionOutput = python -c "import tomllib; f=open('pyproject.toml','rb'); d=tomllib.load(f); print(d['project']['version'])"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error reading version" -ForegroundColor Red
    exit 1
}
$version = $versionOutput.Trim()
Write-Host "Current version: $version" -ForegroundColor Green

# 2. Check if tag exists
Write-Host ""
Write-Host "[2/4] Checking if tag v$version exists..." -ForegroundColor Yellow
$tagName = "v$version"
$tagExists = $false

$null = git rev-parse "$tagName" 2>&1
if ($LASTEXITCODE -eq 0) {
    $tagExists = $true
    Write-Host "Tag $tagName already exists" -ForegroundColor Yellow
} else {
    Write-Host "Tag $tagName does not exist - would create" -ForegroundColor Green
}

# 3. Simulate tag creation (dry-run)
Write-Host ""
Write-Host "[3/4] Simulating tag creation..." -ForegroundColor Yellow
if ($tagExists) {
    Write-Host "Tag already exists - would skip creation" -ForegroundColor Yellow
} else {
    Write-Host "Would run:" -ForegroundColor Gray
    Write-Host "  git config user.name github-actions[bot]" -ForegroundColor Gray
    Write-Host "  git config user.email github-actions[bot]@users.noreply.github.com" -ForegroundColor Gray
    Write-Host "  git tag -a $tagName -m Release version $version" -ForegroundColor Gray
    Write-Host "  git push origin $tagName" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Tag creation command prepared" -ForegroundColor Green
}

# 4. Summary
Write-Host ""
Write-Host "[4/4] Test summary..." -ForegroundColor Yellow
Write-Host ""
Write-Host "=== Test Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  Version: $version" -ForegroundColor White
Write-Host "  Tag: $tagName" -ForegroundColor White
Write-Host "  Exists: $tagExists" -ForegroundColor White
Write-Host ""
Write-Host "To actually create the tag, run:" -ForegroundColor Cyan
Write-Host "  git tag -a $tagName -m `"Release version $version`"" -ForegroundColor White
Write-Host "  git push origin $tagName" -ForegroundColor White
Write-Host ""
