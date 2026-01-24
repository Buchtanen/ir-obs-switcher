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


# Copy necessary files to dist for distribution
Write-Host ""
Write-Host "Copying necessary files to dist..." -ForegroundColor Cyan

# Copy config directory
if (Test-Path "config") {
    $configDest = Join-Path "dist" "config"
    if (Test-Path $configDest) {
        Remove-Item -Path $configDest -Recurse -Force
    }
    Copy-Item -Path "config" -Destination $configDest -Recurse
    Write-Host "  ✓ Copied config/ directory" -ForegroundColor Green
} else {
    Write-Host "  ⚠ config/ directory not found" -ForegroundColor Yellow
}

# Create README for distribution
$readmeContent = @"
# iRacing OBS Switcher - Distribution

## Files

- `irswitchd.exe` - Main application (silent background process)
- `config/` - Configuration directory
  - `config.example.ini` - Example configuration
  - `config.ini` - Your configuration (edit this file)

## Usage

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
Write-Host "  ✓ Created README.txt" -ForegroundColor Green

Write-Host ""
Write-Host "Build complete! Distribution files are in dist\" -ForegroundColor Cyan
Write-Host ""
Write-Host "Distribution structure:" -ForegroundColor Yellow
Write-Host "  dist/"
Write-Host "    irswitchd.exe"
Write-Host "    config/"
Write-Host "      config.example.ini"
Write-Host "      config.ini"
Write-Host "    README.txt"
Write-Host ""
Write-Host "Usage:" -ForegroundColor Yellow
Write-Host "  cd dist"
Write-Host "  .\irswitchd.exe --config config\config.ini"
