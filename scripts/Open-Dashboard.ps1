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
    $host = "127.0.0.1"
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
            $host = $Matches[1].Trim()
            continue
        }
        if ($t -match '^\s*http_port\s*=\s*(\d+)\s*$') {
            $port = [int]$Matches[1]
            continue
        }
    }

    return @{ Host = $host; Port = $port }
}

$cfg = Resolve-Path -Path $ConfigPath -ErrorAction Stop
$app = Read-IniAppHostPort -Path $cfg.Path

$path = if ($Vr) { "/vr-status" } else { "/gr-status" }
$url = "http://{0}:{1}{2}" -f $app.Host, $app.Port, $path

Start-Process $url | Out-Null

