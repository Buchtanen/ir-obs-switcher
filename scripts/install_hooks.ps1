# Instalační skript pro Git hooks (Windows PowerShell)
# Instaluje commit-msg hook pro automatické zvýšení verze

$ErrorActionPreference = "Stop"

# Získat cestu k projektu
$projectRoot = Split-Path -Parent $PSScriptRoot
$gitHooksDir = Join-Path $projectRoot ".git" "hooks"
$hookFile = Join-Path $gitHooksDir "commit-msg"

# Vytvořit .git/hooks adresář pokud neexistuje
if (-not (Test-Path $gitHooksDir)) {
    New-Item -ItemType Directory -Path $gitHooksDir -Force | Out-Null
    Write-Host "Created .git/hooks directory"
}

# Zkopírovat PowerShell hook skript
$hookScript = Join-Path $projectRoot "scripts" "commit-msg-hook.ps1"
if (Test-Path $hookScript) {
    # Vytvořit wrapper batch soubor pro Windows Git
    # Použijeme absolutní cestu k PowerShell skriptu pro spolehlivost
    $hookScriptAbs = (Resolve-Path $hookScript).Path
    $hookContent = @"
@echo off
powershell.exe -ExecutionPolicy Bypass -File "$hookScriptAbs" %1
"@
    
    $hookContent | Out-File -FilePath $hookFile -Encoding ASCII -NoNewline
    Write-Host "✓ Installed commit-msg hook (Windows wrapper)"
    Write-Host "  Hook file: $hookFile"
    Write-Host "  Script: $hookScriptAbs"
} else {
    Write-Error "Hook script not found: $hookScript"
    exit 1
}

# Alternativně použít bash hook pokud je dostupný Git Bash
$bashHookScript = Join-Path $projectRoot "scripts" "commit-msg-hook.sh"
if (Test-Path $bashHookScript) {
    # Git Bash může použít bash skript přímo
    Write-Host "Note: Bash hook script available at: $bashHookScript"
    Write-Host "      If using Git Bash, you can manually copy it to .git/hooks/commit-msg"
}

Write-Host ""
Write-Host "Git hook installed successfully!"
Write-Host ""
Write-Host "Usage:"
Write-Host "  git commit -m 'fix: oprava bugu'     → 0.3.0 → 0.3.1 (PATCH)"
Write-Host "  git commit -m 'feat: nova funkce'     → 0.3.0 → 0.4.0 (MINOR)"
Write-Host "  git commit -m 'rel: major release'     → 0.3.0 → 1.0.0 (MAJOR)"
Write-Host ""
