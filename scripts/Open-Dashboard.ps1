#Requires -Version 5.1

<#
.SYNOPSIS
  Opens iRacing OBS Switcher dashboard in the default browser.

.EXAMPLE
  .\Open-Dashboard.ps1 -ConfigPath "config\config.ini"

.EXAMPLE
  .\Open-Dashboard.ps1 -ConfigPath "config\config.ini" -Vr
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$ConfigPath,
    [switch]$Vr
)

$ErrorActionPreference = "Stop"

function Read-IniAppHostPort {
    param([string]$Path)

    $section = ""
    $httpHost = "127.0.0.1"
    $port = 17321

    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $t = $line.Trim()
        if ($t -match '^\s*#') { continue }
        if ($t -match '^\s*\[(.+)\]\s*$') {
            $section = $Matches[1].ToLower()
            continue
        }
        if ($section -ne "app") { continue }

        if ($t -match '^\s*http_host\s*=\s*(.+)\s*$') {
            $httpHost = $Matches[1].Trim()
            continue
        }
        if ($t -match '^\s*http_port\s*=\s*(\d+)\s*$') {
            $port = [int]$Matches[1]
            continue
        }
    }

    return @{ Host = $httpHost; Port = $port }
}

if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    $scriptRoot = $PSScriptRoot
} else {
    $scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$scriptRoot = [System.IO.Path]::GetFullPath($scriptRoot)

# Relative -ConfigPath is resolved against the script directory (dist/), not the caller's CWD.
if (-not [System.IO.Path]::IsPathRooted($ConfigPath)) {
    $ConfigPath = Join-Path -Path $scriptRoot -ChildPath $ConfigPath
}
$cfgAbs = [System.IO.Path]::GetFullPath($ConfigPath)
if (-not (Test-Path -LiteralPath $cfgAbs)) {
    throw "Config not found: $cfgAbs"
}

$app = Read-IniAppHostPort -Path $cfgAbs

$path = if ($Vr) { "/vr-status" } else { "/gr-status" }
$url = "http://{0}:{1}{2}" -f $app.Host, $app.Port, $path

Start-Process $url | Out-Null
