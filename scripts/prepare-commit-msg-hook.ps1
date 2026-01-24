# Git prepare-commit-msg hook pro automatické zvýšení verze podle commit message prefixu
#
# Tento hook běží PŘED vytvořením commitu, což umožňuje modifikovat staging area
# tak, aby změny byly zahrnuty ve stejném commitu.
#
# Prefixy:
#   fix:  → zvýší PATCH (0.3.0 → 0.3.1)
#   feat: → zvýší MINOR (0.3.0 → 0.4.0)
#   rel:  → zvýší MAJOR (0.3.0 → 1.0.0)

param(
    [Parameter(Mandatory=$true)]
    [string]$CommitMsgFile,

    [Parameter(Mandatory=$false)]
    [string]$CommitSource,  # "message", "template", "merge", "squash", "commit"

    [Parameter(Mandatory=$false)]
    [string]$Sha1  # SHA1 commitu (prázdné pro nový commit)
)

# Přečíst commit message
$commitMsg = Get-Content -Path $CommitMsgFile -Raw

# Kontrolovat, že nepouštíme při merge, squash atd.
# Jen při normálním commit message ("message")
if ($CommitSource -ne "message" -and $CommitSource -ne "") {
    exit 0
}

# Získat cestu k projektu
# Hook běží z .git/hooks/, potřebujeme najít project root
$hookDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$gitDir = Split-Path -Parent $hookDir
$projectRoot = Split-Path -Parent $gitDir
$bumpScript = Join-Path $projectRoot "scripts" "bump_version.py"

# Zkontrolovat, zda existuje bump script
if (-not (Test-Path $bumpScript)) {
    Write-Warning "bump_version.py not found at $bumpScript"
    exit 0
}

# Spustit bump script s commit message
try {
    # Změnit working directory na project root pro správné relativní cesty
    Push-Location $projectRoot

    # Spustit Python skript a zachytit výstup
    $output = python $bumpScript $commitMsg 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Warning "Failed to bump version: $output"
        Pop-Location
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

        # Zkontrolovat, zda soubory skutečně existují a byly změněny
        if ((Test-Path $initFile) -and (Test-Path $pyprojectFile)) {
            git add $initFile $pyprojectFile 2>$null
            Write-Host "Version bumped to $newVersion - files staged for commit"
        } else {
            Write-Warning "Version files not found or not modified"
        }
    }

    Pop-Location
} catch {
    Write-Warning "Error in version bump hook: $_"
    if (Get-Location -Stack) {
        Pop-Location
    }
}

exit 0