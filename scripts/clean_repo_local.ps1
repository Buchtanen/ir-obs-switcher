# PowerShell script to clean local repository
# Removes local files that should not be in repo
# Usage: .\scripts\clean_repo_local.ps1

Write-Host "=== Local Repository Cleaning ===" -ForegroundColor Cyan
Write-Host ""

$removed = @()

# Remove local config.ini (should only have config.example.ini)
if (Test-Path "config\config.ini") {
    Write-Host "Removing config\config.ini..." -ForegroundColor Yellow
    Remove-Item "config\config.ini" -Force
    $removed += "config\config.ini"
}

# Remove .cursor/skills directory (should be in .gitignore)
# Keep .cursorignore and .cursorrules as they are project config files
if (Test-Path ".cursor\skills") {
    Write-Host "Removing .cursor\skills\ directory..." -ForegroundColor Yellow
    Remove-Item ".cursor\skills" -Recurse -Force
    $removed += ".cursor\skills\"
}

# Remove dist directory if exists
if (Test-Path "dist") {
    Write-Host "Removing dist\ directory..." -ForegroundColor Yellow
    Remove-Item "dist" -Recurse -Force
    $removed += "dist\"
}

# Remove build directory if exists
if (Test-Path "build") {
    Write-Host "Removing build\ directory..." -ForegroundColor Yellow
    Remove-Item "build" -Recurse -Force
    $removed += "build\"
}

# Remove .vscode directory if exists
if (Test-Path ".vscode") {
    Write-Host "Removing .vscode\ directory..." -ForegroundColor Yellow
    Remove-Item ".vscode" -Recurse -Force
    $removed += ".vscode\"
}

# Remove .venv directory if exists
if (Test-Path ".venv") {
    Write-Host "Removing .venv\ directory..." -ForegroundColor Yellow
    Remove-Item ".venv" -Recurse -Force
    $removed += ".venv\"
}

# Remove pytest_cache directory if exists
if (Test-Path "pytest_cache") {
    Write-Host "Removing pytest_cache\ directory..." -ForegroundColor Yellow
    Remove-Item "pytest_cache" -Recurse -Force
    $removed += "pytest_cache\"
}

# Remove docs directory if exists
if (Test-Path "docs") {
    Write-Host "Removing docs\ directory..." -ForegroundColor Yellow
    Remove-Item "docs" -Recurse -Force
    $removed += "docs\"
}

if ($removed.Count -eq 0) {
    Write-Host "No files to remove - repository is clean!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Removed the following:" -ForegroundColor Green
    foreach ($item in $removed) {
        Write-Host "  - $item" -ForegroundColor White
    }
}

Write-Host ""
Write-Host "=== Local cleaning completed ===" -ForegroundColor Green
