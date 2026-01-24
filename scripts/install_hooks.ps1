#Requires -Version 5.1

<#
.SYNOPSIS
    Instaluje Git hooks pro automatické verzování.

.DESCRIPTION
    Tento skript instaluje prepare-commit-msg a post-commit hooky.
    Workflow:
    1. prepare-commit-msg: bumps version, stores pre-commit hashes
    2. Commit created (without version files)
    3. post-commit: detects version change, amends commit
    Result: One commit including version changes

    Prefixy:
    - fix:  -> PATCH (0.3.0 -> 0.3.1)
    - feat: -> MINOR (0.3.0 -> 0.4.0)
    - rel:  -> MAJOR (0.3.0 -> 1.0.0)

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
$prepareHookFile = Join-Path -Path $gitHooksDir -ChildPath 'prepare-commit-msg'
$postHookFile = Join-Path -Path $gitHooksDir -ChildPath 'post-commit'
$prepareScript = Join-Path -Path $scriptsDir -ChildPath 'prepare-commit-msg-hook.sh'
$postScript = Join-Path -Path $scriptsDir -ChildPath 'post-commit-hook.sh'

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

# Zkontrolovat existenci hook skriptů
if (-not (Test-Path $prepareScript)) {
    Write-ErrorMsg "Prepare hook script not found: $prepareScript"
    exit 1
}

if (-not (Test-Path $postScript)) {
    Write-ErrorMsg "Post-commit hook script not found: $postScript"
    exit 1
}

# Kopírovat prepare-commit-msg hook
try {
    Copy-Item -Path $prepareScript -Destination $prepareHookFile -Force
    Write-Success "Installed prepare-commit-msg hook"
} catch {
    Write-ErrorMsg "Failed to install prepare-commit-msg hook: $_"
    exit 1
}

# Kopírovat post-commit hook
try {
    Copy-Item -Path $postScript -Destination $postHookFile -Force
    Write-Success "Installed post-commit hook"
} catch {
    Write-ErrorMsg "Failed to install post-commit hook: $_"
    exit 1
}

# Výstup s instrukcemi
Write-Host ''
Write-Host 'Git hooks installed successfully!' -ForegroundColor Green
Write-Host ''
Write-Host 'Workflow:' -ForegroundColor Cyan
Write-Host '  1. prepare-commit-msg: bumps version, stores pre-commit hashes'
Write-Host '  2. Commit created (without version files)'
Write-Host '  3. post-commit: detects version change, amends commit'
Write-Host '  Result: One commit including version changes'
Write-Host ''
Write-Host 'Usage examples:' -ForegroundColor Cyan
Write-Host '  git commit -m ''fix: oprava bugu''     -> 0.3.0 -> 0.3.1 (PATCH)'
Write-Host '  git commit -m ''feat: nova funkce''     -> 0.3.0 -> 0.4.0 (MINOR)'
Write-Host '  git commit -m ''rel: major release''     -> 0.3.0 -> 1.0.0 (MAJOR)'
Write-Host ''