# PowerShell script to start iRacing OBS Switcher service
# Usage: .\start_app.ps1 [-Config path/to/config.ini]
#        .\start_app.ps1 -Config "config\config.ini"
#        .\start_app.ps1 --config "config\config.ini"

$ErrorActionPreference = "Stop"

# Get script directory first
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Broken SSLKEYLOGFILE (e.g. inaccessible Volume GUID path) makes Python 3.14
# fail inside ssl.create_default_context() during `import aiohttp`.
if ($env:SSLKEYLOGFILE) {
    $keylog = $env:SSLKEYLOGFILE
    $usable = $false
    try {
        $parent = Split-Path -Parent $keylog
        if ($parent -and (Test-Path -LiteralPath $parent)) {
            $usable = $true
        }
    } catch {
        $usable = $false
    }
    if (-not $usable) {
        Write-Host "Clearing unusable SSLKEYLOGFILE: $keylog" -ForegroundColor Yellow
        Remove-Item Env:SSLKEYLOGFILE -ErrorAction SilentlyContinue
    }
}

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

# Prefer project .venv over global PATH Python / irswitchd
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$PythonExe = $null

if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
    Write-Host "Using venv Python: $PythonExe" -ForegroundColor Green
} else {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        $PythonExe = $cmd.Source
        Write-Host "Warning: .venv not found; using PATH Python: $PythonExe" -ForegroundColor Yellow
        Write-Host "Recommended: python -m venv .venv; .\.venv\Scripts\pip install -e ." -ForegroundColor Yellow
    }
}

if (-not $PythonExe) {
    Write-Host "Error: Python not found (.venv or PATH)" -ForegroundColor Red
    Write-Host "Please install Python 3.11+ and create .venv (see README Quick Start)" -ForegroundColor Yellow
    exit 1
}

$versionOutput = & $PythonExe --version 2>&1
Write-Host "Python: $versionOutput" -ForegroundColor Green

# Soft warn on very new Python (CI targets 3.11-3.13)
if ($versionOutput -match "Python (\d+)\.(\d+)") {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 14)) {
        Write-Host "Warning: Python $major.$minor is newer than CI matrix (3.11-3.13). Prefer 3.12/3.13 if deps fail." -ForegroundColor Yellow
    }
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
        Write-Host "Error: Python 3.11+ required (found $major.$minor)" -ForegroundColor Red
        exit 1
    }
}

# Fail-fast: package + overlay backends must import from the chosen interpreter.
# Old editable installs still import `irswitch`, so we also require bleak/psutil.
& $PythonExe -c "import irswitch, bleak, psutil" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing/updating editable irswitch (bleak, psutil, NVML) into:" -ForegroundColor Yellow
    Write-Host "  $PythonExe" -ForegroundColor Yellow
    & $PythonExe -m pip install -e .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: pip install -e . failed" -ForegroundColor Red
        exit 1
    }
    & $PythonExe -c "import irswitch, bleak, psutil"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: irswitch/bleak/psutil still not importable after install" -ForegroundColor Red
        Write-Host "Run: `"$PythonExe`" -m pip install -e ." -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""
Write-Host "Starting service..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

try {
    # Same interpreter as the pip install above (avoid PATH irswitchd mismatch).
    & $PythonExe -m irswitch.main --config $Config
    exit $LASTEXITCODE
} catch {
    Write-Host ""
    Write-Host "Error starting application: $_" -ForegroundColor Red
    exit 1
}
