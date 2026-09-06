# Copy irswitch session tapes into the private LoRA/dataset repo inbox.
# Default sibling: ..\ir-commentary-lora  (override with IRSWITCH_LORA_REPO)
param(
    [string]$LoraRepo = $env:IRSWITCH_LORA_REPO,
    [string]$Recordings = "",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$irswitchRoot = Split-Path -Parent $PSScriptRoot
if (-not $LoraRepo) {
    $LoraRepo = Join-Path (Split-Path -Parent $irswitchRoot) "ir-commentary-lora"
}
if (-not $Recordings) {
    $Recordings = Join-Path $irswitchRoot "recordings"
}
if (-not (Test-Path $LoraRepo)) {
    throw "LoRA repo not found: $LoraRepo (clone Buchtanen/ir-commentary-lora next to irswitch, or set IRSWITCH_LORA_REPO)"
}
$inbox = Join-Path $LoraRepo "tapes\inbox"
New-Item -ItemType Directory -Force -Path $inbox | Out-Null
$files = @(Get-ChildItem -Path $Recordings -Filter "overlay-*.jsonl" -ErrorAction SilentlyContinue)
if ($files.Count -eq 0) {
    Write-Error "No overlay-*.jsonl in $Recordings"
    exit 1
}
foreach ($file in $files) {
    Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $inbox $file.Name) -Force
    Write-Output "copied $($file.Name)"
}
if ($Clean) {
    $python = Join-Path $irswitchRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        $python = "python"
    }
    & $python (Join-Path $LoraRepo "scripts\clean_tapes.py")
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
Write-Output "inbox=$inbox files=$($files.Count)"
