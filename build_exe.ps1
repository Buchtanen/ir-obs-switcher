# PowerShell script to build EXE files for Windows
# Usage: .\build_exe.ps1 [--core] [--tui] [--all]

param(
    [switch]$Core,
    [switch]$Tui,
    [switch]$All
)

# Default to all if no option specified
if (-not $Core -and -not $Tui) {
    $All = $true
}

Write-Host "Building EXE files..." -ForegroundColor Cyan
Write-Host ""

# Check if PyInstaller is installed
$pyinstaller = python -m pip show pyinstaller 2>$null
if (-not $pyinstaller) {
    Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
    python -m pip install pyinstaller
}

# Create dist directory if it doesn't exist
if (-not (Test-Path "dist")) {
    New-Item -ItemType Directory -Path "dist" | Out-Null
}

# Build core service
if ($Core -or $All) {
    Write-Host "Building core service (irswitchd.exe)..." -ForegroundColor Green
    pyinstaller --onefile `
        --name irswitchd `
        --collect-all irswitch `
        --distpath dist `
        --workpath build `
        --clean `
        src\irswitch\main.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Core service built: dist\irswitchd.exe" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to build core service" -ForegroundColor Red
        exit 1
    }
}

# Build TUI
if ($Tui -or $All) {
    Write-Host "Building TUI (irswitch-tui.exe)..." -ForegroundColor Green
    pyinstaller --onefile `
        --name irswitch-tui `
        --collect-all irswitch_tui `
        --collect-all textual `
        --distpath dist `
        --workpath build `
        --clean `
        src\irswitch_tui\main.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ TUI built: dist\irswitch-tui.exe" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to build TUI" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "Build complete! Files are in dist\" -ForegroundColor Cyan
Write-Host ""
Write-Host "Usage:" -ForegroundColor Yellow
Write-Host "  dist\irswitchd.exe --config config\config.ini"
Write-Host "  dist\irswitch-tui.exe --url http://127.0.0.1:17321"
