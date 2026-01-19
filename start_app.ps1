# PowerShell script to start iRacing OBS Switcher service
# Usage: .\start_app.ps1 [-Config path/to/config.ini]
#        .\start_app.ps1 -Config "config\config.ini"
#        .\start_app.ps1 --config "config\config.ini"

# Get script directory first
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Parse arguments manually to support both -Config and --config formats
$Config = "config\config.ini"
if ($args.Count -gt 0) {
    for ($i = 0; $i -lt $args.Count; $i++) {
        if ($args[$i] -eq '--config' -or $args[$i] -eq '-Config' -or $args[$i] -eq '-config' -or $args[$i] -eq '-c') {
            if ($i + 1 -lt $args.Count) {
                $Config = $args[$i + 1]
                if ($args[$i] -eq '--config') {
                    Write-Host "Note: Using --config format (PowerShell prefers -Config)" -ForegroundColor Yellow
                }
                break
            }
        }
    }
}

Write-Host "Starting iRacing OBS Switcher..." -ForegroundColor Cyan
Write-Host ""

# Check if config file exists
if (-not (Test-Path $Config)) {
    Write-Host "Error: Config file not found: $Config" -ForegroundColor Red
    Write-Host "Please specify a valid config file with -Config parameter" -ForegroundColor Yellow
    Write-Host "Usage: .\start_app.ps1 -Config `"config\config.ini`"" -ForegroundColor Yellow
    exit 1
}

Write-Host "Using config: $Config" -ForegroundColor Green
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Python not found in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.11+ and add it to PATH" -ForegroundColor Yellow
    exit 1
}

# Check if package is installed
try {
    python -c "import irswitch" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing package in development mode..." -ForegroundColor Yellow
        pip install -e .
    }
} catch {
    Write-Host "Warning: Could not verify package installation" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Starting service..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Start the application
try {
    irswitchd --config $Config
} catch {
    Write-Host ""
    Write-Host "Error starting application: $_" -ForegroundColor Red
    exit 1
}
