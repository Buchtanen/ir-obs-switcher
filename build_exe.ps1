# PowerShell script to build EXE files for Windows
# Usage: .\build_exe.ps1 [--core] [--all]

param(
    [switch]$Core,
    [switch]$All
)

# Default to all if no option specified
if (-not $Core) {
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
        --noconsole `
        --collect-all irswitch `
        --add-data "assets;assets" `
        --distpath dist `
        --workpath build `
        --clean `
        --noupx `
        src\irswitch\main.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host '[OK] Core service built: dist\irswitchd.exe' -ForegroundColor Green
    } else {
        Write-Host '[ERROR] Failed to build core service' -ForegroundColor Red
        exit 1
    }
}


# Copy necessary files to dist for distribution
Write-Host ""
Write-Host "Copying necessary files to dist..." -ForegroundColor Cyan

# Copy config template (avoid leaking local config/config.ini)
$configDest = Join-Path "dist" "config"
if (-not (Test-Path $configDest)) {
    New-Item -ItemType Directory -Path $configDest | Out-Null
}

$exampleIni = Join-Path "config" "config.example.ini"
if (Test-Path $exampleIni) {
    Copy-Item -Path $exampleIni -Destination (Join-Path $configDest "config.example.ini") -Force
    # Provide initial config.ini as a copy of the template (safe placeholders)
    Copy-Item -Path $exampleIni -Destination (Join-Path $configDest "config.ini") -Force
    Write-Host '  [OK] Copied config template (config.example.ini + config.ini)' -ForegroundColor Green
} else {
    Write-Host '  [WARN] config/config.example.ini not found' -ForegroundColor Yellow
}

# Copy installer scripts
$installScript = Join-Path "scripts" "Install.ps1"
$openDashScript = Join-Path "scripts" "Open-Dashboard.ps1"

if (Test-Path $installScript) {
    Copy-Item -Path $installScript -Destination (Join-Path "dist" "Install.ps1") -Force
    Write-Host '  [OK] Copied Install.ps1' -ForegroundColor Green
} else {
    Write-Host '  [WARN] scripts/Install.ps1 not found' -ForegroundColor Yellow
}

if (Test-Path $openDashScript) {
    Copy-Item -Path $openDashScript -Destination (Join-Path "dist" "Open-Dashboard.ps1") -Force
    Write-Host '  [OK] Copied Open-Dashboard.ps1' -ForegroundColor Green
} else {
    Write-Host '  [WARN] scripts/Open-Dashboard.ps1 not found' -ForegroundColor Yellow
}

# Create README for distribution
$readmeContent = @"
# iRacing OBS Switcher - Distribution

## Files

- `irswitchd.exe` - Main application (silent background process)
- `config/` - Configuration directory
  - `config.example.ini` - Example configuration
- `Install.ps1` - Installer (wizard + autostart + shortcuts)
- `Open-Dashboard.ps1` - Opens dashboard URL from config

## Usage

Recommended:
1. Run installer wizard: `powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -Wizard`
2. Use created desktop shortcuts:
   - iRacing OBS Switcher
   - iRacing OBS Switcher - Dashboard

Manual:
1. Edit `config/config.ini` with your settings (OBS password, scenes, etc.)
2. Run: `irswitchd.exe --config config\config.ini`

## Notes

- The application runs silently in the background (no console window)
- Logs go to console (stderr) by default
- If `log_file` is set in config.ini, logs will also be written to that file
- `data/loading_history.json` will be created automatically in the data/ directory when first run

## Stopping the Service

- Use the GR Dashboard (http://127.0.0.1:17321/gr-status) and click "Shutdown Service"
- Or use Task Manager to end the process
"@

$readmePath = Join-Path "dist" "README.txt"
$readmeContent | Out-File -FilePath $readmePath -Encoding UTF8
Write-Host '  [OK] Created README.txt' -ForegroundColor Green

Write-Host ''
Write-Host 'Build complete! Distribution files are in dist/' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Distribution structure:' -ForegroundColor Yellow
Write-Host '  dist/'
Write-Host '    irswitchd.exe'
Write-Host '    config/'
Write-Host '      config.example.ini'
Write-Host '      config.ini'
Write-Host '    Install.ps1'
Write-Host '    Open-Dashboard.ps1'
Write-Host '    README.txt'
Write-Host ''
Write-Host 'Usage:' -ForegroundColor Yellow
Write-Host '  cd dist'
Write-Host '  powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -Wizard'
