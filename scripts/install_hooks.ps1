#Requires -Version 5.1

<#
.SYNOPSIS
    Instaluje Git hooks pro lokální lint/format (podobné CI).

.DESCRIPTION
    Tento skript instaluje:
    - pre-commit: ruff --fix + black na staged .py souborech (auto-fix + re-stage)
    - pre-push: mypy src/ (pokud je nainstalované)

    Zároveň odstraní staré hooky pro automatické bumpování verze
    (prepare-commit-msg + post-commit).

.EXAMPLE
    .\scripts\install_hooks.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# Získat cesty
$scriptDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDir
$gitDir = Join-Path -Path $projectRoot -ChildPath '.git'
$gitHooksDir = Join-Path -Path $gitDir -ChildPath 'hooks'
$scriptsDir = Join-Path -Path $projectRoot -ChildPath 'scripts'

# Hook soubory
$preCommitHookFile = Join-Path -Path $gitHooksDir -ChildPath 'pre-commit'
$prePushHookFile = Join-Path -Path $gitHooksDir -ChildPath 'pre-push'
$preCommitScript = Join-Path -Path $scriptsDir -ChildPath 'pre-commit-hook.sh'
$prePushScript = Join-Path -Path $scriptsDir -ChildPath 'pre-push-hook.sh'

# Funkce pro výstup
function Write-Success {
    param([string]$Message)
    Write-Host ('✓ ' + $Message) -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Cyan
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host ('✗ ' + $Message) -ForegroundColor Red
}

# Vytvořit .git/hooks adresář pokud neexistuje
if (-not (Test-Path $gitHooksDir)) {
    New-Item -ItemType Directory -Path $gitHooksDir -Force | Out-Null
    Write-Info "Created .git/hooks directory"
}

# Odinstalovat staré version-bump hooky (pokud existují)
foreach ($oldHook in @('prepare-commit-msg', 'post-commit')) {
    $oldHookPath = Join-Path $gitHooksDir $oldHook
    if (Test-Path $oldHookPath) {
        try {
            Remove-Item -Path $oldHookPath -Force
            Write-Info "Removed old hook: $oldHook"
        } catch {
            Write-Warning "Failed to remove old hook ${oldHook}: $_"
        }
    }
}

# Zkontrolovat existenci nových hook skriptů
if (-not (Test-Path $preCommitScript)) {
    Write-ErrorMsg "pre-commit hook script not found: $preCommitScript"
    exit 1
}

if (-not (Test-Path $prePushScript)) {
    Write-ErrorMsg "pre-push hook script not found: $prePushScript"
    exit 1
}

try {
    Copy-Item -Path $preCommitScript -Destination $preCommitHookFile -Force
    Write-Success "Installed pre-commit hook"
} catch {
    Write-ErrorMsg "Failed to install pre-commit hook: $_"
    exit 1
}

try {
    Copy-Item -Path $prePushScript -Destination $prePushHookFile -Force
    Write-Success "Installed pre-push hook"
} catch {
    Write-ErrorMsg "Failed to install pre-push hook: $_"
    exit 1
}

# Výstup s instrukcemi
Write-Host ''
Write-Host 'Git hooks installed successfully!' -ForegroundColor Green
Write-Host ''
Write-Host 'Hooks:' -ForegroundColor Cyan
Write-Host '  pre-commit: ruff --fix + black na staged .py souborech (auto-fix + re-stage)'
Write-Host '  pre-push:   mypy src/ (pokud je nainstalované)'
Write-Host ''
Write-Host 'Doporučené závislosti:' -ForegroundColor Cyan
Write-Host '  pip install -e ".[lint]"'
Write-Host ''