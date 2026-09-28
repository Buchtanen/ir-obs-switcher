param(
    [string]$PythonExecutable = 'python',
    [string]$OutputDirectory = 'dist/live-commentary'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    # Install .[supertonic] and PyInstaller in this interpreter before building.
    & $PythonExecutable -c 'import PyInstaller, supertonic, sounddevice, soundfile, onnxruntime'
    if ($LASTEXITCODE -ne 0) { throw 'Build environment requires PyInstaller and .[supertonic]' }
    $env:PYTHONPATH = Join-Path $projectRoot 'src'
    & $PythonExecutable -m PyInstaller --onefile --noconsole --name irswitchd `
        --paths src --collect-all irswitch --collect-all bleak --collect-all psutil `
        --collect-all supertonic --collect-all onnxruntime --collect-all sounddevice `
        --collect-all soundfile --collect-all huggingface_hub --hidden-import pynvml `
        --add-data 'assets;assets' --distpath $OutputDirectory `
        --workpath build/live-commentary --specpath build/live-commentary --clean --noupx `
        src/irswitch/main.py
    if ($LASTEXITCODE -ne 0) { throw 'Commentary EXE build failed' }
    $binary = Join-Path $OutputDirectory 'irswitchd.exe'
    @{
        commit = (git rev-parse HEAD)
        dirty = [bool](git status --porcelain --untracked-files=no)
        sha256 = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash
        builtAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        supertonic = $true
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'build-info.json') -Encoding utf8
} finally {
    Pop-Location
}
