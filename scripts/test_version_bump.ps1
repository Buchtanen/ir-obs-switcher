# Testovací skript pro ověření automatického verzování

Write-Host "=== Test automatického verzování ===" -ForegroundColor Cyan
Write-Host ""

# Získat aktuální verzi
$initFile = "src\irswitch\__init__.py"
$pyprojectFile = "pyproject.toml"

Write-Host "1. Kontrola aktuální verze..." -ForegroundColor Yellow
$currentVersion = Select-String -Path $initFile -Pattern '__version__\s*=\s*["'']([^"'']+)["'']' | ForEach-Object { $_.Matches.Groups[1].Value }
Write-Host "   Aktuální verze v __init__.py: $currentVersion" -ForegroundColor Green

$currentVersionPyproject = Select-String -Path $pyprojectFile -Pattern 'version\s*=\s*["'']([^"'']+)["'']' | ForEach-Object { $_.Matches.Groups[1].Value }
Write-Host "   Aktuální verze v pyproject.toml: $currentVersionPyproject" -ForegroundColor Green

if ($currentVersion -ne $currentVersionPyproject) {
    Write-Host "   ⚠ Varování: Verze se neshodují!" -ForegroundColor Red
} else {
    Write-Host "   ✓ Verze se shodují" -ForegroundColor Green
}

Write-Host ""
Write-Host "2. Test bump_version.py skriptu..." -ForegroundColor Yellow

# Test PATCH bump
Write-Host "   Test PATCH bump (fix:)" -ForegroundColor Cyan
$testOutput = python scripts\bump_version.py "fix: test" 2>&1
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    $newVersion = ($testOutput | Select-String -Pattern '^\d+\.\d+\.\d+$').Matches.Value
    Write-Host "   ✓ Skript úspěšně zvýšil verzi na: $newVersion" -ForegroundColor Green
    
    # Zkontrolovat, zda se soubory skutečně změnily
    $updatedVersion = Select-String -Path $initFile -Pattern '__version__\s*=\s*["'']([^"'']+)["'']' | ForEach-Object { $_.Matches.Groups[1].Value }
    if ($updatedVersion -eq $newVersion) {
        Write-Host "   ✓ Soubory byly aktualizovány" -ForegroundColor Green
    } else {
        Write-Host "   ✗ Soubory nebyly aktualizovány!" -ForegroundColor Red
    }
} else {
    Write-Host "   ✗ Skript selhal: $testOutput" -ForegroundColor Red
}

Write-Host ""
Write-Host "3. Kontrola Git hooku..." -ForegroundColor Yellow
$hookFile = ".git\hooks\commit-msg"
if (Test-Path $hookFile) {
    Write-Host "   ✓ Hook je nainstalován: $hookFile" -ForegroundColor Green
    
    $hookContent = Get-Content $hookFile -Raw
    if ($hookContent -match "bump_version") {
        Write-Host "   ✓ Hook obsahuje odkaz na bump_version.py" -ForegroundColor Green
    } else {
        Write-Host "   ⚠ Hook neobsahuje odkaz na bump_version.py" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ✗ Hook není nainstalován!" -ForegroundColor Red
    Write-Host "   Spusťte: .\scripts\install_hooks.ps1" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "4. Instrukce:" -ForegroundColor Yellow
Write-Host "   - Pro zvýšení verze použijte commit s prefixem:" -ForegroundColor White
Write-Host "     git commit -m 'fix: oprava'     (PATCH)" -ForegroundColor Gray
Write-Host "     git commit -m 'feat: nova funkce' (MINOR)" -ForegroundColor Gray
Write-Host "     git commit -m 'rel: major'      (MAJOR)" -ForegroundColor Gray
Write-Host ""
Write-Host "   - Po změně verze RESTARTUJTE aplikaci!" -ForegroundColor Yellow
Write-Host "     Verze se načítá při startu aplikace." -ForegroundColor Gray
Write-Host ""
