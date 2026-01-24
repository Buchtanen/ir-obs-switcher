#Requires -Version 5.1

<#
.SYNOPSIS
    Instaluje Git commit-msg hook pro automatické verzování.

.DESCRIPTION
    Tento skript instaluje commit-msg hook, který automaticky zvyšuje verzi aplikace
    podle prefixu commit message:
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
$hookFile = Join-Path -Path $gitHooksDir -ChildPath 'commit-msg'
$scriptsDir = Join-Path -Path $projectRoot -ChildPath 'scripts'
$hookScript = Join-Path -Path $scriptsDir -ChildPath 'commit-msg-hook.ps1'

# Funkce pro výstup
function Write-Success {
    param([string]$Message)
    Write-Host ('✓ ' + $Message) -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Cyan
}

function Write-WarningMsg {
    param([string]$Message)
    Write-Host ('⚠ ' + $Message) -ForegroundColor Yellow
}

# Vytvořit .git/hooks adresář pokud neexistuje
if (-not (Test-Path $gitHooksDir)) {
    New-Item -ItemType Directory -Path $gitHooksDir -Force | Out-Null
    Write-Info "Created .git/hooks directory"
}

# Zkontrolovat existenci hook skriptu
if (-not (Test-Path $hookScript)) {
    Write-Error "Hook script not found: $hookScript"
    exit 1
}

# Vytvořit wrapper batch soubor pro Windows Git
$hookScriptAbs = (Resolve-Path $hookScript).Path
$hookContentLines = @(
    '@echo off'
    ('powershell.exe -ExecutionPolicy Bypass -File "' + $hookScriptAbs + '" %1')
)
$hookContent = $hookContentLines -join "`r`n"

try {
    $hookContent | Out-File -FilePath $hookFile -Encoding ASCII -NoNewline -Force
    Write-Success "Installed commit-msg hook"
    Write-Info "  Hook file: $hookFile"
    Write-Info "  Script: $hookScriptAbs"
} catch {
    Write-Error "Failed to install hook: $_"
    exit 1
}

# Informace o bash hooku
$bashHookScript = Join-Path -Path $scriptsDir -ChildPath 'commit-msg-hook.sh'
if (Test-Path $bashHookScript) {
    Write-Info ''
    Write-Info ('Note: Bash hook script available at: ' + $bashHookScript)
    Write-Info '      For Git Bash, manually copy it to .git/hooks/commit-msg'
}

# Výstup s instrukcemi
Write-Host ''
Write-Host 'Git hook installed successfully!' -ForegroundColor Green
Write-Host ''
Write-Host 'Usage examples:' -ForegroundColor Cyan
Write-Host '  git commit -m ''fix: oprava bugu''     -> 0.3.0 -> 0.3.1 (PATCH)'
Write-Host '  git commit -m ''feat: nova funkce''     -> 0.3.0 -> 0.4.0 (MINOR)'
Write-Host '  git commit -m ''rel: major release''     -> 0.3.0 -> 1.0.0 (MAJOR)'
Write-Host ''
