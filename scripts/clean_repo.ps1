# PowerShell script to clean repository from unwanted files
# This script removes files from git history that should not be there
# Usage: .\scripts\clean_repo.ps1

Write-Host "=== Repository Cleaning Script ===" -ForegroundColor Cyan
Write-Host ""

# Check if git-filter-repo is installed
$hasFilterRepo = python -m pip show git-filter-repo 2>$null
if (-not $hasFilterRepo) {
    Write-Host "Installing git-filter-repo..." -ForegroundColor Yellow
    python -m pip install git-filter-repo
}

Write-Host "Step 1: Removing .cursor/skills/ directory from git history..." -ForegroundColor Green
# Remove only .cursor/skills/, keep .cursorignore and .cursorrules
git filter-repo --path .cursor/skills --invert-paths --force

Write-Host "Step 2: Removing config/config.ini from git history (if exists)..." -ForegroundColor Green
git filter-repo --path config/config.ini --invert-paths --force

Write-Host "Step 3: Removing docs/ directory from git history (if exists)..." -ForegroundColor Green
git filter-repo --path docs --invert-paths --force

Write-Host "Step 4: Removing dist/ directory from git history (if exists)..." -ForegroundColor Green
git filter-repo --path dist --invert-paths --force

Write-Host "Step 5: Removing build/ directory from git history (if exists)..." -ForegroundColor Green
git filter-repo --path build --invert-paths --force

Write-Host "Step 6: Removing .vscode/ directory from git history (if exists)..." -ForegroundColor Green
git filter-repo --path .vscode --invert-paths --force

Write-Host "Step 7: Removing .venv/ directory from git history (if exists)..." -ForegroundColor Green
git filter-repo --path .venv --invert-paths --force

Write-Host "Step 8: Removing pytest_cache/ directory from git history (if exists)..." -ForegroundColor Green
git filter-repo --path pytest_cache --invert-paths --force

Write-Host "Step 9: Removing log files (*.log, *.log.*) from git history..." -ForegroundColor Green
# Remove all log files and rotated logs
git filter-repo --path-glob "*.log" --invert-paths --force
git filter-repo --path-glob "*.log.*" --invert-paths --force
git filter-repo --path logs --invert-paths --force

Write-Host ""
Write-Host "=== Cleaning completed ===" -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANT: Review the changes with:" -ForegroundColor Yellow
Write-Host "  git log --all --oneline" -ForegroundColor White
Write-Host ""
Write-Host "To push cleaned history to GitHub (WARNING: rewrites history!):" -ForegroundColor Yellow
Write-Host "  git push origin --force --all" -ForegroundColor White
Write-Host "  git push origin --force --tags" -ForegroundColor White
Write-Host ""
Write-Host "Make sure all collaborators are aware of this change!" -ForegroundColor Red
