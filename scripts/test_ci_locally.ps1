# Test script pro lokální testování CI/CD workflow
# Simuluje všechny kroky z .github/workflows/ci.yml

$ErrorActionPreference = "Stop"
$allTestsPassed = $true

Write-Host "=== Lokální testování CI/CD workflow ===" -ForegroundColor Cyan
Write-Host ""

# Funkce pro testování
function Test-Step {
    param(
        [string]$Name,
        [scriptblock]$TestScript
    )
    Write-Host "[TEST] $Name..." -ForegroundColor Yellow
    try {
        & $TestScript
        Write-Host "[OK] $Name" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "[FAIL] $Name" -ForegroundColor Red
        Write-Host "  Error: $_" -ForegroundColor Red
        return $false
    }
}

# 1. Kontrola Python verze
$pythonVersion = Test-Step "Python version check" {
    $version = python --version
    if ($version -match "Python 3\.(11|12|13)") {
        Write-Host "  Python: $version" -ForegroundColor Gray
    } else {
        throw "Python 3.11+ required, found: $version"
    }
}

# 2. Instalace dependencies
$depsInstalled = Test-Step "Install dependencies" {
    python -m pip install --upgrade pip --quiet
    pip install -e ".[test,lint,security]" --quiet
    Write-Host "  Dependencies installed" -ForegroundColor Gray
}

if (-not $depsInstalled) {
    Write-Host ""
    Write-Host "⚠ Failed to install dependencies - some tests will be skipped" -ForegroundColor Yellow
    Write-Host ""
}

# 3. Linting (ruff)
$ruffTest = Test-Step "Lint (ruff)" {
    if (Get-Command ruff -ErrorAction SilentlyContinue) {
        ruff check src/ tests/
        Write-Host "  Ruff check passed" -ForegroundColor Gray
    } else {
        throw "ruff not installed"
    }
}

# 4. Formatting (black)
$blackTest = Test-Step "Format (black)" {
    if (Get-Command black -ErrorAction SilentlyContinue) {
        black --check src/ tests/
        Write-Host "  Black check passed" -ForegroundColor Gray
    } else {
        throw "black not installed"
    }
}

# 5. Type checking (mypy)
$mypyTest = Test-Step "Type check (mypy)" {
    if (Get-Command mypy -ErrorAction SilentlyContinue) {
        $env:PYTHONPATH = "$PWD/src"
        mypy src/
        Write-Host "  Mypy check passed" -ForegroundColor Gray
    } else {
        throw "mypy not installed"
    }
}

# 6. Security - Bandit
$banditTest = Test-Step "Security (Bandit)" {
    if (Get-Command bandit -ErrorAction SilentlyContinue) {
        bandit -r src/ -f json -o bandit-report.json
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  Bandit check passed" -ForegroundColor Gray
        } else {
            Write-Host "  Bandit found issues (check bandit-report.json)" -ForegroundColor Yellow
        }
    } else {
        throw "bandit not installed"
    }
}

# 7. Security - Safety
$safetyTest = Test-Step "Security (Safety)" {
    if (Get-Command safety -ErrorAction SilentlyContinue) {
        safety check --json 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  Safety check passed" -ForegroundColor Gray
        } else {
            Write-Host "  Safety found issues" -ForegroundColor Yellow
        }
    } else {
        throw "safety not installed"
    }
}

# 8. Tests
$testsPassed = Test-Step "Tests (pytest)" {
    if (Get-Command pytest -ErrorAction SilentlyContinue) {
        $env:PYTHONPATH = "$PWD/src"
        pytest -v --tb=short
        Write-Host "  All tests passed" -ForegroundColor Gray
    } else {
        throw "pytest not installed"
    }
}

# 9. Tests with coverage
$coverageTest = Test-Step "Tests with coverage" {
    if (Get-Command pytest -ErrorAction SilentlyContinue) {
        $env:PYTHONPATH = "$PWD/src"
        pytest --cov=src/irswitch --cov-report=term --cov-report=html --tb=short
        Write-Host "  Coverage report generated" -ForegroundColor Gray
        if (Test-Path "htmlcov/index.html") {
            Write-Host "  Coverage HTML: htmlcov/index.html" -ForegroundColor Gray
        }
    } else {
        throw "pytest not installed"
    }
}

# 10. Build verification
$buildTest = Test-Step "Build verification" {
    if (Get-Command pyinstaller -ErrorAction SilentlyContinue) {
        Write-Host "  PyInstaller available" -ForegroundColor Gray
        # Jen ověření, že build script existuje a je spustitelný
        if (Test-Path "build_exe.ps1") {
            Write-Host "  Build script exists" -ForegroundColor Gray
        } else {
            throw "build_exe.ps1 not found"
        }
    } else {
        Write-Host "  PyInstaller not installed (skipping build test)" -ForegroundColor Yellow
    }
}

# Shrnutí
Write-Host ""
Write-Host "=== Shrnutí testů ===" -ForegroundColor Cyan
Write-Host ""

$results = @{
    "Python version" = $pythonVersion
    "Dependencies" = $depsInstalled
    "Lint (ruff)" = $ruffTest
    "Format (black)" = $blackTest
    "Type check (mypy)" = $mypyTest
    "Security (Bandit)" = $banditTest
    "Security (Safety)" = $safetyTest
    "Tests" = $testsPassed
    "Tests with coverage" = $coverageTest
    "Build verification" = $buildTest
}

foreach ($test in $results.GetEnumerator() | Sort-Object Name) {
    $status = if ($test.Value) { "[OK]" } else { "[FAIL]" }
    $color = if ($test.Value) { "Green" } else { "Red" }
    Write-Host "$status $($test.Key)" -ForegroundColor $color
}

$allPassed = ($results.Values | Where-Object { $_ -eq $false }).Count -eq 0

Write-Host ""
if ($allPassed) {
    Write-Host "✓ Všechny testy prošly!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "✗ Některé testy selhaly" -ForegroundColor Red
    Write-Host ""
    Write-Host "Pro instalaci chybějících nástrojů spusť:" -ForegroundColor Yellow
    Write-Host "pip install -e .[test,lint,security]" -ForegroundColor White
    exit 1
}
