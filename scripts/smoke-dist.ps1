#Requires -Version 5.1

<#
.SYNOPSIS
  Non-interactive layout / install-state asserts for a real dist/ folder.

.DESCRIPTION
  Does NOT run the Install.ps1 wizard (interactive). Use for quick smoke of:
  - required dist layout files
  - optional Scheduled Task / desktop shortcut presence after manual install/uninstall

.EXAMPLE
  .\scripts\smoke-dist.ps1 -DistRoot .\dist

.EXAMPLE
  .\scripts\smoke-dist.ps1 -DistRoot .\dist -AssertInstalled

.EXAMPLE
  .\scripts\smoke-dist.ps1 -DistRoot .\dist -AssertUninstalled
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DistRoot,

    [switch]$AssertInstalled,
    [switch]$AssertUninstalled
)

$ErrorActionPreference = "Stop"

function Write-Ok([string]$Message) { Write-Host ("[OK] " + $Message) -ForegroundColor Green }
function Write-Fail([string]$Message) { Write-Host ("[ERROR] " + $Message) -ForegroundColor Red }

function Assert-PathExists([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing $Label`: $Path"
    }
    Write-Ok $Label
}

try {
    if ($AssertInstalled -and $AssertUninstalled) {
        throw "Use only one of -AssertInstalled / -AssertUninstalled."
    }

    $root = [System.IO.Path]::GetFullPath($DistRoot)
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "DistRoot is not a directory: $root"
    }

    Write-Host "DistRoot: $root"

    Assert-PathExists (Join-Path $root "irswitchd.exe") "irswitchd.exe"
    Assert-PathExists (Join-Path $root "Install.ps1") "Install.ps1"
    Assert-PathExists (Join-Path $root "Open-Dashboard.ps1") "Open-Dashboard.ps1"
    Assert-PathExists (Join-Path $root "config\config.example.ini") "config\config.example.ini"

    $taskName = "iRacing OBS Switcher"
    $desktop = [Environment]::GetFolderPath("Desktop")
    $startLnk = Join-Path $desktop "iRacing OBS Switcher.lnk"
    $dashLnk = Join-Path $desktop "iRacing OBS Switcher - Dashboard.lnk"

    if ($AssertInstalled) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -eq $task) {
            throw "Scheduled Task missing: $taskName"
        }
        Write-Ok "Scheduled Task present: $taskName"

        Assert-PathExists $startLnk "Start shortcut"
        Assert-PathExists $dashLnk "Dashboard shortcut"
    }

    if ($AssertUninstalled) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -ne $task) {
            throw "Scheduled Task still present: $taskName"
        }
        Write-Ok "Scheduled Task absent: $taskName"

        if (Test-Path -LiteralPath $startLnk) {
            throw "Start shortcut still present: $startLnk"
        }
        Write-Ok "Start shortcut absent"

        if (Test-Path -LiteralPath $dashLnk) {
            throw "Dashboard shortcut still present: $dashLnk"
        }
        Write-Ok "Dashboard shortcut absent"
    }

    Write-Ok "smoke-dist passed."
    exit 0
} catch {
    Write-Fail $_.Exception.Message
    exit 1
}
