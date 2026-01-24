# Git commit-msg hook pro automatické zvýšení verze podle commit message prefixu
# PowerShell verze pro Windows
#
# Prefixy:
#   fix:  → zvýší PATCH (0.3.0 → 0.3.1)
#   feat: → zvýší MINOR (0.3.0 → 0.4.0)
#   rel:  → zvýší MAJOR (0.3.0 → 1.0.0)

param(
    [Parameter(Mandatory=$true)]
    [string]$CommitMsgFile
)

# Přečíst commit message
$commitMsg = Get-Content -Path $CommitMsgFile -Raw

# Získat cestu k projektu
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$bumpScript = Join-Path $projectRoot "scripts" "bump_version.py"

# Zkontrolovat, zda existuje bump script
if (-not (Test-Path $bumpScript)) {
    Write-Warning "bump_version.py not found at $bumpScript"
    exit 0
}

# Spustit bump script s commit message
try {
    # Spustit Python skript a zachytit výstup
    $output = python $bumpScript $commitMsg 2>&1
    $exitCode = $LASTEXITCODE
    
    if ($exitCode -ne 0) {
        Write-Warning "Failed to bump version: $output"
        exit 0  # Nechceme blokovat commit, jen varování
    }
    
    # Výstup může obsahovat více řádků (error messages + version)
    # Najdeme řádek s verzí (formát X.Y.Z)
    $newVersion = $null
    foreach ($line in $output) {
        if ($line -match '^\d+\.\d+\.\d+$') {
            $newVersion = $line
            break
        }
    }
    
    # Pokud byla verze zvýšena, přidat změny do staging area
    if ($newVersion) {
        $initFile = Join-Path $projectRoot "src" "irswitch" "__init__.py"
        $pyprojectFile = Join-Path $projectRoot "pyproject.toml"
        
        git add $initFile $pyprojectFile 2>$null
        Write-Host "✓ Version bumped to $newVersion - files staged for commit"
    }
} catch {
    Write-Warning "Error in version bump hook: $_"
}

exit 0
