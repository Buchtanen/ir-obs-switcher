#Requires -Version 5.1

<#
.SYNOPSIS
  Installer for iRacing OBS Switcher distribution (Windows).

.DESCRIPTION
  - Wizard to generate config.ini from config.example.ini (keeps comments by patching template)
  - Optionally sets YouTube OAuth env vars in User scope
  - Creates Scheduled Task (At log on) for silent autostart of irswitchd.exe
  - Creates desktop shortcuts: Start + Open Dashboard

.EXAMPLE
  # Run full wizard (recommended)
  .\Install.ps1 -Wizard

.EXAMPLE
  # Install task + shortcuts using existing config
  .\Install.ps1 -InstallTask -CreateShortcuts -ConfigPath "config\config.ini"

.EXAMPLE
  # Uninstall autostart task
  .\Install.ps1 -UninstallTask
#>

[CmdletBinding()]
param(
    [switch]$Wizard,
    [string]$ConfigPath = "config\config.ini",
    [switch]$InstallTask,
    [switch]$UninstallTask,
    [switch]$CreateShortcuts,
    [switch]$UninstallShortcuts,
    [switch]$SetOAuthEnv,
    [switch]$UnsetOAuthEnv,
    [switch]$Uninstall,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) { Write-Host $Message -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host ("[OK] " + $Message) -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host ("[WARN] " + $Message) -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host ("[ERROR] " + $Message) -ForegroundColor Red }

function Get-PlainTextFromSecureString([securestring]$Secure) {
    if ($null -eq $Secure) { return $null }
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function Read-Secret([string]$Prompt) {
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    return Get-PlainTextFromSecureString $secure
}

function Resolve-PathRelativeToRoot([string]$Root, [string]$PathMaybeRelative) {
    if ([string]::IsNullOrWhiteSpace($PathMaybeRelative)) {
        throw "Empty path"
    }
    if ([System.IO.Path]::IsPathRooted($PathMaybeRelative)) {
        return (Resolve-Path -Path $PathMaybeRelative).Path
    }
    $combined = Join-Path -Path $Root -ChildPath $PathMaybeRelative
    return $combined
}

function Ensure-Directory([string]$DirPath) {
    if (-not (Test-Path -LiteralPath $DirPath)) {
        New-Item -ItemType Directory -Path $DirPath -Force | Out-Null
    }
}

function Patch-IniLines {
    param(
        [Parameter(Mandatory=$true)][string[]]$Lines,
        [Parameter(Mandatory=$true)][string]$Section,
        [Parameter(Mandatory=$true)][string]$Key,
        [Parameter(Mandatory=$true)][string]$Value,
        [switch]$AllowCommented
    )

    $out = New-Object System.Collections.Generic.List[string]
    $inSection = $false
    $patched = $false
    $sectionPattern = '^\s*\[' + [Regex]::Escape($Section) + '\]\s*$'
    $anySectionPattern = '^\s*\[.*\]\s*$'
    $keyPattern = '^\s*' + [Regex]::Escape($Key) + '\s*='
    $commentedKeyPattern = '^\s*#\s*' + [Regex]::Escape($Key) + '\s*='

    foreach ($line in $Lines) {
        if ($line -match $sectionPattern) {
            $inSection = $true
            $out.Add($line)
            continue
        }
        if ($line -match $anySectionPattern) {
            $inSection = $false
            $out.Add($line)
            continue
        }

        if ($inSection -and -not $patched) {
            if ($line -match $keyPattern) {
                $out.Add("$Key = $Value")
                $patched = $true
                continue
            }
            if ($AllowCommented -and ($line -match $commentedKeyPattern)) {
                $out.Add("$Key = $Value")
                $patched = $true
                continue
            }
        }

        $out.Add($line)
    }

    return ,@($out.ToArray())
}

function Test-PortInUse([int]$Port) {
    try {
        if (Get-Command -Name Get-NetTCPConnection -ErrorAction SilentlyContinue) {
            $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
            return ($null -ne $listeners -and $listeners.Count -gt 0)
        }
    } catch {
        # ignore
    }
    return $false
}

function Ensure-OAuthEnvUser {
    param(
        [switch]$Interactive
    )

    $id = [Environment]::GetEnvironmentVariable("GOOGLE_OAUTH_CLIENT_ID", "User")
    $secret = [Environment]::GetEnvironmentVariable("GOOGLE_OAUTH_CLIENT_SECRET", "User")

    if (-not [string]::IsNullOrWhiteSpace($id) -and -not [string]::IsNullOrWhiteSpace($secret)) {
        Write-Ok "OAuth env vars already set in User scope (GOOGLE_OAUTH_CLIENT_ID/SECRET)."
        return
    }

    if (-not $Interactive) {
        Write-Warn "OAuth env vars missing; skipping (non-interactive)."
        return
    }

    Write-Info "YouTube OAuth (optional). If you don't use YouTube API features, you can skip."
    $want = (Read-Host "Configure YouTube OAuth via User env vars? (y/N)").Trim()
    if ($want.ToLower() -ne "y") {
        Write-Info "Skipping OAuth env vars."
        return
    }

    if ([string]::IsNullOrWhiteSpace($id)) {
        $id = (Read-Host "GOOGLE_OAUTH_CLIENT_ID").Trim()
    } else {
        Write-Info "GOOGLE_OAUTH_CLIENT_ID already set (User) - keeping existing value."
    }

    if ([string]::IsNullOrWhiteSpace($secret)) {
        $secret = Read-Secret "GOOGLE_OAUTH_CLIENT_SECRET"
    } else {
        Write-Info "GOOGLE_OAUTH_CLIENT_SECRET already set (User) - keeping existing value."
    }

    if ([string]::IsNullOrWhiteSpace($id) -or [string]::IsNullOrWhiteSpace($secret)) {
        Write-Warn "OAuth env vars not set (missing values)."
        return
    }

    # Set for current process (so StartNow sees it)
    $env:GOOGLE_OAUTH_CLIENT_ID = $id
    $env:GOOGLE_OAUTH_CLIENT_SECRET = $secret

    # Persist for current user (so Scheduled Task after logon sees it)
    [Environment]::SetEnvironmentVariable("GOOGLE_OAUTH_CLIENT_ID", $id, "User")
    [Environment]::SetEnvironmentVariable("GOOGLE_OAUTH_CLIENT_SECRET", $secret, "User")

    Write-Ok "OAuth env vars saved to User scope."
}

function Unset-OAuthEnvUser {
    param(
        [switch]$Interactive
    )

    $id = [Environment]::GetEnvironmentVariable("GOOGLE_OAUTH_CLIENT_ID", "User")
    $secret = [Environment]::GetEnvironmentVariable("GOOGLE_OAUTH_CLIENT_SECRET", "User")

    if ([string]::IsNullOrWhiteSpace($id) -and [string]::IsNullOrWhiteSpace($secret)) {
        Write-Ok "OAuth env vars not set in User scope (nothing to remove)."
        return
    }

    if (-not $Interactive) {
        Write-Warn "OAuth env vars present, but skipping removal (non-interactive)."
        return
    }

    Write-Info "YouTube OAuth env vars detected in User scope."
    $want = (Read-Host "Remove GOOGLE_OAUTH_CLIENT_ID/SECRET from User env vars? (y/N)").Trim()
    if ($want.ToLower() -ne "y") {
        Write-Info "Keeping OAuth env vars."
        return
    }

    [Environment]::SetEnvironmentVariable("GOOGLE_OAUTH_CLIENT_ID", $null, "User")
    [Environment]::SetEnvironmentVariable("GOOGLE_OAUTH_CLIENT_SECRET", $null, "User")

    Write-Ok "OAuth env vars removed from User scope."
}

function Run-Wizard {
    param(
        [Parameter(Mandatory=$true)][string]$DistRoot,
        [Parameter(Mandatory=$true)][string]$ConfigPathResolved
    )

    $configDir = Split-Path -Parent $ConfigPathResolved
    Ensure-Directory $configDir

    $template = Join-Path -Path $DistRoot -ChildPath "config\config.example.ini"
    if (-not (Test-Path -LiteralPath $template)) {
        throw "Template not found: $template"
    }

    if (Test-Path -LiteralPath $ConfigPathResolved) {
        $overwrite = (Read-Host "Config already exists at '$ConfigPathResolved'. Overwrite? (y/N)").Trim()
        if ($overwrite.ToLower() -ne "y") {
            Write-Info "Keeping existing config.ini."
            return
        }
    }

    Copy-Item -LiteralPath $template -Destination $ConfigPathResolved -Force
    $lines = Get-Content -LiteralPath $ConfigPathResolved -Encoding UTF8

    Write-Info ""
    Write-Info "Wizard: minimal required settings"

    # OBS settings (mandatory password)
    $wsUrlDefault = "ws://127.0.0.1:4455"
    $wsUrl = (Read-Host "OBS WebSocket URL [$wsUrlDefault]").Trim()
    if ([string]::IsNullOrWhiteSpace($wsUrl)) { $wsUrl = $wsUrlDefault }

    $obsPassword = Read-Secret "OBS WebSocket password"
    if ([string]::IsNullOrWhiteSpace($obsPassword)) {
        throw "OBS WebSocket password is required."
    }

    # App HTTP settings (optional)
    $hostDefault = "127.0.0.1"
    $portDefault = 17321

    $httpHost = (Read-Host "HTTP host [$hostDefault]").Trim()
    if ([string]::IsNullOrWhiteSpace($httpHost)) { $httpHost = $hostDefault }

    $httpPortStr = (Read-Host "HTTP port [$portDefault]").Trim()
    $httpPort = $portDefault
    if (-not [string]::IsNullOrWhiteSpace($httpPortStr)) {
        $parsed = 0
        if ([int]::TryParse($httpPortStr, [ref]$parsed) -and $parsed -gt 0 -and $parsed -lt 65536) {
            $httpPort = $parsed
        } else {
            Write-Warn "Invalid port '$httpPortStr', using default $portDefault."
        }
    }

    if (Test-PortInUse -Port $httpPort) {
        Write-Warn "Port $httpPort already has a listener. Running multiple instances will fail."
        Write-Warn "Installer will configure Scheduled Task to IgnoreNew instances to mitigate this."
    }

    # Logging to file (optional)
    $wantLog = (Read-Host "Log to file? (y/N)").Trim().ToLower()
    $logFile = $null
    if ($wantLog -eq "y") {
        $logDefault = "logs/irswitch.log"
        $logFile = (Read-Host "Log file path [$logDefault]").Trim()
        if ([string]::IsNullOrWhiteSpace($logFile)) { $logFile = $logDefault }
    }

    # Patch template lines
    $lines = Patch-IniLines -Lines $lines -Section "obs" -Key "ws_url" -Value $wsUrl
    $lines = Patch-IniLines -Lines $lines -Section "obs" -Key "password" -Value $obsPassword
    $lines = Patch-IniLines -Lines $lines -Section "app" -Key "http_host" -Value $httpHost
    $lines = Patch-IniLines -Lines $lines -Section "app" -Key "http_port" -Value $httpPort

    if ($logFile) {
        $lines = Patch-IniLines -Lines $lines -Section "app" -Key "log_file" -Value $logFile -AllowCommented
        # Ensure logs/ exists if using default relative logs path
        $logsDir = Join-Path -Path $DistRoot -ChildPath (Split-Path -Path $logFile -Parent)
        if (-not [string]::IsNullOrWhiteSpace($logsDir)) {
            Ensure-Directory $logsDir
        }
    }

    $lines | Out-File -FilePath $ConfigPathResolved -Encoding UTF8 -Force
    Write-Ok "Generated config: $ConfigPathResolved"

    # OAuth env vars
    if ($SetOAuthEnv) {
        Ensure-OAuthEnvUser -Interactive
    }
}

function Install-AutostartTask {
    param(
        [Parameter(Mandatory=$true)][string]$DistRoot,
        [Parameter(Mandatory=$true)][string]$ExePath,
        [Parameter(Mandatory=$true)][string]$ConfigAbsPath
    )

    $taskName = "iRacing OBS Switcher"
    $userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

    $action = New-ScheduledTaskAction -Execute $ExePath -Argument "--config `"$ConfigAbsPath`"" -WorkingDirectory $DistRoot

    $trigger = $null
    try {
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
    } catch {
        $trigger = New-ScheduledTaskTrigger -AtLogOn
    }

    $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType InteractiveToken -RunLevel LeastPrivilege
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -Hidden

    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Ok "Scheduled Task installed: $taskName (At log on, MultipleInstances=IgnoreNew)"
}

function Uninstall-AutostartTask {
    $taskName = "iRacing OBS Switcher"
    try {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
        Write-Ok "Scheduled Task removed: $taskName"
    } catch {
        Write-Warn "Scheduled Task not removed (maybe not present): $taskName"
    }
}

function Create-DesktopShortcuts {
    param(
        [Parameter(Mandatory=$true)][string]$DistRoot,
        [Parameter(Mandatory=$true)][string]$ExePath,
        [Parameter(Mandatory=$true)][string]$ConfigAbsPath
    )

    $desktop = [Environment]::GetFolderPath("Desktop")
    $wsh = New-Object -ComObject WScript.Shell

    $startLnk = Join-Path $desktop "iRacing OBS Switcher.lnk"
    $dashLnk = Join-Path $desktop "iRacing OBS Switcher - Dashboard.lnk"

    # Start shortcut
    $s = $wsh.CreateShortcut($startLnk)
    $s.TargetPath = $ExePath
    $s.Arguments = "--config `"$ConfigAbsPath`""
    $s.WorkingDirectory = $DistRoot
    $s.Save()

    # Dashboard shortcut (opens URL derived from config)
    $openScript = Join-Path $DistRoot "Open-Dashboard.ps1"
    $s2 = $wsh.CreateShortcut($dashLnk)
    $s2.TargetPath = "powershell.exe"
    $s2.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$openScript`" -ConfigPath `"$ConfigAbsPath`""
    $s2.WorkingDirectory = $DistRoot
    $s2.Save()

    Write-Ok "Desktop shortcuts created."
}

function Remove-DesktopShortcuts {
    $desktop = [Environment]::GetFolderPath("Desktop")

    $startLnk = Join-Path $desktop "iRacing OBS Switcher.lnk"
    $dashLnk = Join-Path $desktop "iRacing OBS Switcher - Dashboard.lnk"

    foreach ($p in @($startLnk, $dashLnk)) {
        try {
            if (Test-Path -LiteralPath $p) {
                Remove-Item -LiteralPath $p -Force -ErrorAction Stop
                Write-Ok "Removed shortcut: $p"
            } else {
                Write-Warn "Shortcut not present: $p"
            }
        } catch {
            Write-Warn "Failed to remove shortcut: $p"
        }
    }
}

function Start-AppNow {
    param(
        [Parameter(Mandatory=$true)][string]$DistRoot,
        [Parameter(Mandatory=$true)][string]$ExePath,
        [Parameter(Mandatory=$true)][string]$ConfigAbsPath
    )

    Write-Info "Starting app..."
    Start-Process -FilePath $ExePath -WorkingDirectory $DistRoot -ArgumentList @("--config", $ConfigAbsPath) | Out-Null
    Write-Ok "Start requested (silent)."
}

try {
    $scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $scriptRoot

    $distRoot = $scriptRoot

    # Convenience uninstall: remove autostart + shortcuts; offer OAuth cleanup (interactive).
    if ($Uninstall) {
        $UninstallTask = $true
        $UninstallShortcuts = $true
        if (-not $PSBoundParameters.ContainsKey("UnsetOAuthEnv")) {
            $UnsetOAuthEnv = $true
        }
    }

    # Defaults: wizard implies installing task + shortcuts and setting OAuth env
    if ($Wizard) {
        $InstallTask = $true
        $CreateShortcuts = $true
        if (-not $PSBoundParameters.ContainsKey("SetOAuthEnv")) {
            $SetOAuthEnv = $true
        }
    }

    if ($UninstallTask) {
        Uninstall-AutostartTask
    }

    if ($UninstallShortcuts) {
        Remove-DesktopShortcuts
    }

    if ($UnsetOAuthEnv) {
        Unset-OAuthEnvUser -Interactive
    }

    $needsDistLayout = ($Wizard -or $InstallTask -or $CreateShortcuts -or $StartNow)
    if ($needsDistLayout) {
        # Validate dist layout (must contain irswitchd.exe)
        $exe = Join-Path $scriptRoot "irswitchd.exe"
        if (-not (Test-Path -LiteralPath $exe)) {
            throw "irswitchd.exe not found at '$exe'. Run this installer from the distribution folder (dist/)."
        }
    } else {
        # Keep variable for later branches; not required in uninstall-only runs.
        $exe = Join-Path $scriptRoot "irswitchd.exe"
    }

    if ($Wizard) {
        $configAbs = Resolve-PathRelativeToRoot -Root $distRoot -PathMaybeRelative $ConfigPath
        Run-Wizard -DistRoot $distRoot -ConfigPathResolved $configAbs
    } else {
        if ($SetOAuthEnv) {
            # Non-wizard: only set env when explicitly requested
            Ensure-OAuthEnvUser -Interactive:$false
        }
    }

    if ($InstallTask) {
        $configAbs = Resolve-PathRelativeToRoot -Root $distRoot -PathMaybeRelative $ConfigPath
        if (-not (Test-Path -LiteralPath $configAbs)) {
            throw "Config not found: $configAbs (run with -Wizard or provide an existing config)."
        }
        Install-AutostartTask -DistRoot $distRoot -ExePath $exe -ConfigAbsPath $configAbs
    }

    if ($CreateShortcuts) {
        $configAbs = Resolve-PathRelativeToRoot -Root $distRoot -PathMaybeRelative $ConfigPath
        if (-not (Test-Path -LiteralPath $configAbs)) {
            throw "Config not found: $configAbs (run with -Wizard or provide an existing config)."
        }
        Create-DesktopShortcuts -DistRoot $distRoot -ExePath $exe -ConfigAbsPath $configAbs
    }

    if ($StartNow) {
        $configAbs = Resolve-PathRelativeToRoot -Root $distRoot -PathMaybeRelative $ConfigPath
        if (-not (Test-Path -LiteralPath $configAbs)) {
            throw "Config not found: $configAbs (run with -Wizard or provide an existing config)."
        }
        Start-AppNow -DistRoot $distRoot -ExePath $exe -ConfigAbsPath $configAbs
    }

    Write-Info ""
    Write-Ok "Done."
} catch {
    Write-Fail $_.Exception.Message
    exit 1
}

