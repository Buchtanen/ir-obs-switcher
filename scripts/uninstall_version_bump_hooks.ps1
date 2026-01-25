#Requires -Version 5.1

<#
.SYNOPSIS
  Removes legacy version-bump git hooks from .git/hooks.

.DESCRIPTION
  Deletes prepare-commit-msg and post-commit hooks that were used for bumping
  version based on commit messages.

.EXAMPLE
  .\scripts\uninstall_version_bump_hooks.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDir
$gitHooksDir = Join-Path -Path $projectRoot -ChildPath '.git\hooks'

if (-not (Test-Path $gitHooksDir)) {
    Write-Host "No .git/hooks directory found at: $gitHooksDir" -ForegroundColor Yellow
    exit 0
}

$hooksToRemove = @('prepare-commit-msg', 'post-commit')
foreach ($hook in $hooksToRemove) {
    $path = Join-Path $gitHooksDir $hook
    if (Test-Path $path) {
        Remove-Item -Force $path
        Write-Host "Removed hook: $hook" -ForegroundColor Green
    } else {
        Write-Host "Not present: $hook" -ForegroundColor DarkGray
    }
}

