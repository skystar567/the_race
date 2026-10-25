param(
    [string]$DataDir = '',
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $taskPython)) {
    throw 'Missing .venv. Follow README to create it and install requirements.lock first.'
}
Push-Location -LiteralPath $taskRoot
try {
    $taskArgs = @('-m', 'campus', '--port', $Port)
    if ($DataDir) { $taskArgs += @('--data-dir', $DataDir) }
    & $taskPython @taskArgs
    if ($LASTEXITCODE -ne 0) { throw "Startup failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
